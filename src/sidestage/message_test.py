from __future__ import annotations

from dataclasses import fields
from typing import get_type_hints
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from sidestage.entity import EntityId
from sidestage.message import Message


class TestMessage:
    def test_message_class_has_only_sender_and_body(self) -> None:
        # message-class: Message has fields `sender: Character` and `body: str` only.
        # No `id` field — position in scene.messages IS the id.
        field_names = {f.name for f in fields(Message)}
        assert field_names == {"sender", "body"}, (
            "message-class-fields: Message has exactly two fields, "
            f"sender and body; got {field_names!r}"
        )

    def test_message_class_no_id_attribute_on_instances(self) -> None:
        # message-class (negative): instances must not carry an `id` attribute.
        sender = MagicMock()
        msg = Message(sender=sender, body="Hello")
        assert not hasattr(msg, "id"), (
            "message-class-fields: Message instances MUST NOT carry an "
            "`id` attribute; identity is the position in scene.messages"
        )

    def test_message_has_no_serialize_method(self) -> None:
        # message-class-no-serialize: serialization moved to Scene.serialize_message,
        # so Message no longer carries a `serialize` method.
        sender = MagicMock()
        msg = Message(sender=sender, body="Hello")
        assert not hasattr(msg, "serialize"), (
            "message-class-no-serialize: Message carries no `serialize` method; "
            "wire serialization lives on Scene.serialize_message"
        )

    def test_message_constructor_assigns_fields(self) -> None:
        # message-class: constructor assigns sender and body.
        sender = MagicMock()
        msg = Message(sender=sender, body="hi there")
        assert msg.sender is sender
        assert msg.body == "hi there"


class TestMessageModel:
    def test_model_fields(self) -> None:
        # message-model-fields: Message.Model has scene_id, index, sender_id, body.
        hints = get_type_hints(Message.Model)
        assert set(hints.keys()) == {"scene_id", "index", "sender_id", "body"}, (
            "message-model-fields: Message.Model has exactly four fields "
            "(scene_id, index, sender_id, body); "
            f"got {set(hints.keys())!r}"
        )

    def test_model_constructs_with_correct_types(self) -> None:
        # message-model: constructing the wire model with proper types succeeds.
        m = Message.Model(
            scene_id=EntityId("scene-1"),
            index=0,
            sender_id=EntityId("char-a"),
            body="hello",
        )
        assert m.scene_id == "scene-1"
        assert m.index == 0
        assert m.sender_id == "char-a"
        assert m.body == "hello"

    def test_model_rejects_missing_fields(self) -> None:
        # message-model-fields: all four fields are required by the Pydantic model.
        with pytest.raises(ValidationError):
            Message.Model(scene_id="s", index=0, body="hi")  # type: ignore[call-arg]

    def test_model_is_inner_class_of_message(self) -> None:
        # message-model-inner: defined as an inner class on Message (per spec).
        assert Message.Model.__qualname__.startswith("Message."), (
            "message-model-inner: Message.Model must be an inner class on "
            f"Message; got qualname={Message.Model.__qualname__!r}"
        )
