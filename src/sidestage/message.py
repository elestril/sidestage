import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sidestage.ids import CharacterId, MessageId, SceneId


@dataclass(frozen=True)
class Message:
    id: MessageId
    scene_id: SceneId
    character_id: CharacterId
    content: str
    timestamp: datetime

    @classmethod
    def create(
        cls, scene_id: SceneId, character_id: CharacterId, content: str
    ) -> "Message":
        return cls(
            id=MessageId(str(uuid.uuid4())),
            scene_id=scene_id,
            character_id=character_id,
            content=content,
            timestamp=datetime.now(UTC),
        )
