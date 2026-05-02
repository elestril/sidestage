from fastapi import APIRouter, HTTPException

from sidestage.campaign import Campaign
from sidestage.ids import CampaignId, SceneId
from sidestage.message_repository import MessageRepository


def create_router(
    campaigns: dict[CampaignId, Campaign], repo: MessageRepository
) -> APIRouter:
    router = APIRouter()

    @router.get("/campaigns")
    def list_campaigns() -> list[dict]:
        return [
            {
                "id": campaign.id.value,
                "name": campaign.name,
                "active_scene_id": (
                    campaign.active_scene_id.value
                    if campaign.active_scene_id is not None
                    else None
                ),
            }
            for campaign in campaigns.values()
        ]

    @router.get("/campaigns/{campaign_id}")
    def get_campaign(campaign_id: str) -> dict:
        campaign = campaigns.get(CampaignId(campaign_id))
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {
            "id": campaign.id.value,
            "name": campaign.name,
            "active_scene_id": (
                campaign.active_scene_id.value
                if campaign.active_scene_id is not None
                else None
            ),
        }

    @router.get("/campaigns/{campaign_id}/scenes/{scene_id}/messages")
    async def get_messages(campaign_id: str, scene_id: str) -> list[dict]:
        if CampaignId(campaign_id) not in campaigns:
            raise HTTPException(status_code=404, detail="Campaign not found")
        messages = await repo.get_by_scene(SceneId(scene_id))
        return [
            {
                "id": message.id.value,
                "character_id": message.character_id.value,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
            }
            for message in messages
        ]

    return router
