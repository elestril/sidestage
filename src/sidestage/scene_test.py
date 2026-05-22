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
            character_ids=[EntityId(user_id), EntityId(npc_id)],
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

    def test_scene_model_has_character_ids_field_of_entity_ids(self) -> None:
        # scene-model: character_ids is `list[EntityId]`.
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            character_ids=[EntityId("c1"), EntityId("c2")],
        )
        assert model.character_ids == [EntityId("c1"), EntityId("c2")]

    def test_scene_model_field_is_named_character_ids(self) -> None:
        # scene-model: field is named `character_ids` (NOT `characters` or
        # `active_character_ids`).
        fields = Scene.Model.model_fields
        assert "character_ids" in fields
        assert "characters" not in fields
        assert "active_character_ids" not in fields

    def test_scene_model_messages_defaults_empty(self) -> None:
        model = Scene.Model(
            id=EntityId("s"),
            name="n",
            type=EntityType.SCENE,
            body="b",
            character_ids=[EntityId("c1"), EntityId("c2")],
        )
        assert model.messages == []


# ---------------------------------------------------------------------------
# Scene.characters property (resolves character_ids via campaign)
# ---------------------------------------------------------------------------


class TestSceneCharactersProperty:
    def test_characters_resolves_ids_via_campaign(self) -> None:
        # scene-characters: each id in model.character_ids is resolved via
        # campaign.get(id) to a Character.
        campaign = Campaign(name="t")
        user = make_character(campaign, id="c1", owner="user", name="U")
        npc = make_character(campaign, id="c2", owner="stub", name="N")
        scene = SimpleScene(
            SimpleScene.Model(
                id=EntityId("s"),
                name="n",
                type=EntityType.SCENE,
                body="b",
                character_ids=[EntityId("c1"), EntityId("c2")],
            ),
            campaign,
        )
        campaign.add(scene)
        assert scene.characters == [user, npc]

    def test_characters_preserves_order(self) -> None:
        # scene-characters: order follows model.character_ids order.
        campaign = Campaign(name="t")
        a = make_character(campaign, id="alpha", owner="user", name="A")
        b = make_character(campaign, id="beta", owner="stub", name="B")
        scene = SimpleScene(
            SimpleScene.Model(
                id=EntityId("scn"),
                name="My Scene",
                type=EntityType.SCENE,
                body="The body",
                character_ids=[EntityId("alpha"), EntityId("beta")],
            ),
            campaign,
        )
        campaign.add(scene)
        assert scene.characters == [a, b]

    def test_characters_is_property(self) -> None:
        # scene-characters: declared as a property on Scene.
        attr = Scene.__dict__.get("characters")
        assert isinstance(attr, property)


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

    def test_init_messages_starts_empty(self) -> None:
        # The auto-wrapped EntityList[Message] starts empty.
        scene = make_simple_scene()
        assert list(scene.messages) == []
        assert isinstance(scene.messages, EntityList)

    def test_init_count_raises_when_too_few(self) -> None:
        # simple-scene-init-count: ValueError if len(character_ids) != 2.
        campaign = self._campaign_with_chars()
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    character_ids=[EntityId("u")],
                ),
                campaign,
            )

    def test_init_count_raises_when_too_many(self) -> None:
        # simple-scene-init-count: ValueError if len(character_ids) != 2.
        campaign = self._campaign_with_chars(extra=True)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    character_ids=[EntityId("u"), EntityId("n"), EntityId("x")],
                ),
                campaign,
            )

    def test_init_count_raises_when_empty(self) -> None:
        # simple-scene-init-count: ValueError if len(character_ids) != 2.
        campaign = self._campaign_with_chars()
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    character_ids=[],
                ),
                campaign,
            )

    def test_init_user_must_be_human(self) -> None:
        # simple-scene-init-user: ValueError if characters[0].has_human_actor()
        # is False.
        campaign = self._campaign_with_chars(user_human=False, npc_human=False)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    character_ids=[EntityId("u"), EntityId("n")],
                ),
                campaign,
            )

    def test_init_npc_must_not_be_human(self) -> None:
        # simple-scene-init-npc: ValueError if characters[1].has_human_actor()
        # is True.
        campaign = self._campaign_with_chars(user_human=True, npc_human=True)
        with pytest.raises(ValueError):
            SimpleScene(
                SimpleScene.Model(
                    id=EntityId("s"),
                    name="x",
                    type=EntityType.SCENE,
                    body="b",
                    character_ids=[EntityId("u"), EntityId("n")],
                ),
                campaign,
            )

    def test_init_aliases_set(self) -> None:
        # simple-scene-init-aliases: _user = characters[0], _npc = characters[1].
        campaign = Campaign(name="t")
        user = make_character(campaign, id="the-user", owner="user", name="U")
        npc = make_character(campaign, id="the-npc", owner="stub", name="N")
        scene = SimpleScene(
            SimpleScene.Model(
                id=EntityId("s"),
                name="x",
                type=EntityType.SCENE,
                body="b",
                character_ids=[EntityId("the-user"), EntityId("the-npc")],
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


# ---------------------------------------------------------------------------
# Scene.user_characters
# ---------------------------------------------------------------------------


class TestSceneUserCharacters:
    def test_user_characters_returns_only_human_actors(self) -> None:
        # scene-user-characters: subset of `characters` with has_human_actor()
        # True.
        scene = make_simple_scene()
        assert scene.user_characters == [scene._user]

    def test_user_characters_preserves_scene_order(self) -> None:
        # scene-user-characters: order follows `characters` order — filter only.
        scene = make_simple_scene()
        assert scene.user_characters == [
            c for c in scene.characters if c.has_human_actor()
        ]

    def test_user_characters_is_property(self) -> None:
        # scene-user-characters: declared as a property on Scene.
        attr = Scene.__dict__.get("user_characters")
        assert isinstance(attr, property)


# ---------------------------------------------------------------------------
# Scene.model — the canonical wire shape
# ---------------------------------------------------------------------------


class TestSceneModelAccessor:
    def test_model_is_scene_model(self) -> None:
        # scene-model: scene.model returns a Scene.Model with id, name, and
        # character_ids populated correctly.
        scene = make_simple_scene(scene_id="scn-7", user_id="user-1", npc_id="npc-1")
        # make_simple_scene sets name="Test Scene".
        resp = scene.model
        assert isinstance(resp, Scene.Model)
        assert resp.id == EntityId("scn-7")
        assert resp.name == "Test Scene"
        assert resp.character_ids == [EntityId("user-1"), EntityId("npc-1")]

    def test_user_characters_excludes_npcs(self) -> None:
        # scene-user-characters: only includes characters with has_human_actor().
        # Scene.Model carries only character_ids; the user subset is exposed
        # via the `user_characters` property.
        scene = make_simple_scene(user_id="u", npc_id="n")
        user_ids = [c.id for c in scene.user_characters]
        assert EntityId("u") in user_ids
        assert EntityId("n") not in user_ids

    def test_model_character_ids_includes_all_characters(self) -> None:
        # scene-model: character_ids has every character's id, in order.
        scene = make_simple_scene(user_id="u", npc_id="n")
        resp = scene.model
        assert resp.character_ids == [EntityId("u"), EntityId("n")]
