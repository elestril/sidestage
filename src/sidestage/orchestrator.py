import logging
from typing import Optional, List, Dict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import json
import asyncio

from sidestage.campaign import Campaign
from sidestage.sync import SyncManager
from sidestage.schemas import (
    SceneCreateRequest, 
    EntityMarkdownUpdateRequest, 
    ChatRequest, 
    EntityListResponse, 
    EntityMarkdownResponse, 
    StatusResponse,
    ExportResponse,
    ImportResponse,
    ChatResponse
)

logger = logging.getLogger(__name__)

class SidestageOrchestrator:
    def __init__(self, campaign_name: str, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or (Path.home() / ".sidestage")
        
        # API Dispatching: SyncManager owned by Orchestrator
        self.sync_manager = SyncManager()

        # Manage multiple campaigns
        self.campaigns: Dict[str, Campaign] = {}
        self.active_campaign_name = campaign_name
        
        # Initialize the requested campaign
        self._load_campaign(campaign_name)
        
        # Initialize FastAPI app
        self.fastapi_app = FastAPI(
            title="Sidestage Core",
            version="0.1.0",
        )
        
        self._setup_routes()
        self._mount_frontend()

    def _load_campaign(self, name: str):
        if name not in self.campaigns:
            self.campaigns[name] = Campaign(name, self.base_dir)
        return self.campaigns[name]

    @property
    def campaign(self) -> Campaign:
        """Helper to access the active campaign."""
        return self.campaigns[self.active_campaign_name]

    def _setup_routes(self):
        # WebSocket
        @self.fastapi_app.websocket("/v1/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.sync_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await self.sync_manager.handle_message(websocket, data)
            except WebSocketDisconnect:
                self.sync_manager.disconnect(websocket)

        # Entities
        @self.fastapi_app.get("/v1/entities")
        async def list_entities():
            return self.campaign.list_entities()

        @self.fastapi_app.get("/v1/entities/{entity_id}/markdown")
        async def get_entity_markdown(entity_id: str):
            markdown = self.campaign.get_entity_markdown(entity_id)
            if not markdown:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"markdown": markdown}

        @self.fastapi_app.post("/v1/entities/export")
        async def export_entities():
            count = self.campaign.export_entities()
            return {"message": f"Exported {count} entities to disk"}

        @self.fastapi_app.post("/v1/entities/import")
        async def import_entities():
            count = await self.campaign.import_entities()
            if count > 0:
                await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"message": f"Successfully imported {count} entities."}

        @self.fastapi_app.post("/v1/entities/{entity_id}/markdown")
        async def update_entity_markdown(entity_id: str, request: EntityMarkdownUpdateRequest):
            success = await self.campaign.update_entity_markdown(entity_id, request.markdown)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"status": "ok"}

        @self.fastapi_app.post("/v1/entities/{entity_id}")
        async def update_entity(entity_id: str, data: dict):
            success = await self.campaign.update_entity(entity_id, data)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"status": "ok"}

        # Scenes
        @self.fastapi_app.get("/v1/scenes")
        async def list_scenes():
            return self.campaign.list_scenes()

        @self.fastapi_app.post("/v1/scenes")
        async def create_scene(request: SceneCreateRequest):
            scene = await self.campaign.create_scene(
                name=request.name,
                description=request.description,
                current_gametime=request.current_gametime
            )
            await self.sync_manager.broadcast({"type": "scene_updated"})
            return scene.model_dump()

        @self.fastapi_app.get("/v1/scenes/{scene_id}/messages")
        async def get_scene_messages(scene_id: str):
            messages = self.campaign.get_scene_messages(scene_id)
            if messages is None:
                raise HTTPException(status_code=404, detail="Scene not found")
            return messages

        # Chat
        @self.fastapi_app.post("/v1/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            # 1. Get Scene object
            scene = self.campaign.get_scene_object(request.scene_id)
            if not scene:
                raise HTTPException(status_code=404, detail="Scene not found")

            # 2. Create user message object (Logic handled by Scene factory)
            user_msg = scene.create_message(actor="user", text=request.message)
            
            # 3. Broadcast user message immediately (non-blocking for UI)
            # Persistance will happen inside scene.chat
            await self.sync_manager.broadcast({
                "type": "chat_message",
                "message": user_msg.model_dump(),
                "scene_id": request.scene_id
            })
            
            # 4. Call chat generator (which handles persistance of user and agent messages)
            agent_msg = None
            async for msg in scene.chat(user_msg):
                await self.sync_manager.broadcast({
                    "type": "chat_message",
                    "message": msg.model_dump(),
                    "scene_id": request.scene_id
                })
                agent_msg = msg
            
            if not agent_msg:
                 raise HTTPException(status_code=500, detail="Agent failed to respond")

            return ChatResponse(user_message=user_msg, agent_message=agent_msg)

        # Redirect root to /sidestage
        @self.fastapi_app.get("/")
        async def root_redirect():
            return RedirectResponse(url="/sidestage")

        # Redirect legacy routes
        @self.fastapi_app.get("/scenes")
        @self.fastapi_app.get("/scenes/{rest:path}")
        async def scenes_redirect(rest: str = ""):
            return RedirectResponse(url=f"/sidestage/scenes/{rest}")

        @self.fastapi_app.get("/entities")
        @self.fastapi_app.get("/entities/{rest:path}")
        async def entities_redirect(rest: str = ""):
            return RedirectResponse(url=f"/sidestage/entities/{rest}")

        # UI Catch-all for SPA routing
        @self.fastapi_app.get("/sidestage/{full_path:path}")
        async def ui_catch_all(full_path: str):
            dist_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
            
            # Check if it's a direct file request (e.g. assets)
            file_path = dist_dir / full_path
            if full_path != "" and file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            
            # Otherwise serve index.html for SPA
            index_path = dist_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404)

    def _mount_frontend(self):
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "frontend" / "dist"
        
        if dist_dir.exists():
            # Mount static files at /sidestage
            # This handles /sidestage/assets/... and /sidestage/index.html
            self.fastapi_app.mount("/sidestage", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
            logger.info(f"Frontend mounted from: {dist_dir} at /sidestage")
        else:
            logger.warning(f"Built frontend directory not found at {dist_dir}. No frontend will be served.")
