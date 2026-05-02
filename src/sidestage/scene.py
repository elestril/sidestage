from dataclasses import dataclass

from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.message import Message


@dataclass
class Scene:
    id: SceneId
    campaign_id: CampaignId
    name: str
    description: str
    active_character_ids: list[CharacterId]
    messages: list[Message]

    def add_message(self, message: Message) -> None:
        if message.scene_id != self.id:
            raise ValueError(
                f"Message scene_id {message.scene_id} does not match scene id {self.id}"
            )
        self.messages.append(message)
