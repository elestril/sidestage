from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.entity import Entity, EntityId, EntityList, EntityType
from sidestage.events import EntityChanged, ListDelta
from sidestage.message import Message
from sidestage.scene import Scene, SimpleScene

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _patch_get_actor(actor: object | None = None) -> AbstractContextManager[MagicMock]:
    """Patch sidestage.server.App.get_actor to return `actor` (default: MagicMock).

    `create=True` because tests must not depend on App.get_actor's presence
    at import time.
    """
    if actor is None:
        actor = MagicMock()
    return patch("sidestage.server.App.get_actor", return_value=actor, create=True)


def make_character(
    campaign: Campaign,
    *,
    id: str,
    owner: Literal["user", "stub", "npc"] = "stub",
    name: str = "Char",
    body: str = "",
) -> Character:
    """Build a Character with App.get_actor patched, register it in `campaign`."""
    with _patch_get_actor():
        char = Character(
            Character.Model(
                id=EntityId(id),
                name=name,
                type=EntityType.CHARACTER,
                body=body,
                owner=owner,
            ),
            campaign,
        )
    campaign.add(char)
    return char


def make_simple_scene(
    *,
    scene_id: str = "scene-1",
    user_id: str = "user",
    npc_id: str = "npc",
    campaign: Campaign | None = None,
) -> SimpleScene:
    """Build a SimpleScene with two pre-registered characters in a fresh campaign."""
    if campaign is None:
        campaign = Campaign(name="t")
    if campaign.get(user_id) is None:
        make_character(campaign, id=user_id, owner="user", name="User")
    if campaign.get(npc_id) is None:
        make_character(campaign, id=npc_id, owner="stub", name="Npc")
    scene = SimpleScene(
        SimpleScene.Model(
            id=EntityId(scene_id),
            name="Test Scene",
            type=EntityType.SCENE,
            body="scene body",
            characters=[EntityId(user_id), EntityId(npc_id)],
        ),
        campaign,
    )
    campaign.add(scene)
    return scene


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

    def test_scene_messages_field_on_model(self) -> None:
        # scene-model: Scene.Model carries `messages: list[Message] = []`.
        assert "messages" in Scene.Model.model_fields

    def test_scene_messages_registered_as_entity_list(self) -> None:
        # entity-list-attribute: the `messages` field is registered in
        # `_entity_lists` so the Entity machinery wraps it at construction.
        assert "messages" in Scene._entity_lists


# ---------------------------------------------------------------------------
# scene.messages — the public mutation surface
# ---------------------------------------------------------------------------


class TestSceneMessagesAppend:
    """The single mutator: `scene.messages.append(msg)`. Records, emits a
    `ListDelta`, and is the same surface used by `Character.say`."""

    async def test_append_records_message(self) -> None:
        scene = make_simple_scene()
        m = Message(sender_id=scene._user.id, body="hello")
        scene.messages.append(m)
        assert list(scene.messages) == [m]

    async def test_append_noop_persistence_when_db_handle_none(self) -> None:
        # scene-message-persistence: against `DictEntityFactory`,
        # `campaign.db_handle is None` and `MessageList._on_add` skips
        # the XADD path. The message still lands in the in-memory list
        # and a ListDelta still fires — only durable persistence is
        # skipped.
        scene = make_simple_scene()
        assert scene._campaign.db_handle is None  # DictEntityFactory case
        scene.messages.append(Message(sender_id=scene._user.id, body="hi"))
        # No exception means MessageList._on_add gracefully no-op'd.
        assert [m.body for m in scene.messages] == ["hi"]

    async def test_append_records_in_order(self) -> None:
        scene = make_simple_scene()
        s = scene._user.id
        m0 = Message(sender_id=s, body="a")
        m1 = Message(sender_id=s, body="b")
        m2 = Message(sender_id=s, body="c")
        scene.messages.append(m0)
        scene.messages.append(m1)
        scene.messages.append(m2)
        assert list(scene.messages) == [m0, m1, m2]

    async def test_append_emits_entity_changed_to_subscribers(self) -> None:
        # entity-list-attribute: appending emits `EntityChanged` whose
        # `entity` is the scene, `attributes` contains "messages", and
        # `deltas["messages"]` is a `ListDelta(start=-1, len=0, items=[msg])`.
        scene = make_simple_scene()
        recorder = _Recorder()
        scene.subscribe(recorder)

        m = Message(sender_id=scene._user.id, body="hi")
        scene.messages.append(m)

        # _emit wraps each listener in a task (events-async-tasks); wait for
        # them to settle before asserting.
        await scene.idle()

        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert isinstance(event, EntityChanged)
        assert event.entity is scene
        assert "messages" in event.attributes
        delta = event.deltas["messages"]
        assert isinstance(delta, ListDelta)
        assert delta.start == -1
        assert delta.len == 0
        assert delta.items == [m]

    async def test_append_emits_once_per_call(self) -> None:
        scene = make_simple_scene()
        recorder = _Recorder()
        scene.subscribe(recorder)
        s = scene._user.id
        scene.messages.append(Message(sender_id=s, body="a"))
        scene.messages.append(Message(sender_id=s, body="b"))
        scene.messages.append(Message(sender_id=s, body="c"))
        await scene.idle()
        assert len(recorder.events) == 3
        for event in recorder.events:
            assert event.entity is scene
            assert "messages" in event.attributes


class TestSceneMessagesIsEntityList:
    """The `messages` field is replaced in place by an `EntityList` at
    construction (per `entity-list-attribute`)."""

    def test_messages_is_entity_list(self) -> None:
        scene = make_simple_scene()
        assert isinstance(scene.messages, EntityList)

    def test_messages_starts_empty(self) -> None:
        scene = make_simple_scene()
        assert list(scene.messages) == []

    async def test_messages_pop_emits_delta(self) -> None:
        # entity-list-attribute: pop emits a ListDelta with len=1, items=[].
        scene = make_simple_scene()
        recorder = _Recorder()
        s = scene._user.id
        scene.messages.append(Message(sender_id=s, body="a"))
        # Drain the append emit before subscribing the recorder so we only
        # see the pop event.
        await scene.idle()
        scene.subscribe(recorder)

        scene.messages.pop()
        await scene.idle()

        assert len(recorder.events) == 1
        delta = recorder.events[0].deltas["messages"]
        assert isinstance(delta, ListDelta)
        assert delta.len == 1
        assert delta.items == []


# ---------------------------------------------------------------------------
# Scene.Model
# ---------------------------------------------------------------------------


class TestSceneModel:
    def test_scene_model_exists(self) -> None:
        # scene-model: Scene.Model is an inner Pydantic model.
        assert hasattr(Scene, "Model")

    def test_scene_model_characters_is_list_of_entity_ids(self) -> None:
        # scene-model: `characters` is a list of `EntityId` references.
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            characters=[EntityId("c1"), EntityId("c2")],
        )
        assert model.characters == [EntityId("c1"), EntityId("c2")]

    def test_scene_model_field_is_named_characters(self) -> None:
        # scene-model: field is named `characters` (NOT `character_ids`).
        # The `EntityId` element type carries the "list of references"
        # semantics; the suffix is no longer needed on the field name.
        fields = Scene.Model.model_fields
        assert "characters" in fields
        assert "character_ids" not in fields

    def test_scene_characters_registered_as_entity_list(self) -> None:
        # entity-list-attribute: `characters` is auto-wrapped at
        # construction so mutations emit `ListDelta`.
        assert "characters" in Scene._entity_lists

    def test_scene_model_messages_defaults_empty(self) -> None:
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            characters=[EntityId("c1"), EntityId("c2")],
        )
        assert model.messages == []


# ---------------------------------------------------------------------------
# scene.characters — EntityList[EntityId] field with auto-ListDelta emission
# ---------------------------------------------------------------------------


class TestSceneCharactersAttribute:
    def test_characters_is_entity_list(self) -> None:
        # scene-model: `characters` is wrapped in an EntityList at
        # construction so append/remove emit ListDelta.
        scene = make_simple_scene()
        assert isinstance(scene.characters, EntityList)

    def test_characters_contains_ids_in_construction_order(self) -> None:
        scene = make_simple_scene(user_id="alpha", npc_id="beta")
        assert list(scene.characters) == [EntityId("alpha"), EntityId("beta")]

    async def test_characters_append_emits_list_delta(self) -> None:
        # Mutating `scene.characters` is observable over the WS, same
        # machinery as `scene.messages`.
        scene = make_simple_scene()
        recorder = _Recorder()
        scene.subscribe(recorder)

        scene.characters.append(EntityId("late-arrival"))
        await scene.idle()

        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert "characters" in event.attributes
        delta = event.deltas["characters"]
        assert isinstance(delta, ListDelta)
        assert delta.items == [EntityId("late-arrival")]


# ---------------------------------------------------------------------------
# SimpleScene constructor
# ---------------------------------------------------------------------------


class TestSimpleSceneInit:
    def _campaign_with_chars(
        self,
        *,
        user_human: bool = True,
        npc_human: bool = False,
        extra: bool = False,
    ) -> Campaign:
        campaign = Campaign(name="t")
        make_character(
            campaign,
            id="u",
            owner="user" if user_human else "stub",
            name="U",
        )
        make_character(
            campaign,
            id="n",
            owner="user" if npc_human else "stub",
            name="N",
        )
        if extra:
            make_character(campaign, id="x", owner="stub", name="X")
        return campaign

    def test_init_count_raises_when_too_few(self) -> None:
        # simple-scene-init-count: ValueError if len(characters) != 2.
        campaign = self._campaign_with_chars()
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    characters=[EntityId("u")],
                ),
                campaign,
            )

    def test_init_count_raises_when_too_many(self) -> None:
        # simple-scene-init-count: ValueError if len(characters) != 2.
        campaign = self._campaign_with_chars(extra=True)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    characters=[EntityId("u"), EntityId("n"), EntityId("x")],
                ),
                campaign,
            )

    def test_init_count_raises_when_empty(self) -> None:
        # simple-scene-init-count: ValueError if len(characters) != 2.
        campaign = self._campaign_with_chars()
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    characters=[],
                ),
                campaign,
            )

    def test_init_requires_one_user_one_npc(self) -> None:
        # simple-scene-init-roles: ValueError unless exactly one character
        # has has_human_actor()=True and one has False. Role identification
        # is by Character.owner, not list position — so two NPCs (or two
        # users) is invalid.
        campaign = self._campaign_with_chars(user_human=False, npc_human=False)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    characters=[EntityId("u"), EntityId("n")],
                ),
                campaign,
            )

    def test_init_rejects_two_users(self) -> None:
        # simple-scene-init-roles: two human-controlled characters is
        # invalid for SimpleScene.
        campaign = self._campaign_with_chars(user_human=True, npc_human=True)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    characters=[EntityId("u"), EntityId("n")],
                ),
                campaign,
            )

    def test_init_aliases_set_by_role(self) -> None:
        # simple-scene-init-roles: _user is the human-actor character,
        # _npc is the non-human one — regardless of list order.
        campaign = Campaign(name="t")
        user = make_character(campaign, id="the-user", owner="user", name="U")
        npc = make_character(campaign, id="the-npc", owner="stub", name="N")
        # Intentionally put npc first to verify role-based (not positional)
        # identification.
        scene = SimpleScene(
            SimpleScene.Model(
                id=EntityId("s"),
                name="x",
                type=EntityType.SCENE,
                body="b",
                characters=[EntityId("the-npc"), EntityId("the-user")],
            ),
            campaign,
        )
        campaign.add(scene)
        assert scene._user is user
        assert scene._npc is npc

    def test_init_subscribes_every_character(self) -> None:
        # simple-scene-init-subscribes-characters: every character in
        # `characters` ends up in scene._listeners after construction.
        scene = make_simple_scene()
        assert scene._user in scene._listeners
        assert scene._npc in scene._listeners

    def test_init_subscribes_characters_only(self) -> None:
        # simple-scene-init-subscribes-characters: no extra unrelated listeners
        # are added.
        scene = make_simple_scene()
        assert len(scene._listeners) == 2

    def test_init_messages_starts_empty(self) -> None:
        # The auto-wrapped MessageList[Message] starts empty.
        scene = make_simple_scene()
        assert list(scene.messages) == []
        assert isinstance(scene.messages, EntityList)


# ---------------------------------------------------------------------------
# Scene.model — the canonical wire shape
# ---------------------------------------------------------------------------


class TestSceneModelAccessor:
    def test_model_is_scene_model(self) -> None:
        # scene-model: scene.model returns a Scene.Model with id, name, and
        # characters populated.
        scene = make_simple_scene(scene_id="scn-7", user_id="user-1", npc_id="npc-1")
        # make_simple_scene sets name="Test Scene".
        resp = scene.model
        assert isinstance(resp, Scene.Model)
        assert resp.id == EntityId("scn-7")
        assert resp.name == "Test Scene"
        assert list(resp.characters) == [EntityId("user-1"), EntityId("npc-1")]

    def test_model_characters_includes_all_ids(self) -> None:
        # scene-model: `characters` carries every character's id, in
        # construction order.
        scene = make_simple_scene(user_id="u", npc_id="n")
        resp = scene.model
        assert list(resp.characters) == [EntityId("u"), EntityId("n")]
