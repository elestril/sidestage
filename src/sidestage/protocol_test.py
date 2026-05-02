import pytest

from sidestage.ids import CharacterId, MessageId
from sidestage.protocol import (
    ErrorFrame,
    MessageFrame,
    SendMessage,
    StreamDelta,
    StreamEnd,
    StreamStart,
    parse_client_message,
)


def test_parse_client_message_returns_send_message_with_content():
    result = parse_client_message({"type": "send_message", "content": "hello"})
    assert result == SendMessage(content="hello"), (
        "parse_client_message must convert {'type': 'send_message', 'content': 'hello'} "
        "into SendMessage(content='hello'); got a different value or type"
    )
    assert isinstance(result, SendMessage), (
        "parse_client_message must return an instance of SendMessage when the type "
        "is 'send_message'; got a different class"
    )
    assert result.content == "hello", (
        "SendMessage.content must equal the 'content' field of the input dict; "
        "expected 'hello'"
    )


def test_parse_client_message_raises_value_error_for_unknown_type():
    with pytest.raises(ValueError):
        parse_client_message({"type": "unknown"})


def test_message_frame_to_dict_includes_type_and_all_fields():
    frame = MessageFrame(
        message_id=MessageId("m1"),
        character_id=CharacterId("c1"),
        character_name="Bob",
        content="hi there",
        timestamp="2026-05-02T12:00:00+00:00",
    )
    d = frame.to_dict()
    assert isinstance(d, dict), (
        "MessageFrame.to_dict() must return a dict"
    )
    assert d.get("type") == "message", (
        "MessageFrame.to_dict() must include 'type': 'message'; got "
        f"type={d.get('type')!r}"
    )
    assert "m1" in repr(d.get("message_id")) or d.get("message_id") == "m1" or d.get("message_id") == MessageId("m1"), (
        "MessageFrame.to_dict() must include the message_id value 'm1' (as a string "
        f"or wrapped MessageId); got message_id={d.get('message_id')!r}"
    )
    assert "c1" in repr(d.get("character_id")) or d.get("character_id") == "c1" or d.get("character_id") == CharacterId("c1"), (
        "MessageFrame.to_dict() must include the character_id value 'c1' (as a string "
        f"or wrapped CharacterId); got character_id={d.get('character_id')!r}"
    )
    assert d.get("character_name") == "Bob", (
        "MessageFrame.to_dict() must include 'character_name': 'Bob'; got "
        f"character_name={d.get('character_name')!r}"
    )
    assert d.get("content") == "hi there", (
        "MessageFrame.to_dict() must include 'content': 'hi there'; got "
        f"content={d.get('content')!r}"
    )
    assert d.get("timestamp") == "2026-05-02T12:00:00+00:00", (
        "MessageFrame.to_dict() must include the ISO-format timestamp string; "
        f"expected '2026-05-02T12:00:00+00:00', got timestamp={d.get('timestamp')!r}"
    )


def test_stream_start_to_dict_includes_type_and_fields():
    frame = StreamStart(
        character_id=CharacterId("c1"),
        character_name="Bob",
    )
    d = frame.to_dict()
    assert isinstance(d, dict), "StreamStart.to_dict() must return a dict"
    assert d.get("type") == "stream_start", (
        "StreamStart.to_dict() must include 'type': 'stream_start'; got "
        f"type={d.get('type')!r}"
    )
    assert "c1" in repr(d.get("character_id")) or d.get("character_id") == "c1" or d.get("character_id") == CharacterId("c1"), (
        "StreamStart.to_dict() must include the character_id value 'c1'; got "
        f"character_id={d.get('character_id')!r}"
    )
    assert d.get("character_name") == "Bob", (
        "StreamStart.to_dict() must include 'character_name': 'Bob'; got "
        f"character_name={d.get('character_name')!r}"
    )


def test_stream_delta_to_dict_includes_type_and_fields():
    frame = StreamDelta(
        character_id=CharacterId("c1"),
        token="hel",
    )
    d = frame.to_dict()
    assert isinstance(d, dict), "StreamDelta.to_dict() must return a dict"
    assert d.get("type") == "stream_delta", (
        "StreamDelta.to_dict() must include 'type': 'stream_delta'; got "
        f"type={d.get('type')!r}"
    )
    assert "c1" in repr(d.get("character_id")) or d.get("character_id") == "c1" or d.get("character_id") == CharacterId("c1"), (
        "StreamDelta.to_dict() must include the character_id value 'c1'; got "
        f"character_id={d.get('character_id')!r}"
    )
    assert d.get("token") == "hel", (
        "StreamDelta.to_dict() must include 'token': 'hel'; got "
        f"token={d.get('token')!r}"
    )


def test_stream_end_to_dict_includes_type_and_fields():
    frame = StreamEnd(
        character_id=CharacterId("c1"),
        message_id=MessageId("m1"),
    )
    d = frame.to_dict()
    assert isinstance(d, dict), "StreamEnd.to_dict() must return a dict"
    assert d.get("type") == "stream_end", (
        "StreamEnd.to_dict() must include 'type': 'stream_end'; got "
        f"type={d.get('type')!r}"
    )
    assert "c1" in repr(d.get("character_id")) or d.get("character_id") == "c1" or d.get("character_id") == CharacterId("c1"), (
        "StreamEnd.to_dict() must include the character_id value 'c1'; got "
        f"character_id={d.get('character_id')!r}"
    )
    assert "m1" in repr(d.get("message_id")) or d.get("message_id") == "m1" or d.get("message_id") == MessageId("m1"), (
        "StreamEnd.to_dict() must include the message_id value 'm1'; got "
        f"message_id={d.get('message_id')!r}"
    )


def test_error_frame_to_dict_returns_type_and_detail():
    d = ErrorFrame(detail="oops").to_dict()
    assert d == {"type": "error", "detail": "oops"}, (
        "ErrorFrame(detail='oops').to_dict() must return exactly "
        f"{{'type': 'error', 'detail': 'oops'}}; got {d!r}"
    )
