from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sidestage.actor import NpcActor, UserActor
from sidestage.campaign import Campaign
from sidestage.chat_service import ChatService
from sidestage.ids import CampaignId, CharacterId
from sidestage.message import Message
from sidestage.message_repository import MessageRepository
from sidestage.protocol import (
    ErrorFrame,
    MessageFrame,
    StreamDelta,
    StreamEnd,
    StreamStart,
    parse_client_message,
)


def create_ws_router(
    campaigns: dict[CampaignId, Campaign],
    chat_service: ChatService,
    repo: MessageRepository,
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/campaigns/{campaign_id}/ws")
    async def ws_endpoint(
        websocket: WebSocket, campaign_id: str, character_id: str
    ) -> None:
        campaign_id_obj = CampaignId(campaign_id)
        character_id_obj = CharacterId(character_id)

        campaign = campaigns.get(campaign_id_obj)
        if campaign is None:
            await websocket.accept()
            await websocket.send_json(ErrorFrame("Campaign not found").to_dict())
            await websocket.close()
            return

        scene = campaign.get_active_scene()
        character = campaign.characters.get(character_id_obj)
        if character is None:
            await websocket.accept()
            await websocket.send_json(ErrorFrame("Character not found").to_dict())
            await websocket.close()
            return

        if not isinstance(character.actor, UserActor):
            await websocket.accept()
            await websocket.send_json(
                ErrorFrame("Character is not a user character").to_dict()
            )
            await websocket.close()
            return

        if character.id not in scene.active_character_ids:
            await websocket.accept()
            await websocket.send_json(
                ErrorFrame("Character is not active in scene").to_dict()
            )
            await websocket.close()
            return

        await websocket.accept()

        def get_name(cid: CharacterId) -> str:
            return campaign.characters[cid].name

        try:
            while True:
                data = await websocket.receive_json()
                client_msg = parse_client_message(data)
                user_msg = await chat_service.handle_user_message(
                    campaign_id_obj, character_id_obj, client_msg.content
                )
                await websocket.send_json(
                    MessageFrame(
                        user_msg.id,
                        user_msg.character_id,
                        character.name,
                        user_msg.content,
                        user_msg.timestamp.isoformat(),
                    ).to_dict()
                )

                for cid in scene.active_character_ids:
                    npc = campaign.get_character(cid)
                    if not isinstance(npc.actor, NpcActor):
                        continue
                    await websocket.send_json(
                        StreamStart(npc.id, npc.name).to_dict()
                    )
                    tokens: list[str] = []
                    async for token in npc.chat_stream(
                        scene.messages, scene.description, get_name
                    ):
                        tokens.append(token)
                        await websocket.send_json(
                            StreamDelta(npc.id, token).to_dict()
                        )
                    full_content = "".join(tokens)
                    npc_msg = Message.create(scene.id, npc.id, full_content)
                    scene.add_message(npc_msg)
                    await repo.append(npc_msg)
                    await websocket.send_json(
                        StreamEnd(npc.id, npc_msg.id).to_dict()
                    )
        except WebSocketDisconnect:
            return

    return router
