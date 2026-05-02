from sidestage.actor import UserActor
from sidestage.campaign import Campaign
from sidestage.ids import CampaignId, CharacterId
from sidestage.message import Message
from sidestage.message_repository import MessageRepository


class ChatService:
    def __init__(
        self,
        campaigns: dict[CampaignId, Campaign],
        repo: MessageRepository,
    ) -> None:
        self.campaigns = campaigns
        self.repo = repo

    async def handle_user_message(
        self,
        campaign_id: CampaignId,
        character_id: CharacterId,
        content: str,
    ) -> Message:
        campaign = self.campaigns[campaign_id]
        scene = campaign.get_active_scene()
        character = campaign.get_character(character_id)
        if not isinstance(character.actor, UserActor):
            raise ValueError("Character actor is not a UserActor")
        if character.id not in scene.active_character_ids:
            raise ValueError("Character is not active in scene")
        msg = Message.create(scene.id, character_id, content)
        scene.add_message(msg)
        await self.repo.append(msg)
        return msg
