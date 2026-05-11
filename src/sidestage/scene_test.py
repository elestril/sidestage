from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from sidestage.actor import SceneUpdatedEvent
from sidestage.character import Character
from sidestage.entity import Entity, EntityId, EntityType
from sidestage.message import Message, MessageId
from sidestage.scene import Scene, SimpleScene


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def make_character_mock(
    id: str,
    *,
    is_human: bool = False,
) -> MagicMock:
    """A test double for Character.

    `has_human_actor()` is set directly on the mock per the agent directives —
    we don't want test failures here to depend on live Actor wiring.
    """
    char = MagicMock(spec=Character)
    char.id = EntityId(id)
    char.has_human_actor = MagicMock(return_value=is_human)
    return char


def make_simple_scene(
    *,
    user: MagicMock | None = None,
    npc: MagicMock | None = None,
    scene_id: str = "scene-1",
) -> SimpleScene:
    user = user or make_character_mock("user", is_human=True)
    npc = npc or make_character_mock("npc", is_human=False)
    return SimpleScene(
        id=EntityId(scene_id),
        name="Test Scene",
        body="scene body",
        characters=[user, npc],
    )


# ---------------------------------------------------------------------------
# Scene base class invariants
# ---------------------------------------------------------------------------


class TestSceneBase:
    def test_scene_is_entity_subclass(self):
        # scene-class: Scene inherits from Entity.
        assert issubclass(Scene, Entity)

    def test_scene_messages_is_abstract_property_on_base(self):
        # scene-messages-property: `messages` is an abstract property on Scene.
        # Subclasses own the backing storage.
        attr = Scene.__dict__.get("messages")
        assert attr is not None, "Scene must define a `messages` property"
        assert isinstance(attr, property)
        assert getattr(attr.fget, "__isabstractmethod__", False) is True

    def test_dispatch_is_abstract_on_base(self):
        # Scene.dispatch is abstract.
        attr = Scene.__dict__.get("dispatch")
        assert attr is not None
        assert getattr(attr, "__isabstractmethod__", False) is True

class TestSceneAppendMessage:
    def test_append_history(self):
        # scene-append-history: Appends message to self.messages.
        scene = make_simple_scene()
        sender = make_character_mock("user", is_human=True)
        m = Message(sender=sender, body="first")
        scene._append_message(m)
        assert scene.messages == [m]

    def test_append_history_preserves_order(self):
        # scene-append-history: ordered list.
        scene = make_simple_scene()
        s = make_character_mock("user", is_human=True)
        m0 = Message(sender=s, body="a")
        m1 = Message(sender=s, body="b")
        m2 = Message(sender=s, body="c")
        scene._append_message(m0)
        scene._append_message(m1)
        scene._append_message(m2)
        assert scene.messages == [m0, m1, m2]

    def test_append_return(self):
        # scene-append-return: Returns the new index (len-1).
        scene = make_simple_scene()
        s = make_character_mock("user", is_human=True)
        idx0 = scene._append_message(Message(sender=s, body="a"))
        idx1 = scene._append_message(Message(sender=s, body="b"))
        idx2 = scene._append_message(Message(sender=s, body="c"))
        assert idx0 == 0
        assert idx1 == 1
        assert idx2 == 2


class TestSceneSerializeMessage:
    def test_serialize_message_builds_model(self):
        # scene-serialize-message: returns Message.Model with composed id, sender_id, body.
        scene = make_simple_scene(scene_id="scene-77")
        sender = make_character_mock("char-x")
        scene._append_message(Message(sender=sender, body="hello"))
        model = scene.serialize_message(0)
        assert isinstance(model, Message.Model)
        assert model.id == MessageId("scene-77:0")
        assert model.sender_id == EntityId("char-x")
        assert model.body == "hello"

    def test_serialize_message_uses_index_in_id(self):
        # scene-serialize-message + message-id-format.
        scene = make_simple_scene(scene_id="abc")
        s = make_character_mock("u")
        scene._append_message(Message(sender=s, body="m0"))
        scene._append_message(Message(sender=s, body="m1"))
        scene._append_message(Message(sender=s, body="m2"))
        assert scene.serialize_message(0).id == "abc:0"
        assert scene.serialize_message(1).id == "abc:1"
        assert scene.serialize_message(2).id == "abc:2"


# ---------------------------------------------------------------------------
# Scene.Model + Scene.deserialize
# ---------------------------------------------------------------------------


class TestSceneModel:
    def test_scene_model_exists(self):
        # scene-model: Scene.Model is an inner Pydantic model.
        assert hasattr(Scene, "Model")

    def test_scene_model_has_characters_field_of_entity_ids(self):
        # scene-model: characters is `list[EntityId]` (NOT active_character_ids).
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            characters=[EntityId("c1"), EntityId("c2")],
        )
        assert model.characters == [EntityId("c1"), EntityId("c2")]

    def test_scene_model_does_not_have_active_character_ids(self):
        # scene-model: spec mandates `characters`, NOT `active_character_ids`.
        fields = Scene.Model.model_fields
        assert "characters" in fields
        assert "active_character_ids" not in fields


class TestSceneDeserialize:
    def test_deserialize_resolves_each_id_via_app_factory(self):
        # scene-deserialize-resolves: each id in model.characters is resolved
        # via App.factory.get(id) to a Character.
        user = make_character_mock("c1", is_human=True)
        npc = make_character_mock("c2", is_human=False)

        fake_factory = MagicMock()
        fake_factory.get.side_effect = lambda i: {"c1": user, "c2": npc}[i]

        with patch("sidestage.server.App.factory", fake_factory, create=True):
            model = SimpleScene.Model(
                id=EntityId("s"),
                name="n",
                type=EntityType.SCENE,
                body="b",
                characters=[EntityId("c1"), EntityId("c2")],
            )
            scene = SimpleScene.deserialize(model)

        assert fake_factory.get.call_count == 2
        fake_factory.get.assert_any_call(EntityId("c1"))
        fake_factory.get.assert_any_call(EntityId("c2"))
        assert scene.characters == [user, npc]

    def test_deserialize_constructs_via_cls(self):
        # scene-deserialize-constructs: returns cls(id=..., name=..., body=...,
        # characters=resolved).
        user = make_character_mock("c1", is_human=True)
        npc = make_character_mock("c2", is_human=False)

        fake_factory = MagicMock()
        fake_factory.get.side_effect = lambda i: {"c1": user, "c2": npc}[i]

        with patch("sidestage.server.App.factory", fake_factory, create=True):
            model = SimpleScene.Model(
                id=EntityId("scn"),
                name="My Scene",
                type=EntityType.SCENE,
                body="The body",
                characters=[EntityId("c1"), EntityId("c2")],
            )
            scene = SimpleScene.deserialize(model)

        assert isinstance(scene, SimpleScene)
        assert scene.id == EntityId("scn")
        assert scene.name == "My Scene"
        assert scene.body == "The body"
        assert scene.characters == [user, npc]

    def test_deserialize_signature_uniform_with_entity(self):
        # scene-deserialize-signature: same `(cls, model)` signature as Entity.deserialize.
        import inspect

        sig = inspect.signature(Scene.deserialize)
        params = list(sig.parameters.keys())
        # Bound classmethod — params is ["model"].
        assert params == ["model"]


# ---------------------------------------------------------------------------
# SimpleScene constructor
# ---------------------------------------------------------------------------


class TestSimpleSceneInit:
    def test_init_messages_starts_empty(self):
        # simple-scene-init-messages: self._messages = [].
        scene = make_simple_scene()
        assert scene._messages == []
        assert isinstance(scene._messages, list)

    def test_init_count_raises_when_not_two(self):
        # simple-scene-init-count: ValueError if len(characters) != 2.
        u = make_character_mock("u", is_human=True)
        n = make_character_mock("n", is_human=False)
        extra = make_character_mock("x", is_human=False)
        with pytest.raises(ValueError):
            SimpleScene(id=EntityId("s"), name="x", body="b", characters=[u])
        with pytest.raises(ValueError):
            SimpleScene(id=EntityId("s"), name="x", body="b", characters=[u, n, extra])
        with pytest.raises(ValueError):
            SimpleScene(id=EntityId("s"), name="x", body="b", characters=[])

    def test_init_user_must_be_human(self):
        # simple-scene-init-user: ValueError if characters[0].has_human_actor() is False.
        non_human = make_character_mock("u", is_human=False)
        npc = make_character_mock("n", is_human=False)
        with pytest.raises(ValueError):
            SimpleScene(
                id=EntityId("s"),
                name="x",
                body="b",
                characters=[non_human, npc],
            )

    def test_init_npc_must_not_be_human(self):
        # simple-scene-init-npc: ValueError if characters[1].has_human_actor() is True.
        user = make_character_mock("u", is_human=True)
        also_human = make_character_mock("n", is_human=True)
        with pytest.raises(ValueError):
            SimpleScene(
                id=EntityId("s"),
                name="x",
                body="b",
                characters=[user, also_human],
            )

    def test_init_aliases_set(self):
        # simple-scene-init-aliases: _user = characters[0], _npc = characters[1].
        user = make_character_mock("the-user", is_human=True)
        npc = make_character_mock("the-npc", is_human=False)
        scene = SimpleScene(
            id=EntityId("s"),
            name="x",
            body="b",
            characters=[user, npc],
        )
        assert scene._user is user
        assert scene._npc is npc


# ---------------------------------------------------------------------------
# SimpleScene.messages property
# ---------------------------------------------------------------------------


class TestSimpleSceneMessages:
    def test_messages_returns_underlying_list(self):
        # simple-scene-messages: returns self._messages.
        scene = make_simple_scene()
        assert scene.messages is scene._messages

    def test_messages_mutable_via_append_message(self):
        # simple-scene-messages: mutable; _append_message mutates in place.
        scene = make_simple_scene()
        s = make_character_mock("s")
        m = Message(sender=s, body="a")
        scene._append_message(m)
        assert scene.messages == [m]
        assert scene._messages == [m]


# ---------------------------------------------------------------------------
# SimpleScene.dispatch
# ---------------------------------------------------------------------------


class TestSimpleSceneDispatch:
    async def test_dispatch_appends_incoming_to_history(self):
        # simple-scene-dispatch-append: dispatch calls _append_message(message).
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)

        async def async_resp(_msg):
            return None

        npc.respond = MagicMock(side_effect=async_resp)
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        scene.dispatch(msg)
        assert msg in scene.messages
        assert scene.messages[0] is msg

    async def test_dispatch_returns_message_id_with_correct_format(self):
        # simple-scene-dispatch-return: returns MessageId(f"{self.id}:{index}").
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)

        async def async_resp(_msg):
            return None

        npc.respond = MagicMock(side_effect=async_resp)
        scene = make_simple_scene(user=user, npc=npc, scene_id="my-scene")
        msg = Message(sender=user, body="hi")
        result = scene.dispatch(msg)
        assert result == MessageId("my-scene:0")

    async def test_dispatch_returns_index_for_each_subsequent_message(self):
        # simple-scene-dispatch-return: index is per-scene monotonic.
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)

        async def async_resp(_msg):
            return None

        npc.respond = MagicMock(side_effect=async_resp)
        scene = make_simple_scene(user=user, npc=npc, scene_id="s")
        m0 = scene.dispatch(Message(sender=user, body="a"))
        m1 = scene.dispatch(Message(sender=user, body="b"))
        assert m0 == "s:0"
        assert m1 == "s:1"

    def test_dispatch_spawns_create_task(self, monkeypatch):
        # simple-scene-dispatch-task: dispatch calls asyncio.create_task on _respond.
        import sidestage.scene as scene_mod

        captured = {}

        def fake_create_task(coro):
            captured["coro"] = coro
            coro.close()
            return MagicMock()

        monkeypatch.setattr(scene_mod.asyncio, "create_task", fake_create_task)

        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        scene.dispatch(msg)
        assert "coro" in captured
        # The captured coroutine was created by calling self._respond(message).
        # We can't easily inspect the coroutine's args after .close(), but we
        # confirmed a task was spawned without dispatch awaiting itself.

    def test_dispatch_does_not_await(self, monkeypatch):
        # simple-scene-dispatch-task: dispatch is synchronous and does NOT await.
        import sidestage.scene as scene_mod

        monkeypatch.setattr(
            scene_mod.asyncio,
            "create_task",
            lambda coro: (coro.close(), MagicMock())[1],
        )

        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)
        # Make npc.respond raise if called synchronously — proves dispatch
        # doesn't traverse it on the calling thread.
        npc.respond = MagicMock(side_effect=AssertionError("respond called sync"))
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        result = scene.dispatch(msg)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# SimpleScene._respond
# ---------------------------------------------------------------------------


class TestSimpleSceneRespond:
    async def test_respond_awaits_npc_respond_with_message(self):
        # simple-scene-respond-call: response = await self._npc.respond(message).
        # Character.respond is async.
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)

        async def async_respond(message):
            return None

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        await scene._respond(msg)
        npc.respond.assert_called_once_with(msg)

    async def test_respond_appends_response_when_not_none(self):
        # simple-scene-respond-append: appends response to messages when non-None.
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)
        response = Message(sender=npc, body="Hello User!")

        async def async_respond(_msg):
            return response

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        await scene._respond(msg)
        assert response in scene.messages

    async def test_respond_does_not_append_when_none(self):
        # simple-scene-respond-append (negative): no append when response is None.
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)

        async def async_respond(_msg):
            return None

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc)
        msg = Message(sender=user, body="hi")
        await scene._respond(msg)
        assert scene.messages == []

    async def test_respond_notifies_user_with_event(self):
        # simple-scene-respond-notify: builds an event via
        # self._make_scene_update(latest_index) and calls self._user.notify(event).
        user = make_character_mock("user-1", is_human=True)
        user.notify = MagicMock()
        npc = make_character_mock("npc-1", is_human=False)
        response = Message(sender=npc, body="hi back")

        async def async_respond(_msg):
            return response

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc, scene_id="s")
        # Pre-populate with one message so the response lands at index 1.
        scene._append_message(Message(sender=user, body="seed"))
        await scene._respond(Message(sender=user, body="trigger"))
        user.notify.assert_called_once()
        (event,), _ = user.notify.call_args
        assert isinstance(event, SceneUpdatedEvent)
        assert event.scene_id == EntityId("s")
        assert event.latest_message_index == 1

    async def test_respond_uses_make_scene_update_to_build_event(self):
        # simple-scene-respond-notify: the event is constructed via
        # self._make_scene_update(latest_index) — not built inline.
        user = make_character_mock("user-1", is_human=True)
        user.notify = MagicMock()
        npc = make_character_mock("npc-1", is_human=False)
        response = Message(sender=npc, body="hi back")

        async def async_respond(_msg):
            return response

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc, scene_id="s")
        sentinel = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=42)
        scene._make_scene_update = MagicMock(return_value=sentinel)
        await scene._respond(Message(sender=user, body="trigger"))
        # latest_index will be 0 here since nothing was pre-appended.
        scene._make_scene_update.assert_called_once_with(0)
        user.notify.assert_called_once_with(sentinel)

    async def test_respond_does_not_notify_when_response_none(self):
        # simple-scene-respond-notify (negative): notify only fires when a response
        # was appended.
        user = make_character_mock("user-1", is_human=True)
        user.notify = MagicMock()
        npc = make_character_mock("npc-1", is_human=False)

        async def async_respond(_msg):
            return None

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc)
        await scene._respond(Message(sender=user, body="hi"))
        user.notify.assert_not_called()


# ---------------------------------------------------------------------------
# SimpleScene._make_scene_update
# ---------------------------------------------------------------------------


class TestSceneMakeUpdate:
    def test_make_scene_update_returns_event_with_scene_id_and_index(self):
        # scene-make-update: returns SceneUpdatedEvent(scene_id=self.id,
        # latest_message_index=latest_index).
        scene = make_simple_scene(scene_id="scene-xyz")
        event = scene._make_scene_update(7)
        assert isinstance(event, SceneUpdatedEvent)
        assert event.scene_id == EntityId("scene-xyz")
        assert event.latest_message_index == 7

    def test_make_scene_update_uses_self_id(self):
        # scene-make-update: scene_id is self.id, not something else.
        scene = make_simple_scene(scene_id="another")
        event = scene._make_scene_update(0)
        assert event.scene_id == EntityId("another")
        assert event.latest_message_index == 0


# ---------------------------------------------------------------------------
# End-to-end via dispatch + drain
# ---------------------------------------------------------------------------


class TestSimpleSceneEndToEnd:
    async def test_dispatch_then_drain_event_loop_appends_response(self):
        # End-to-end: with a real event loop, dispatch's fire-and-forget task
        # eventually appends the response and notifies the user.
        user = make_character_mock("user-1", is_human=True)
        user.notify = MagicMock()
        npc = make_character_mock("npc-1", is_human=False)
        response = Message(sender=npc, body="Hello User!")

        async def async_respond(_msg):
            return response

        npc.respond = MagicMock(side_effect=async_respond)
        scene = make_simple_scene(user=user, npc=npc, scene_id="s")
        msg = Message(sender=user, body="hi")

        mid = scene.dispatch(msg)
        assert mid == "s:0"
        # Yield control so the spawned task can run.
        for _ in range(5):
            await asyncio.sleep(0)
        assert scene.messages == [msg, response]
        user.notify.assert_called_once()
        (event,), _ = user.notify.call_args
        assert isinstance(event, SceneUpdatedEvent)
        assert event.scene_id == EntityId("s")
        assert event.latest_message_index == 1
