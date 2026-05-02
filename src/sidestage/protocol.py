from dataclasses import dataclass

from sidestage.ids import CharacterId, MessageId


@dataclass(frozen=True)
class SendMessage:
    content: str


def parse_client_message(data: dict) -> SendMessage:
    msg_type = data.get("type")
    if msg_type == "send_message":
        return SendMessage(content=data["content"])
    raise ValueError(f"Unknown client message type: {msg_type!r}")


@dataclass(frozen=True)
class MessageFrame:
    message_id: MessageId
    character_id: CharacterId
    character_name: str
    content: str
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "type": "message",
            "message_id": self.message_id.value,
            "character_id": self.character_id.value,
            "character_name": self.character_name,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class StreamStart:
    character_id: CharacterId
    character_name: str

    def to_dict(self) -> dict:
        return {
            "type": "stream_start",
            "character_id": self.character_id.value,
            "character_name": self.character_name,
        }


@dataclass(frozen=True)
class StreamDelta:
    character_id: CharacterId
    token: str

    def to_dict(self) -> dict:
        return {
            "type": "stream_delta",
            "character_id": self.character_id.value,
            "token": self.token,
        }


@dataclass(frozen=True)
class StreamEnd:
    character_id: CharacterId
    message_id: MessageId

    def to_dict(self) -> dict:
        return {
            "type": "stream_end",
            "character_id": self.character_id.value,
            "message_id": self.message_id.value,
        }


@dataclass(frozen=True)
class ErrorFrame:
    detail: str

    def to_dict(self) -> dict:
        return {"type": "error", "detail": self.detail}
