from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.entity import (
    Entity,
    EntityId,
    EntityType,
    MessageContext,
)
from sidestage.events import EntityChanged
from sidestage.message import Message
from sidestage.scene import Scene

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_get_actor(actor: object | None = None) -> AbstractContextManager[MagicMock]:
    """Patch sidestage.server.App.get_actor to return `actor` (default: MagicMock).

    `create=True` because App.get_actor is added by a parallel agent; tests
    must not depend on its presence at import time.
    """
    if actor is None:
        actor = MagicMock()
    return patch("sidestage.server.App.get_actor", return_value=actor, create=True)


def make_character(
    *,
    id: str = "c1",
    name: str = "Alice",
    body: str = "a body",
    owner: Literal["user", "stub", "npc"] = "stub",
    actor: object | None = None,
    campaign: Campaign | None = None,
) -> Character:
    """Construct a Character with App.get_actor patched to return `actor`.

    `campaign` defaults to a fresh in-memory `Campaign` — tests that don't
    exercise cross-entity recursion don't need to think about it.
    """
    if campaign is None:
        campaign = Campaign(name="t")
    model = Character.Model(
        id=EntityId(id),
        name=name,
        type=EntityType.CHARACTER,
        body=body,
        owner=owner,
    )
    with _patch_get_actor(actor):
        return Character(model, campaign)


# ---------------------------------------------------------------------------
# character-class: Character is an Entity
# ---------------------------------------------------------------------------


class TestCharacterClass:
    """character-class: Character(Entity)."""

    def test_character_is_entity(self) -> None:
        char = make_character()
        assert isinstance(char, Entity)


# ---------------------------------------------------------------------------
# character-init-stores-owner
# ---------------------------------------------------------------------------


class TestCharacterInitStoresOwner:
    """character-init-stores-owner: Stores owner as an attribute."""

    def test_stores_owner_user(self) -> None:
        char = make_character(owner="user")
        assert char.owner == "user"

    def test_stores_owner_npc(self) -> None:
        char = make_character(owner="npc")
        assert char.owner == "npc"

    def test_stores_owner_stub(self) -> None:
        char = make_character(owner="stub")
        assert char.owner == "stub"

    def test_stores_other_init_fields(self) -> None:
        char = make_character(id="c42", name="Bob", body="some body", owner="user")
        assert char.id == "c42"
        assert char.name == "Bob"
        assert char.body == "some body"
        assert char.type == EntityType.CHARACTER

    def test_loaded_true_after_init(self) -> None:
        # The Entity ghost guard must allow free attribute access — i.e. the
        # newly-constructed Character is a real (non-ghost) entity.
        char = make_character(owner="stub")
        # If _loaded were False this would raise UnresolvedEntityError.
        assert char.name == "Alice"


# ---------------------------------------------------------------------------
# character-init-binds-actor
# ---------------------------------------------------------------------------


def _build_model(
    *,
    id: str = "c1",
    name: str = "Alice",
    body: str = "body",
    owner: Literal["user", "stub", "npc"] = "stub",
) -> Character.Model:
    return Character.Model(
        id=EntityId(id),
        name=name,
        type=EntityType.CHARACTER,
        body=body,
        owner=owner,
    )


class TestCharacterInitBindsActor:
    """character-init-binds-actor: Calls App.get_actor(self.owner) and stores
    the returned Actor as self._actor."""

    def test_get_actor_called_with_owner(self) -> None:
        sentinel_actor = MagicMock(name="actor")
        with _patch_get_actor(sentinel_actor) as mock_get_actor:
            Character(_build_model(owner="stub"), Campaign(name="t"))
        mock_get_actor.assert_called_once_with("stub")

    def test_stores_returned_actor_as_underscore_actor(self) -> None:
        sentinel_actor = MagicMock(name="actor")
        char = make_character(owner="user", actor=sentinel_actor)
        assert char._actor is sentinel_actor

    def test_get_actor_called_with_user_owner(self) -> None:
        with _patch_get_actor() as mock_get_actor:
            Character(_build_model(owner="user"), Campaign(name="t"))
        mock_get_actor.assert_called_once_with("user")

    def test_get_actor_called_with_stub_owner(self) -> None:
        with _patch_get_actor() as mock_get_actor:
            Character(_build_model(owner="stub"), Campaign(name="t"))
        mock_get_actor.assert_called_once_with("stub")


# ---------------------------------------------------------------------------
# character-say: the @action that publishes a Message into a Scene.
# ---------------------------------------------------------------------------


class TestCharacterSay:
    """character-say: Append `Message(sender_id=self.id, body=body)` to
    `scene_id`'s messages. Single mutator for character-produced output —
    used by both the FE-issued EntityAction path and the in-process NPC
    response path."""

    async def test_say_appends_message_to_scene(self) -> None:
        campaign = Campaign(name="t")
        char = make_character(id="alice", campaign=campaign)
        campaign.add(char)

        scene = MagicMock(spec=Scene)
        scene.id = EntityId("s1")
        scene.messages = MagicMock()
        scene.messages.append = MagicMock()
        # Register the scene mock with the campaign so `_campaign.get(scene_id)`
        # returns it.
        campaign.add(scene)

        await char.say(EntityId("s1"), "hello world")

        scene.messages.append.assert_called_once()
        appended: Message = scene.messages.append.call_args.args[0]
        assert isinstance(appended, Message)
        assert appended.sender_id == EntityId("alice")
        assert appended.body == "hello world"

    async def test_say_raises_on_unknown_scene_id(self) -> None:
        char = make_character(id="alice")
        with pytest.raises(ValueError, match="unknown scene_id"):
            await char.say(EntityId("nope"), "hi")

    def test_say_is_registered_as_action(self) -> None:
        # backend-action-class-level: `@action`-decorated methods register
        # in the class-level `_actions` set so the WS entity_action
        # dispatcher can validate the call.
        assert "say" in Character._actions, (
            "backend-action-class-level: `Character.say` is decorated with "
            f"`@action` and MUST appear in Character._actions; got {Character._actions!r}"
        )

    def test_say_is_coroutine(self) -> None:
        import inspect

        assert inspect.iscoroutinefunction(Character.say)


# ---------------------------------------------------------------------------
# character-notify-react  (async)
# ---------------------------------------------------------------------------


def _make_scene_event(
    *,
    messages: list[Message],
    attributes: list[str] | None = None,
    scene_id: str = "s1",
) -> tuple[EntityChanged, MagicMock]:
    """Build an EntityChanged whose `entity` is a Scene-spec MagicMock with
    the given `messages`. Returns (event, scene_mock).
    """
    scene = MagicMock(spec=Scene)
    scene.id = EntityId(scene_id)
    scene.messages = messages
    event = EntityChanged(
        entity=scene,
        attributes=["messages"] if attributes is None else attributes,
    )
    return event, scene


class TestCharacterNotifyReact:
    """character-notify-react: filter on Scene + "messages" attribute + sender
    not self; on pass, await actor.respond(latest, self, scene) and publish
    any non-None response via `self.say`."""

    async def test_notify_filters_non_scene_emitter(self) -> None:
        # event.entity is a non-Scene Entity → no actor.respond
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        non_scene = MagicMock(spec=Entity)
        event = EntityChanged(entity=non_scene, attributes=["messages"])

        await char.notify(event)

        actor.respond.assert_not_called()

    async def test_notify_filters_non_messages_attribute(self) -> None:
        # attributes = ["body"] → no actor.respond
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        msg = Message(sender_id=EntityId("other"), body="hi")
        event, _scene = _make_scene_event(messages=[msg], attributes=["body"])

        await char.notify(event)

        actor.respond.assert_not_called()

    async def test_notify_filters_own_message(self) -> None:
        # Latest message's sender_id IS this character → no actor.respond
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        own_msg = Message(sender_id=char.id, body="my own words")
        event, _scene = _make_scene_event(messages=[own_msg])

        await char.notify(event)

        actor.respond.assert_not_called()

    async def test_notify_calls_actor_respond_with_latest(self) -> None:
        # Happy path: await actor.respond(latest, self, event.entity) is invoked
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        older = Message(sender_id=EntityId("other"), body="older")
        latest = Message(sender_id=EntityId("other"), body="latest")
        event, scene = _make_scene_event(messages=[older, latest])

        await char.notify(event)

        actor.respond.assert_awaited_once_with(latest, char, scene)

    async def test_notify_publishes_non_none_response_via_say(self) -> None:
        # Actor returns text → char.say(scene.id, text) is called
        actor = MagicMock()
        actor.respond = AsyncMock(return_value="my reply")
        char = make_character(actor=actor)

        latest = Message(sender_id=EntityId("other"), body="provoke")
        event, scene = _make_scene_event(messages=[latest], scene_id="s9")

        # Spy on char.say so we don't need a full Campaign-resolvable Scene.
        say_mock = AsyncMock()
        object.__setattr__(char, "say", say_mock)

        await char.notify(event)

        say_mock.assert_awaited_once_with(scene.id, "my reply")

    async def test_notify_skips_say_when_response_none(self) -> None:
        # Actor returns None → no `say` call
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        latest = Message(sender_id=EntityId("other"), body="provoke")
        event, scene = _make_scene_event(messages=[latest])

        say_mock = AsyncMock()
        object.__setattr__(char, "say", say_mock)

        await char.notify(event)

        actor.respond.assert_awaited_once_with(latest, char, scene)
        say_mock.assert_not_called()


# ---------------------------------------------------------------------------
# character-has-human-actor
# ---------------------------------------------------------------------------


class TestCharacterHasHumanActor:
    """character-has-human-actor: Returns self.owner == "user". Checks the
    persistent role, NOT the live actor."""

    def test_returns_true_when_owner_is_user(self) -> None:
        char = make_character(owner="user")
        assert char.has_human_actor() is True

    def test_returns_false_when_owner_is_npc(self) -> None:
        char = make_character(owner="npc")
        assert char.has_human_actor() is False

    def test_returns_false_when_owner_is_stub(self) -> None:
        char = make_character(owner="stub")
        assert char.has_human_actor() is False

    def test_does_not_query_actor(self) -> None:
        # The check is on the persistent owner field; it must NOT consult the
        # actor's is_human() method.
        actor = MagicMock()
        actor.is_human = MagicMock(side_effect=AssertionError("must not be called"))
        char = make_character(owner="user", actor=actor)

        assert char.has_human_actor() is True
        actor.is_human.assert_not_called()


# ---------------------------------------------------------------------------
# character-model: Character.Model shape
# ---------------------------------------------------------------------------


class TestCharacterModel:
    """character-model: Inner Pydantic Model with `owner` Literal field."""

    def test_model_accepts_user(self) -> None:
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="user",
        )
        assert m.owner == "user"

    def test_model_accepts_npc(self) -> None:
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="npc",
        )
        assert m.owner == "npc"

    def test_model_accepts_stub(self) -> None:
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="stub",
        )
        assert m.owner == "stub"

    def test_model_rejects_unknown_owner(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Character.Model(
                id=EntityId("c1"),
                name="Alice",
                type=EntityType.CHARACTER,
                body="body",
                owner="alien",  # type: ignore[arg-type]
            )

    def test_model_has_no_actor_type_field(self) -> None:
        # The obsolete `actor_type` field has been removed.
        assert "actor_type" not in Character.Model.model_fields

    def test_model_has_no_model_field(self) -> None:
        # The obsolete `model: str | None` field has been removed.
        assert "model" not in Character.Model.model_fields

    def test_model_owner_field_present(self) -> None:
        assert "owner" in Character.Model.model_fields


# ---------------------------------------------------------------------------
# character-campaign-ref + character-annotate-context
# ---------------------------------------------------------------------------


class TestCharacterCampaignRef:
    """character-campaign-ref: Character stores the campaign passed at construction."""

    def test_init_stores_campaign(self) -> None:
        campaign = Campaign(name="t")
        char = make_character(campaign=campaign)
        assert char._campaign is campaign, (
            "character-campaign-ref: __init__ MUST store the campaign arg as "
            f"self._campaign; got {char._campaign!r}"
        )


class TestCharacterAnnotateContext:
    """character-annotate-context: super (writes self.body) + recurse into
    `ctx.scene` (which the actor populates from event.entity)."""

    def test_writes_own_body(self) -> None:
        # character-annotate-context: super().annotate_context(ctx) is called,
        # which writes self.body keyed by self.
        scene_mock = MagicMock(spec=Entity)
        scene_mock.id = EntityId("scene-x")
        # Mock annotate_context as a no-op so the test isolates Character's
        # own contribution.
        scene_mock.annotate_context = MagicMock(return_value=None)

        char = make_character(body="character body")
        msg = Message(sender_id=EntityId("sender"), body="trigger")
        ctx = MessageContext(message=msg, scene=scene_mock)

        char.annotate_context(ctx)

        assert char in ctx.annotations, (
            "character-annotate-context: super().annotate_context MUST write "
            f"self.body keyed by self; got annotations={ctx.annotations!r}"
        )
        assert ctx.annotations[char] == "character body"

    def test_recurses_into_ctx_scene(self) -> None:
        # character-annotate-context: after super, recurses with
        # ctx.scene.annotate_context(ctx).
        scene_mock = MagicMock(spec=Entity)
        scene_mock.id = EntityId("scene-x")
        scene_mock.annotate_context = MagicMock(return_value=None)

        char = make_character()
        msg = Message(sender_id=EntityId("sender"), body="trigger")
        ctx = MessageContext(message=msg, scene=scene_mock)

        char.annotate_context(ctx)

        scene_mock.annotate_context.assert_called_once_with(ctx)
