from __future__ import annotations

from unittest.mock import MagicMock
from sidestage.actor import StubActor
from sidestage.message import Message


def make_character(is_human: bool) -> MagicMock:
    char = MagicMock()
    char.has_human_actor.return_value = is_human
    return char


class TestStubActor:
    def test_is_human_returns_false(self):
        actor = StubActor()
        assert actor.is_human() is False

    def test_respond_ignores_non_human_sender(self):
        actor = StubActor()
        sender = make_character(is_human=False)
        character = make_character(is_human=False)
        msg = Message(sender=sender, body="Hi")
        result = actor.respond(msg, character)
        assert result is None

    def test_respond_returns_hello_for_human_sender(self):
        actor = StubActor()
        sender = make_character(is_human=True)
        character = MagicMock()
        msg = Message(sender=sender, body="Hi")
        result = actor.respond(msg, character)
        assert result is not None
        assert result.sender is character
        assert result.body == "Hello User!"

    def test_stub_actor_implements_actor(self):
        from sidestage.actor import Actor
        assert isinstance(StubActor(), Actor)
