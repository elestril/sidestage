from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.actor import SceneUpdatedEvent
from sidestage.character import Character
from sidestage.entity import Entity, EntityId, EntityType
from sidestage.message import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_get_actor(actor: object | None = None):
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
    owner: str = "npc",
    actor: object | None = None,
) -> Character:
    """Construct a Character with App.get_actor patched to return `actor`."""
    with _patch_get_actor(actor):
        return Character(
            id=EntityId(id),
            name=name,
            body=body,
            owner=owner,
        )


# ---------------------------------------------------------------------------
# character-class: Character is an Entity
# ---------------------------------------------------------------------------


class TestCharacterClass:
    """character-class: Character(Entity)."""

    def test_character_is_entity(self):
        char = make_character()
        assert isinstance(char, Entity)


# ---------------------------------------------------------------------------
# character-init-stores-owner
# ---------------------------------------------------------------------------


class TestCharacterInitStoresOwner:
    """character-init-stores-owner: Stores owner as an attribute."""

    def test_stores_owner_user(self):
        char = make_character(owner="user")
        assert char.owner == "user"

    def test_stores_owner_npc(self):
        char = make_character(owner="npc")
        assert char.owner == "npc"

    def test_stores_owner_stub(self):
        char = make_character(owner="stub")
        assert char.owner == "stub"

    def test_stores_other_init_fields(self):
        char = make_character(id="c42", name="Bob", body="some body", owner="user")
        assert char.id == "c42"
        assert char.name == "Bob"
        assert char.body == "some body"
        assert char.type == EntityType.CHARACTER

    def test_loaded_true_after_init(self):
        # The Entity ghost guard must allow free attribute access — i.e. the
        # newly-constructed Character is a real (non-ghost) entity.
        char = make_character(owner="npc")
        # If _loaded were False this would raise UnresolvedEntityError.
        assert char.name == "Alice"


# ---------------------------------------------------------------------------
# character-init-binds-actor
# ---------------------------------------------------------------------------


class TestCharacterInitBindsActor:
    """character-init-binds-actor: Calls App.get_actor(self.owner) and stores
    the returned Actor as self._actor."""

    def test_get_actor_called_with_owner(self):
        sentinel_actor = MagicMock(name="actor")
        with _patch_get_actor(sentinel_actor) as mock_get_actor:
            Character(
                id=EntityId("c1"),
                name="Alice",
                body="body",
                owner="npc",
            )
        mock_get_actor.assert_called_once_with("npc")

    def test_stores_returned_actor_as_underscore_actor(self):
        sentinel_actor = MagicMock(name="actor")
        char = make_character(owner="user", actor=sentinel_actor)
        assert char._actor is sentinel_actor

    def test_get_actor_called_with_user_owner(self):
        with _patch_get_actor() as mock_get_actor:
            Character(
                id=EntityId("c1"),
                name="Alice",
                body="body",
                owner="user",
            )
        mock_get_actor.assert_called_once_with("user")

    def test_get_actor_called_with_stub_owner(self):
        with _patch_get_actor() as mock_get_actor:
            Character(
                id=EntityId("c1"),
                name="Alice",
                body="body",
                owner="stub",
            )
        mock_get_actor.assert_called_once_with("stub")


# ---------------------------------------------------------------------------
# character-respond-passthrough  (async)
# ---------------------------------------------------------------------------


class TestCharacterRespondPassthrough:
    """character-respond-passthrough: Pure pass-through —
    `await self._actor.respond(message, self)`."""

    async def test_respond_delegates_to_actor_with_self(self):
        actor = MagicMock()
        actor.respond = AsyncMock(return_value=None)
        char = make_character(actor=actor)

        sender = MagicMock()
        msg = Message(sender=sender, body="hi")

        result = await char.respond(msg)

        actor.respond.assert_awaited_once_with(msg, char)
        assert result is None

    async def test_respond_returns_actor_result(self):
        actor = MagicMock()
        char = make_character(actor=actor)
        expected = Message(sender=char, body="response")
        actor.respond = AsyncMock(return_value=expected)

        sender = MagicMock()
        msg = Message(sender=sender, body="hi")

        result = await char.respond(msg)

        assert result is expected

    async def test_respond_is_a_coroutine(self):
        # Sanity: Character.respond must be an async function.
        import inspect

        assert inspect.iscoroutinefunction(Character.respond)


# ---------------------------------------------------------------------------
# character-notify-passthrough
# ---------------------------------------------------------------------------


class TestCharacterNotifyPassthrough:
    """character-notify-passthrough: Pure pass-through to
    self._actor.notify(event)."""

    def test_notify_delegates_to_actor(self):
        actor = MagicMock()
        actor.notify.return_value = None
        char = make_character(actor=actor)

        event = SceneUpdatedEvent(
            scene_id=EntityId("s1"),
            latest_message_index=7,
        )

        result = char.notify(event)

        actor.notify.assert_called_once_with(event)
        assert result is None

    def test_notify_passes_same_event_instance(self):
        # The same event object must be forwarded — no copying / wrapping.
        actor = MagicMock()
        char = make_character(actor=actor)

        event = SceneUpdatedEvent(
            scene_id=EntityId("s2"),
            latest_message_index=3,
        )

        char.notify(event)

        forwarded = actor.notify.call_args.args[0]
        assert forwarded is event

    def test_notify_accepts_arbitrary_event_object(self):
        # Pure pass-through — Character does not introspect the event.
        actor = MagicMock()
        char = make_character(actor=actor)

        event = MagicMock(name="event")

        char.notify(event)

        actor.notify.assert_called_once_with(event)

    def test_notify_forwards_each_call(self):
        actor = MagicMock()
        char = make_character(actor=actor)

        e1 = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=0)
        e2 = SceneUpdatedEvent(scene_id=EntityId("s"), latest_message_index=42)

        char.notify(e1)
        char.notify(e2)

        assert actor.notify.call_args_list[0].args == (e1,)
        assert actor.notify.call_args_list[1].args == (e2,)


# ---------------------------------------------------------------------------
# character-has-human-actor
# ---------------------------------------------------------------------------


class TestCharacterHasHumanActor:
    """character-has-human-actor: Returns self.owner == "user". Checks the
    persistent role, NOT the live actor."""

    def test_returns_true_when_owner_is_user(self):
        char = make_character(owner="user")
        assert char.has_human_actor() is True

    def test_returns_false_when_owner_is_npc(self):
        char = make_character(owner="npc")
        assert char.has_human_actor() is False

    def test_returns_false_when_owner_is_stub(self):
        char = make_character(owner="stub")
        assert char.has_human_actor() is False

    def test_does_not_query_actor(self):
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

    def test_model_accepts_user(self):
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="user",
        )
        assert m.owner == "user"

    def test_model_accepts_npc(self):
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="npc",
        )
        assert m.owner == "npc"

    def test_model_accepts_stub(self):
        m = Character.Model(
            id=EntityId("c1"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="body",
            owner="stub",
        )
        assert m.owner == "stub"

    def test_model_rejects_unknown_owner(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Character.Model(
                id=EntityId("c1"),
                name="Alice",
                type=EntityType.CHARACTER,
                body="body",
                owner="alien",
            )

    def test_model_has_no_actor_type_field(self):
        # The obsolete `actor_type` field has been removed.
        assert "actor_type" not in Character.Model.model_fields

    def test_model_has_no_model_field(self):
        # The obsolete `model: str | None` field has been removed.
        assert "model" not in Character.Model.model_fields

    def test_model_owner_field_present(self):
        assert "owner" in Character.Model.model_fields


# ---------------------------------------------------------------------------
# Character.deserialize — constructs via __init__ with owner from model.
# ---------------------------------------------------------------------------


class TestCharacterDeserialize:
    """Character.deserialize(model) constructs
    Character(id=..., name=..., body=..., owner=model.owner)."""

    def test_deserialize_builds_character_with_owner(self):
        model = Character.Model(
            id=EntityId("c2"),
            name="Bob",
            type=EntityType.CHARACTER,
            body="bob body",
            owner="user",
        )
        with _patch_get_actor():
            char = Character.deserialize(model)

        assert char.id == "c2"
        assert char.name == "Bob"
        assert char.body == "bob body"
        assert char.owner == "user"
        assert char.type == EntityType.CHARACTER

    def test_deserialize_invokes_get_actor(self):
        model = Character.Model(
            id=EntityId("c3"),
            name="Carol",
            type=EntityType.CHARACTER,
            body="carol body",
            owner="npc",
        )
        sentinel = MagicMock(name="actor")
        with _patch_get_actor(sentinel) as mock_get_actor:
            char = Character.deserialize(model)

        mock_get_actor.assert_called_once_with("npc")
        assert char._actor is sentinel

    def test_serialize_roundtrip(self):
        with _patch_get_actor():
            char = Character(
                id=EntityId("c4"),
                name="Dave",
                body="dave body",
                owner="user",
            )
        model = char.serialize()
        assert model.id == "c4"
        assert model.name == "Dave"
        assert model.body == "dave body"
        assert model.owner == "user"

        with _patch_get_actor():
            char2 = Character.deserialize(model)
        assert char2.id == "c4"
        assert char2.name == "Dave"
        assert char2.body == "dave body"
        assert char2.owner == "user"
