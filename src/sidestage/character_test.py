from __future__ import annotations

from unittest.mock import MagicMock
from sidestage.character import Character
from sidestage.actor import StubActor
from sidestage.entity import EntityId, EntityType
from sidestage.message import Message


def make_character(id: str = "c1", name: str = "Alice", actor_type: str = "npc") -> Character:
    model = Character.Model(
        id=EntityId(id),
        name=name,
        type=EntityType.CHARACTER,
        body="a body",
        actor_type=actor_type,
    )
    char = Character.deserialize(model)
    char._actor = StubActor()
    return char


class TestCharacter:
    def test_character_is_entity(self):
        from sidestage.entity import Entity
        char = make_character()
        assert isinstance(char, Entity)

    def test_has_human_actor_false_for_stub(self):
        char = make_character()
        char._actor = StubActor()
        assert char.has_human_actor() is False

    def test_has_human_actor_true_for_human(self):
        char = make_character()
        human_actor = MagicMock()
        human_actor.is_human.return_value = True
        char._actor = human_actor
        assert char.has_human_actor() is True

    def test_respond_passthrough(self):
        char = make_character()
        mock_actor = MagicMock()
        mock_actor.respond.return_value = None
        char._actor = mock_actor
        sender = MagicMock()
        msg = Message(sender=sender, body="hi")
        result = char.respond(msg)
        mock_actor.respond.assert_called_once_with(msg, char)
        assert result is None

    def test_respond_returns_message(self):
        char = make_character()
        mock_actor = MagicMock()
        expected = Message(sender=char, body="response")
        mock_actor.respond.return_value = expected
        char._actor = mock_actor
        sender = MagicMock()
        msg = Message(sender=sender, body="hi")
        result = char.respond(msg)
        assert result is expected

    def test_model_has_actor_type(self):
        char = make_character(actor_type="user")
        assert char.actor_type == "user"

    def test_serialize_deserialize_roundtrip(self):
        char = make_character(id="c2", name="Bob", actor_type="user")
        model = char.serialize()
        assert model.id == "c2"
        assert model.name == "Bob"
        assert model.actor_type == "user"
        char2 = Character.deserialize(model)
        assert char2.id == "c2"
        assert char2.name == "Bob"
        assert char2.actor_type == "user"
