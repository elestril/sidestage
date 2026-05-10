from __future__ import annotations

from unittest.mock import MagicMock
from sidestage.message import Message


class TestMessage:
    def test_message_has_sender_and_body(self):
        sender = MagicMock()
        msg = Message(sender=sender, body="Hello")
        assert msg.sender is sender
        assert msg.body == "Hello"

    def test_message_body_str(self):
        sender = MagicMock()
        msg = Message(sender=sender, body="test body")
        assert isinstance(msg.body, str)
