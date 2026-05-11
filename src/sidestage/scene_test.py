from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sidestage.character import Character
from sidestage.entity import Entity, EntityId, EntityType
from sidestage.events import EntityChanged
from sidestage.message import Message
from sidestage.scene import Scene, SceneResponse, SimpleScene

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def make_character_mock(
    id: str,
    *,
    is_human: bool = False,
) -> MagicMock:
    """A test double for Character.

    `has_human_actor()` is set directly on the mock — we don't want test
    failures here to depend on live Actor wiring.
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


class _Recorder:
    """Minimal sync Listener that records every event it receives."""

    def __init__(self) -> None:
        self.events: list[EntityChanged] = []

    def notify(self, event: EntityChanged) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Scene base class invariants
# ---------------------------------------------------------------------------


class TestSceneBase:
    def test_scene_is_entity_subclass(self) -> None:
        # scene-class: Scene inherits from Entity.
        assert issubclass(Scene, Entity)

    def test_scene_messages_is_abstract_property_on_base(self) -> None:
        # scene-messages-property: `messages` is an abstract property on Scene.
        # Subclasses own the backing storage.
        attr = Scene.__dict__.get("messages")
        assert attr is not None, "Scene must define a `messages` property"
        assert isinstance(attr, property)
        assert getattr(attr.fget, "__isabstractmethod__", False) is True


# ---------------------------------------------------------------------------
# Scene._append_message (still present as the internal helper)
# ---------------------------------------------------------------------------


class TestSceneAppendMessage:
    def test_append_history(self) -> None:
        # scene-append-history: Appends message to self.messages.
        scene = make_simple_scene()
        sender = make_character_mock("user", is_human=True)
        m = Message(sender=sender, body="first")
        scene._append_message(m)
        assert scene.messages == [m]

    def test_append_history_preserves_order(self) -> None:
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

    def test_append_return(self) -> None:
        # scene-append-return: Returns the new index (len-1).
        scene = make_simple_scene()
        s = make_character_mock("user", is_human=True)
        idx0 = scene._append_message(Message(sender=s, body="a"))
        idx1 = scene._append_message(Message(sender=s, body="b"))
        idx2 = scene._append_message(Message(sender=s, body="c"))
        assert idx0 == 0
        assert idx1 == 1
        assert idx2 == 2


# ---------------------------------------------------------------------------
# Scene.append (the new public mutation API)
# ---------------------------------------------------------------------------


class TestSceneAppend:
    """scene-append: Public mutation API. Records, emits, returns the index."""

    async def test_append_records_message(self) -> None:
        # scene-append-records: appended via _append_message; visible in
        # scene.messages.
        scene = make_simple_scene()
        sender = make_character_mock("u", is_human=True)
        m = Message(sender=sender, body="hello")
        scene.append(m)
        assert scene.messages == [m]

    async def test_append_records_in_order(self) -> None:
        # scene-append-records: subsequent appends preserve order.
        scene = make_simple_scene()
        s = make_character_mock("s", is_human=True)
        m0 = Message(sender=s, body="a")
        m1 = Message(sender=s, body="b")
        m2 = Message(sender=s, body="c")
        scene.append(m0)
        scene.append(m1)
        scene.append(m2)
        assert scene.messages == [m0, m1, m2]

    async def test_append_returns_index_for_first(self) -> None:
        # scene-append-returns: returns the new message's index; first append is 0.
        scene = make_simple_scene(scene_id="sceneid")
        sender = make_character_mock("u", is_human=True)
        result = scene.append(Message(sender=sender, body="hi"))
        assert result == 0, (
            f"scene-append-returns: first append must return index 0; got {result!r}"
        )

    async def test_append_returns_monotonic_indices(self) -> None:
        # scene-append-returns: index advances per-append.
        scene = make_simple_scene(scene_id="s")
        u = make_character_mock("u", is_human=True)
        r0 = scene.append(Message(sender=u, body="a"))
        r1 = scene.append(Message(sender=u, body="b"))
        r2 = scene.append(Message(sender=u, body="c"))
        assert (r0, r1, r2) == (0, 1, 2), (
            "scene-append-returns: index advances by 1 per append; "
            f"got {(r0, r1, r2)!r}"
        )

    async def test_append_emits_entity_changed_to_subscribers(self) -> None:
        # scene-append-emits: a subscribed listener receives an EntityChanged
        # whose entity is the scene and whose attributes contains "messages".
        # Use a fresh scene with NO character listeners interfering — but the
        # SimpleScene constructor subscribes them. We add our own recorder.
        scene = make_simple_scene()
        recorder = _Recorder()
        scene.subscribe(recorder)

        sender = make_character_mock("u", is_human=True)
        scene.append(Message(sender=sender, body="hi"))

        # _emit wraps each listener in a task (events-async-tasks); wait for
        # them to settle before asserting.
        await scene.idle()

        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert isinstance(event, EntityChanged)
        assert event.entity is scene
        assert "messages" in event.attributes

    async def test_append_emits_once_per_call(self) -> None:
        # scene-append-emits: exactly one EntityChanged per append.
        scene = make_simple_scene()
        recorder = _Recorder()
        scene.subscribe(recorder)
        s = make_character_mock("u", is_human=True)
        scene.append(Message(sender=s, body="a"))
        scene.append(Message(sender=s, body="b"))
        scene.append(Message(sender=s, body="c"))
        await scene.idle()
        assert len(recorder.events) == 3
        for event in recorder.events:
            assert event.entity is scene
            assert "messages" in event.attributes


# ---------------------------------------------------------------------------
# Scene.serialize_message
# ---------------------------------------------------------------------------


class TestSceneSerializeMessage:
    def test_serialize_message_builds_model(self) -> None:
        # scene-serialize-message: returns Message.Model with scene_id,
        # index, sender_id, body.
        scene = make_simple_scene(scene_id="scene-77")
        sender = make_character_mock("char-x")
        scene._append_message(Message(sender=sender, body="hello"))
        model = scene.serialize_message(0)
        assert isinstance(model, Message.Model)
        assert model.scene_id == EntityId("scene-77"), (
            "scene-serialize-message: model.scene_id MUST echo self.id; "
            f"got {model.scene_id!r}"
        )
        assert model.index == 0, (
            "scene-serialize-message: model.index MUST equal the requested "
            f"position; got {model.index!r}"
        )
        assert model.sender_id == EntityId("char-x")
        assert model.body == "hello"

    def test_serialize_message_indices_advance(self) -> None:
        # scene-serialize-message: index reflects the requested position.
        scene = make_simple_scene(scene_id="abc")
        s = make_character_mock("u")
        scene._append_message(Message(sender=s, body="m0"))
        scene._append_message(Message(sender=s, body="m1"))
        scene._append_message(Message(sender=s, body="m2"))
        assert scene.serialize_message(0).index == 0
        assert scene.serialize_message(1).index == 1
        assert scene.serialize_message(2).index == 2


# ---------------------------------------------------------------------------
# Scene.Model + Scene.deserialize
# ---------------------------------------------------------------------------


class TestSceneModel:
    def test_scene_model_exists(self) -> None:
        # scene-model: Scene.Model is an inner Pydantic model.
        assert hasattr(Scene, "Model")

    def test_scene_model_has_characters_field_of_entity_ids(self) -> None:
        # scene-model: characters is `list[EntityId]` (NOT active_character_ids).
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            characters=[EntityId("c1"), EntityId("c2")],
        )
        assert model.characters == [EntityId("c1"), EntityId("c2")]

    def test_scene_model_does_not_have_active_character_ids(self) -> None:
        # scene-model: spec mandates `characters`, NOT `active_character_ids`.
        fields = Scene.Model.model_fields
        assert "characters" in fields
        assert "active_character_ids" not in fields


class TestSceneDeserialize:
    def test_deserialize_resolves_each_id_via_app_factory(self) -> None:
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

    def test_deserialize_constructs_via_cls(self) -> None:
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

    def test_deserialize_signature_uniform_with_entity(self) -> None:
        # scene-deserialize-signature: same `(cls, model)` signature as
        # Entity.deserialize.
        import inspect

        sig = inspect.signature(Scene.deserialize)
        params = list(sig.parameters.keys())
        # Bound classmethod — params is ["model"].
        assert params == ["model"]


class TestSceneToModel:
    """scene-to-model: inverse of Scene.deserialize."""

    def test_to_model_returns_scene_model(self) -> None:
        scene = make_simple_scene(scene_id="s")
        model = scene.to_model()
        assert isinstance(model, Scene.Model)

    def test_to_model_captures_id_name_body(self) -> None:
        user = make_character_mock("u", is_human=True)
        npc = make_character_mock("n", is_human=False)
        scene = SimpleScene(
            id=EntityId("scn-7"),
            name="My Scene",
            body="The body",
            characters=[user, npc],
        )
        model = scene.to_model()
        assert model.id == EntityId("scn-7")
        assert model.name == "My Scene"
        assert model.body == "The body"

    def test_to_model_captures_character_ids_in_order(self) -> None:
        # scene-to-model: characters is a list of EntityId (NOT Character).
        user = make_character_mock("alpha", is_human=True)
        npc = make_character_mock("beta", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        model = scene.to_model()
        assert model.characters == [EntityId("alpha"), EntityId("beta")]

    def test_to_model_round_trips_with_deserialize(self) -> None:
        # scene-to-model is the inverse of Scene.deserialize for the
        # persistent on-disk shape.
        user = make_character_mock("c1", is_human=True)
        npc = make_character_mock("c2", is_human=False)
        scene = SimpleScene(
            id=EntityId("rt"),
            name="round-trip",
            body="b",
            characters=[user, npc],
        )
        model = scene.to_model()

        fake_factory = MagicMock()
        fake_factory.get.side_effect = lambda i: {"c1": user, "c2": npc}[i]
        with patch("sidestage.server.App.factory", fake_factory, create=True):
            rebuilt = SimpleScene.deserialize(model)

        assert rebuilt.id == scene.id
        assert rebuilt.name == scene.name
        assert rebuilt.body == scene.body
        assert rebuilt.characters == scene.characters


# ---------------------------------------------------------------------------
# SimpleScene constructor
# ---------------------------------------------------------------------------


class TestSimpleSceneInit:
    def test_init_messages_starts_empty(self) -> None:
        # simple-scene-init-messages: self._messages = [].
        scene = make_simple_scene()
        assert scene._messages == []
        assert isinstance(scene._messages, list)

    def test_init_count_raises_when_not_two(self) -> None:
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

    def test_init_user_must_be_human(self) -> None:
        # simple-scene-init-user: ValueError if characters[0].has_human_actor()
        # is False.
        non_human = make_character_mock("u", is_human=False)
        npc = make_character_mock("n", is_human=False)
        with pytest.raises(ValueError):
            SimpleScene(
                id=EntityId("s"),
                name="x",
                body="b",
                characters=[non_human, npc],
            )

    def test_init_npc_must_not_be_human(self) -> None:
        # simple-scene-init-npc: ValueError if characters[1].has_human_actor()
        # is True.
        user = make_character_mock("u", is_human=True)
        also_human = make_character_mock("n", is_human=True)
        with pytest.raises(ValueError):
            SimpleScene(
                id=EntityId("s"),
                name="x",
                body="b",
                characters=[user, also_human],
            )

    def test_init_aliases_set(self) -> None:
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

    def test_init_subscribes_every_character(self) -> None:
        # simple-scene-init-subscribes-characters: every character in
        # `characters` ends up in scene._listeners after construction.
        user = make_character_mock("u", is_human=True)
        npc = make_character_mock("n", is_human=False)
        scene = SimpleScene(
            id=EntityId("s"),
            name="x",
            body="b",
            characters=[user, npc],
        )
        assert user in scene._listeners
        assert npc in scene._listeners

    def test_init_subscribes_characters_only(self) -> None:
        # simple-scene-init-subscribes-characters: no extra unrelated listeners
        # are added.
        user = make_character_mock("u", is_human=True)
        npc = make_character_mock("n", is_human=False)
        scene = SimpleScene(
            id=EntityId("s"),
            name="x",
            body="b",
            characters=[user, npc],
        )
        assert len(scene._listeners) == 2


# ---------------------------------------------------------------------------
# SimpleScene.messages property
# ---------------------------------------------------------------------------


class TestSimpleSceneMessages:
    def test_messages_returns_underlying_list(self) -> None:
        # simple-scene-messages: returns self._messages.
        scene = make_simple_scene()
        assert scene.messages is scene._messages

    def test_messages_mutable_via_append_message(self) -> None:
        # simple-scene-messages: mutable; _append_message mutates in place.
        scene = make_simple_scene()
        s = make_character_mock("s")
        m = Message(sender=s, body="a")
        scene._append_message(m)
        assert scene.messages == [m]
        assert scene._messages == [m]


# ---------------------------------------------------------------------------
# Scene.user_characters
# ---------------------------------------------------------------------------


class TestSceneUserCharacters:
    def test_user_characters_returns_only_human_actors(self) -> None:
        # scene-user-characters: subset of `characters` with has_human_actor()
        # True.
        user = make_character_mock("user", is_human=True)
        npc = make_character_mock("npc", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        assert scene.user_characters == [user]

    def test_user_characters_preserves_scene_order(self) -> None:
        # scene-user-characters: order follows `characters` order — filter only.
        user = make_character_mock("user", is_human=True)
        npc = make_character_mock("npc", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        # user is at characters[0], so it appears first (and is the only one).
        assert scene.user_characters == [
            c for c in scene.characters if c.has_human_actor()
        ]

    def test_user_characters_is_property(self) -> None:
        # scene-user-characters: declared as a property on Scene.
        attr = Scene.__dict__.get("user_characters")
        assert isinstance(attr, property)


# ---------------------------------------------------------------------------
# Scene.to_response + SceneResponse
# ---------------------------------------------------------------------------


class TestSceneToResponse:
    def test_to_response_builds_scene_response(self) -> None:
        # scene-to-response: returns a SceneResponse with id, name,
        # character_ids, and player_character_ids populated correctly.
        user = make_character_mock("user-1", is_human=True)
        npc = make_character_mock("npc-1", is_human=False)
        scene = make_simple_scene(user=user, npc=npc, scene_id="scn-7")
        # SimpleScene constructor sets name="Test Scene".
        resp = scene.to_response()
        assert isinstance(resp, SceneResponse)
        assert resp.id == EntityId("scn-7")
        assert resp.name == "Test Scene"
        assert resp.character_ids == [EntityId("user-1"), EntityId("npc-1")]
        assert resp.player_character_ids == [EntityId("user-1")]

    def test_to_response_player_character_ids_excludes_npcs(self) -> None:
        # scene-to-response: player_character_ids only includes user_characters.
        user = make_character_mock("u", is_human=True)
        npc = make_character_mock("n", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        resp = scene.to_response()
        assert EntityId("u") in resp.player_character_ids
        assert EntityId("n") not in resp.player_character_ids

    def test_to_response_character_ids_includes_all_characters(self) -> None:
        # scene-to-response: character_ids has every character's id, in order.
        user = make_character_mock("u", is_human=True)
        npc = make_character_mock("n", is_human=False)
        scene = make_simple_scene(user=user, npc=npc)
        resp = scene.to_response()
        assert resp.character_ids == [EntityId("u"), EntityId("n")]
