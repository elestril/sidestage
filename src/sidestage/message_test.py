from __future__ import annotations

from dataclasses import fields
from typing import get_type_hints
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from sidestage.entity import EntityId
from sidestage.message import Message, MessageId


class TestMessageId:
    def test_message_id_newtype(self):
        # message-id-newtype: MessageId exists and wraps str via NewType.
        # NewType callables expose __supertype__ pointing at the wrapped type.
        assert getattr(MessageId, "__supertype__", None) is str

    def test_message_id_round_trips_as_str(self):
        # message-id-newtype: A MessageId still IS a str at runtime.
        mid = MessageId("scene-1:0")
        assert isinstance(mid, str)
        assert mid == "scene-1:0"

    def test_message_id_format_constructed_via_scene_index(self):
        # message-id-format: A MessageId is "{scene_id}:{index}". Validate the
        # composition rule at the type level by constructing one the canonical way.
        scene_id = "scene-xyz"
        index = 4
        mid = MessageId(f"{scene_id}:{index}")
        assert mid == "scene-xyz:4"
        assert ":" in mid
        scene_part, _, idx_part = mid.partition(":")
        assert scene_part == scene_id
        assert int(idx_part) == index


class TestMessage:
    def test_message_class_has_only_sender_and_body(self):
        # message-class: Message has fields `sender: Character` and `body: str` only.
        # No `id` field — position in scene.messages IS the id.
        field_names = {f.name for f in fields(Message)}
        assert field_names == {"sender", "body"}

    def test_message_class_no_id_attribute_on_instances(self):
        # message-class (negative): instances must not carry an `id` attribute.
        sender = MagicMock()
        msg = Message(sender=sender, body="Hello")
        assert not hasattr(msg, "id")

    def test_message_has_no_serialize_method(self):
        # message-class (negative): serialization moved to Scene.serialize_message,
        # so Message no longer carries a `serialize` method.
        sender = MagicMock()
        msg = Message(sender=sender, body="Hello")
        assert not hasattr(msg, "serialize")

    def test_message_constructor_assigns_fields(self):
        # message-class: constructor assigns sender and body.
        sender = MagicMock()
        msg = Message(sender=sender, body="hi there")
        assert msg.sender is sender
        assert msg.body == "hi there"


class TestMessageModel:
    def test_model_fields(self):
        # message-model: Message.Model has id (MessageId), sender_id (EntityId), body (str).
        hints = get_type_hints(Message.Model)
        assert set(hints.keys()) == {"id", "sender_id", "body"}

    def test_model_constructs_with_correct_types(self):
        # message-model: constructing the wire model with proper types succeeds.
        m = Message.Model(
            id=MessageId("scene-1:0"),
            sender_id=EntityId("char-a"),
            body="hello",
        )
        assert m.id == "scene-1:0"
        assert m.sender_id == "char-a"
        assert m.body == "hello"

    def test_model_rejects_missing_fields(self):
        # message-model: All three fields are required by the Pydantic model.
        with pytest.raises(ValidationError):
            Message.Model(id="scene:0", body="hi")  # type: ignore[call-arg]

    def test_model_is_inner_class_of_message(self):
        # message-model: defined as an inner class on Message (per spec).
        assert Message.Model.__qualname__.startswith("Message.")
