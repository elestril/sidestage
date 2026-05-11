from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from sidestage.actor import Actor, SceneUpdatedEvent, StubActor, UserActor
from sidestage.entity import EntityId
from sidestage.message import Message


class TestActorBase:
    def test_actor_notify_default_noop(self):
        # actor-notify-default-noop: Default Actor.notify does nothing — no
        # exception, no side effect. Verify by constructing a minimal concrete
        # subclass that does NOT override notify, and calling it.
        class MinimalActor(Actor):
            def is_human(self) -> bool:
                return False

            async def respond(self, message, character):
                return None

        actor = MinimalActor()
        event = SceneUpdatedEvent(scene_id=EntityId("s1"), latest_message_index=0)
        # Should return None and not raise.
        result = actor.notify(event)
        assert result is None


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
        # body=character.body) regardless of message.sender. The body comes
        # from the character, not a hardcoded string.
        actor = StubActor()
        character = MagicMock()
        character.body = "canned response"

        # Try with a human sender.
        sender_human = MagicMock()
        sender_human.has_human_actor.return_value = True
        msg1 = Message(sender=sender_human, body="anything")
        result1 = await actor.respond(msg1, character)
        assert result1 is not None
        assert result1.sender is character
        assert result1.body == character.body
        assert result1.body == "canned response"

        # And with a non-human sender — same result, no filtering.
        sender_npc = MagicMock()
        sender_npc.has_human_actor.return_value = False
        msg2 = Message(sender=sender_npc, body="anything")
        result2 = await actor.respond(msg2, character)
        assert result2 is not None
        assert result2.sender is character
        assert result2.body == character.body
        assert result2.body == "canned response"


class TestUserActor:
    def test_user_actor_implements_actor(self):
        # user-actor: UserActor is a concrete Actor.
        actor = UserActor()
        assert isinstance(actor, Actor)

    def test_user_actor_constructor_takes_nothing(self):
        # user-actor: Constructor takes no arguments — no scene field.
        actor = UserActor()
        assert not hasattr(actor, "scene")

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
        sender_human.has_human_actor.return_value = True
        sender_npc = MagicMock()
        sender_npc.has_human_actor.return_value = False
        assert await actor.respond(Message(sender=sender_human, body="hi"), character) is None
        assert await actor.respond(Message(sender=sender_npc, body="hi"), character) is None

    def test_user_actor_add_queue(self):
        # user-actor-add-queue: Registers queue for SSE delivery.
        # Verified observably by notify() broadcasting to it.
        actor = UserActor()
        q1: asyncio.Queue = asyncio.Queue()
        actor.add_queue(q1)
        event = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        actor.notify(event)
        assert q1.qsize() == 1
        assert q1.get_nowait() is event

    def test_user_actor_add_queue_multiple(self):
        # user-actor-add-queue: multiple queues all become registered.
        actor = UserActor()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        actor.add_queue(q1)
        actor.add_queue(q2)
        event = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        actor.notify(event)
        assert q1.qsize() == 1
        assert q2.qsize() == 1

    def test_user_actor_remove_queue(self):
        # user-actor-remove-queue: Deregisters queue. After removal it does
        # NOT receive subsequent broadcasts.
        actor = UserActor()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        actor.add_queue(q1)
        actor.add_queue(q2)
        actor.remove_queue(q1)
        event = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        actor.notify(event)
        assert q1.qsize() == 0
        assert q2.qsize() == 1

    def test_user_actor_remove_queue_missing_is_noop(self):
        # user-actor-remove-queue: No-op if not registered.
        actor = UserActor()
        q1: asyncio.Queue = asyncio.Queue()
        q_missing: asyncio.Queue = asyncio.Queue()
        actor.add_queue(q1)
        # Should not raise.
        actor.remove_queue(q_missing)
        # q1 still registered.
        event = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        actor.notify(event)
        assert q1.qsize() == 1

    def test_user_actor_notify_broadcasts_same_instance_to_all_queues(self):
        # user-actor-notify-broadcast: Puts the SAME event instance onto every
        # registered queue via put_nowait. No copying.
        actor = UserActor()
        q1 = MagicMock()
        q2 = MagicMock()
        q3 = MagicMock()
        actor.add_queue(q1)
        actor.add_queue(q2)
        actor.add_queue(q3)

        event = SceneUpdatedEvent(scene_id=EntityId("scene-xyz"), latest_message_index=11)
        actor.notify(event)

        # Each queue received exactly one put_nowait call.
        q1.put_nowait.assert_called_once()
        q2.put_nowait.assert_called_once()
        q3.put_nowait.assert_called_once()

        # The exact same event instance was dispatched to all queues.
        ev1 = q1.put_nowait.call_args.args[0]
        ev2 = q2.put_nowait.call_args.args[0]
        ev3 = q3.put_nowait.call_args.args[0]
        assert ev1 is event
        assert ev2 is event
        assert ev3 is event

    def test_user_actor_notify_broadcast_real_queues(self):
        # user-actor-notify-broadcast: integration with real asyncio.Queue.
        actor = UserActor()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        actor.add_queue(q1)
        actor.add_queue(q2)

        event = SceneUpdatedEvent(scene_id=EntityId("scene-abc"), latest_message_index=5)
        actor.notify(event)

        assert q1.qsize() == 1
        assert q2.qsize() == 1
        # Same instance ends up on both queues.
        assert q1.get_nowait() is event
        assert q2.get_nowait() is event

    def test_user_actor_notify_no_queues_is_noop(self):
        # user-actor-notify-broadcast: with no registered queues, nothing
        # happens — no exception.
        actor = UserActor()
        event = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        actor.notify(event)


class TestSceneUpdatedEvent:
    def test_scene_updated_event_fields(self):
        ev = SceneUpdatedEvent(scene_id=EntityId("s1"), latest_message_index=0)
        assert ev.scene_id == "s1"
        assert ev.latest_message_index == 0
