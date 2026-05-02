from datetime import datetime, timezone

import pytest

from sidestage.ids import CharacterId, SceneId
from sidestage.message import Message


def test_create_sets_scene_character_and_content_from_arguments():
    msg = Message.create(SceneId("s"), CharacterId("c"), "hello")
    assert msg.scene_id == SceneId("s"), (
        "Message.create must set .scene_id to the SceneId argument; "
        "expected SceneId('s')"
    )
    assert msg.character_id == CharacterId("c"), (
        "Message.create must set .character_id to the CharacterId argument; "
        "expected CharacterId('c')"
    )
    assert msg.content == "hello", (
        "Message.create must set .content to the content argument; expected 'hello'"
    )


def test_create_produces_unique_ids_for_identical_arguments():
    msg1 = Message.create(SceneId("s"), CharacterId("c"), "hello")
    msg2 = Message.create(SceneId("s"), CharacterId("c"), "hello")
    assert msg1.id != msg2.id, (
        "Each Message.create call must produce a unique .id (uuid uniqueness), "
        "even when called with identical arguments; got the same id twice"
    )


def test_timestamp_is_timezone_aware_utc():
    msg = Message.create(SceneId("s"), CharacterId("c"), "hello")
    assert isinstance(msg.timestamp, datetime), (
        "Message.timestamp must be a datetime instance"
    )
    assert msg.timestamp.tzinfo is not None, (
        "Message.timestamp must be timezone-aware (tzinfo must not be None)"
    )
    assert msg.timestamp.utcoffset() == timezone.utc.utcoffset(None), (
        "Message.timestamp must be in UTC; expected utcoffset to equal UTC's offset (zero)"
    )


def test_message_is_immutable():
    msg = Message.create(SceneId("s"), CharacterId("c"), "hello")
    with pytest.raises((AttributeError,)) as exc_info:
        msg.content = "changed"
    error_name = type(exc_info.value).__name__
    assert error_name in ("FrozenInstanceError", "AttributeError"), (
        f"Setting an attribute on a Message must raise FrozenInstanceError or "
        f"AttributeError to enforce immutability; got {error_name} instead"
    )
