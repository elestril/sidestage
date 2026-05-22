from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from sidestage.entity import EntityId
from sidestage.message import Message


class TestMessage:
    def test_message_class_has_only_sender_id_and_body(self) -> None:
        # message-class: Message has fields `sender_id: EntityId` and `body: str`
        # only. No `id` / `scene_id` / `index` field — position in
        # `scene.messages` IS the identity.
        field_names = set(Message.model_fields)
        assert field_names == {"sender_id", "body"}, (
            "message-class-fields: Message has exactly two fields, "
            f"sender_id and body; got {field_names!r}"
        )

    def test_message_class_no_id_attribute_on_instances(self) -> None:
        # message-class (negative): instances must not carry an `id` attribute.
        msg = Message(sender_id=EntityId("alice"), body="Hello")
        assert not hasattr(msg, "id"), (
            "message-class-fields: Message instances MUST NOT carry an "
            "`id` attribute; identity is the position in scene.messages"
        )

    def test_message_constructor_assigns_fields(self) -> None:
        # message-class: constructor assigns sender_id and body.
        msg = Message(sender_id=EntityId("alice"), body="hi there")
        assert msg.sender_id == "alice"
        assert msg.body == "hi there"

    def test_message_is_basemodel(self) -> None:
        # message-class: Message IS a Pydantic BaseModel — the wire shape and
        # the in-memory representation are one and the same.
        assert issubclass(Message, BaseModel)

    def test_message_no_inner_model(self) -> None:
        # message-class: the Model/instance split has been collapsed. There is
        # no `Message.Model` inner class anymore.
        assert not hasattr(Message, "Model"), (
            "message-class: Message MUST NOT carry an inner `Model` class; "
            "the BaseModel itself is the wire shape"
        )

    def test_message_rejects_missing_sender_id(self) -> None:
        with pytest.raises(ValidationError):
            Message(body="hi")  # type: ignore[call-arg]

    def test_message_rejects_missing_body(self) -> None:
        with pytest.raises(ValidationError):
            Message(sender_id=EntityId("alice"))  # type: ignore[call-arg]

    def test_message_round_trip_model_dump(self) -> None:
        # message-class: model_dump produces the on-wire shape — flat
        # `{sender_id, body}`.
        msg = Message(sender_id=EntityId("alice"), body="hi")
        assert msg.model_dump() == {"sender_id": "alice", "body": "hi"}
