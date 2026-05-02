from pathlib import Path

import uvicorn
from fastapi import FastAPI

from sidestage.campaign import Campaign
from sidestage.chat_service import ChatService
from sidestage.config_loader import ConfigLoader
from sidestage.ids import CampaignId
from sidestage.llm_client import LiteLLMClient
from sidestage.message_repository import InMemoryMessageRepository, MessageRepository
from sidestage.rest import create_router
from sidestage.ws import create_ws_router


def create_app(
    campaigns: dict[CampaignId, Campaign],
    repo: MessageRepository,
) -> FastAPI:
    chat_service = ChatService(campaigns, repo)
    app = FastAPI()
    app.include_router(create_router(campaigns, repo))
    app.include_router(create_ws_router(campaigns, chat_service, repo))
    return app


def main() -> None:
    config_root = Path("./configs")
    loader = ConfigLoader(config_root)
    server_config = loader.load_server_config()
    llm_client = LiteLLMClient(server_config.default_model)
    campaigns = loader.load_all_campaigns(llm_client)
    repo = InMemoryMessageRepository()
    app = create_app(campaigns, repo)
    uvicorn.run(app)


if __name__ == "__main__":
    main()
