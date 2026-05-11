from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

from sidestage.actor import Actor, QueueListener, StubActor, UserActor
from sidestage.events import EntityChanged
from sidestage.message import Message


class TestActorBase:
    def test_actor_is_abstract(self):
        # actor-base: Actor is abstract — `is_human` and `respond` are
        # abstract methods, instantiation must fail.
        try:
            Actor()  # type: ignore[abstract]
        except TypeError:
            return
        raise AssertionError("Actor() should have raised TypeError")

    def test_actor_minimal_concrete_subclass_works(self):
        # actor-base: A subclass implementing the two abstract methods
        # instantiates fine and is recognized as an Actor.
        class MinimalActor(Actor):
            def is_human(self) -> bool:
                return False

            async def respond(self, message, character):
                return None

        actor = MinimalActor()
        assert isinstance(actor, Actor)
        assert actor.is_human() is False


class TestStubActor:
    def test_stub_actor_implements_actor(self):
        # stub-actor: StubActor is a concrete Actor.
        assert isinstance(StubActor(), Actor)

    def test_stub_actor_is_human(self):
        # stub-actor-is-human: Returns False.
        actor = StubActor()
        assert actor.is_human() is False

    async def test_stub_actor_respond_returns_character_body(self):
        # stub-actor-respond-returns: Returns Message(sender=character,
        # body=character.body) regardless of message.sender. Body comes
        # from the character, not a hardcoded string.
        actor = StubActor()
        character = MagicMock()
        character.body = "canned response"

        sender_human = MagicMock()
        msg1 = Message(sender=sender_human, body="anything")
        result1 = await actor.respond(msg1, character)
        assert result1 is not None
        assert result1.sender is character
        assert result1.body == character.body
        assert result1.body == "canned response"

        # Different sender — same result, no filtering.
        sender_npc = MagicMock()
        msg2 = Message(sender=sender_npc, body="anything")
        result2 = await actor.respond(msg2, character)
        assert result2 is not None
        assert result2.sender is character
        assert result2.body == character.body


class TestUserActorBasics:
    def test_user_actor_implements_actor(self):
        # user-actor: UserActor is a concrete Actor.
        actor = UserActor()
        assert isinstance(actor, Actor)

    def test_user_actor_constructor_takes_nothing(self):
        # user-actor: Constructor takes no arguments.
        actor = UserActor()
        # Internal subscription tracker exists and starts empty.
        assert actor._subscriptions == []

    def test_user_actor_is_human(self):
        # user-actor-is-human: Returns True.
        actor = UserActor()
        assert actor.is_human() is True

    async def test_user_actor_respond_noop(self):
        # user-actor-respond-noop: Returns None unconditionally. Human
        # responses arrive via REST.
        actor = UserActor()
        character = MagicMock()
        sender_human = MagicMock()
        sender_npc = MagicMock()
        assert (
            await actor.respond(Message(sender=sender_human, body="hi"), character)
            is None
        )
        assert (
            await actor.respond(Message(sender=sender_npc, body="hi"), character)
            is None
        )


class TestQueueListener:
    def test_queue_listener_puts_event_on_queue(self):
        # queue-listener-notify: notify enqueues the event via put_nowait.
        # Same instance lands on the queue.
        queue: asyncio.Queue = asyncio.Queue()
        listener = QueueListener(queue)
        event = EntityChanged(entity=MagicMock(), attributes=["messages"])

        listener.notify(event)

        assert queue.qsize() == 1
        assert queue.get_nowait() is event

    def test_queue_listener_drops_on_queue_full(self, caplog):
        # events-errors-slow-consumer: when the queue is full, notify
        # swallows the QueueFull and logs a warning. No exception
        # propagates to the emitter.
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        listener = QueueListener(queue)
        ev1 = EntityChanged(entity=MagicMock(), attributes=["a"])
        ev2 = EntityChanged(entity=MagicMock(), attributes=["b"])

        listener.notify(ev1)  # fills the queue.

        with caplog.at_level(logging.WARNING, logger="sidestage.actor"):
            listener.notify(ev2)  # would block — must drop, not raise.

        # ev1 is still queued; ev2 was dropped.
        assert queue.qsize() == 1
        assert queue.get_nowait() is ev1
        # A warning was logged.
        assert any(
            record.levelno == logging.WARNING and "slow consumer" in record.message
            for record in caplog.records
        ), f"Expected slow-consumer WARNING; got: {[r.message for r in caplog.records]}"


class TestUserActorSubscribeTo:
    def test_subscribe_to_creates_queue_listener_and_subscribes(self):
        # user-actor-subscribe-to: wraps queue in a QueueListener, calls
        # entity.subscribe with that listener.
        actor = UserActor()
        entity = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity, queue)

        entity.subscribe.assert_called_once()
        passed_listener = entity.subscribe.call_args.args[0]
        assert isinstance(passed_listener, QueueListener)
        assert passed_listener.queue is queue

    def test_subscribe_to_tracks_subscription(self):
        # user-actor-subscribe-to: tracks the (entity, listener) pair so
        # later `unsubscribe_from` / `cancel_all` can find it.
        actor = UserActor()
        entity = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity, queue)

        assert len(actor._subscriptions) == 1
        tracked_entity, tracked_listener = actor._subscriptions[0]
        assert tracked_entity is entity
        assert isinstance(tracked_listener, QueueListener)
        assert tracked_listener.queue is queue

    def test_subscribe_to_multiple_pairs_each_tracked(self):
        # user-actor-subscribe-to: multiple subscriptions accumulate;
        # each entity gets its own subscribe() call.
        actor = UserActor()
        entity_a = MagicMock()
        entity_b = MagicMock()
        q_a: asyncio.Queue = asyncio.Queue()
        q_b: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity_a, q_a)
        actor.subscribe_to(entity_b, q_b)

        assert len(actor._subscriptions) == 2
        entity_a.subscribe.assert_called_once()
        entity_b.subscribe.assert_called_once()


class TestUserActorUnsubscribeFrom:
    def test_unsubscribe_from_calls_entity_unsubscribe(self):
        # user-actor-unsubscribe-from: calls entity.unsubscribe with the
        # SAME QueueListener that was subscribed.
        actor = UserActor()
        entity = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity, queue)
        subscribed_listener = entity.subscribe.call_args.args[0]

        actor.unsubscribe_from(entity, queue)

        entity.unsubscribe.assert_called_once_with(subscribed_listener)

    def test_unsubscribe_from_drops_tracked_pair(self):
        # user-actor-unsubscribe-from: drops the (entity, listener) pair
        # from internal tracking.
        actor = UserActor()
        entity = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity, queue)
        assert len(actor._subscriptions) == 1

        actor.unsubscribe_from(entity, queue)
        assert actor._subscriptions == []

    def test_unsubscribe_from_missing_is_noop(self):
        # user-actor-unsubscribe-from: no-op if not subscribed. Does not
        # raise, does not call entity.unsubscribe.
        actor = UserActor()
        entity = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()

        # Never subscribed.
        actor.unsubscribe_from(entity, queue)

        entity.unsubscribe.assert_not_called()
        assert actor._subscriptions == []

    def test_unsubscribe_from_other_queue_is_noop(self):
        # user-actor-unsubscribe-from: only matches the exact (entity, queue)
        # pair. A different queue on the same entity does not match.
        actor = UserActor()
        entity = MagicMock()
        q_subscribed: asyncio.Queue = asyncio.Queue()
        q_other: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity, q_subscribed)

        actor.unsubscribe_from(entity, q_other)

        entity.unsubscribe.assert_not_called()
        assert len(actor._subscriptions) == 1

    def test_unsubscribe_from_only_drops_matching_pair(self):
        # user-actor-unsubscribe-from: with several tracked pairs, only
        # the matching (entity, queue) pair is removed.
        actor = UserActor()
        entity_a = MagicMock()
        entity_b = MagicMock()
        q_a: asyncio.Queue = asyncio.Queue()
        q_b: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity_a, q_a)
        actor.subscribe_to(entity_b, q_b)

        actor.unsubscribe_from(entity_a, q_a)

        # Only entity_a.unsubscribe was called.
        entity_a.unsubscribe.assert_called_once()
        entity_b.unsubscribe.assert_not_called()
        # Only the b-pair remains tracked.
        assert len(actor._subscriptions) == 1
        remaining_entity, _ = actor._subscriptions[0]
        assert remaining_entity is entity_b


class TestUserActorCancelAll:
    def test_cancel_all_unsubscribes_each(self):
        # user-actor-cancel-all: every tracked pair is unsubscribed. After
        # the call, internal tracking is empty.
        actor = UserActor()
        entity_a = MagicMock()
        entity_b = MagicMock()
        entity_c = MagicMock()
        q_a: asyncio.Queue = asyncio.Queue()
        q_b: asyncio.Queue = asyncio.Queue()
        q_c: asyncio.Queue = asyncio.Queue()

        actor.subscribe_to(entity_a, q_a)
        actor.subscribe_to(entity_b, q_b)
        actor.subscribe_to(entity_c, q_c)

        actor.cancel_all()

        entity_a.unsubscribe.assert_called_once()
        entity_b.unsubscribe.assert_called_once()
        entity_c.unsubscribe.assert_called_once()
        assert actor._subscriptions == []

    def test_cancel_all_with_no_subscriptions_is_noop(self):
        # user-actor-cancel-all: empty tracker — no-op, no exception.
        actor = UserActor()
        actor.cancel_all()
        assert actor._subscriptions == []
