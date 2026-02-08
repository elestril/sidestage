import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import json
import asyncio

from sidestage.campaign import Campaign
from sidestage.sync import SyncManager
from sidestage.health import HealthStatus
from sidestage.migration.models import (
    MigrationImportRequest,
    MigrationImportResponse,
    MigrationBackupResult,
    MigrationValidationReport,
    MigrationValidationIssue,
)
from sidestage.migration.parser import parse_directory
from sidestage.migration.validator import validate_parse_result
from sidestage.migration.importer import import_campaign
from sidestage.migration.exporter import export_campaign
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
    """
    The central coordinator for the Sidestage application.
    
    The Orchestrator is responsible for:
    1. Initializing the FastAPI application and routes.
    2. Managing the lifecycle of Campaigns.
    3. Handling WebSocket connections via SyncManager.
    4. Routing API requests to the appropriate Campaign or Scene components.
    5. Serving the frontend static assets.
    """
    def __init__(self, campaign_name: str, base_dir: Optional[Path] = None):
        """
        Initialize the Orchestrator.

        Args:
            campaign_name (str): The name of the campaign to load/create.
            base_dir (Optional[Path]): The base directory for data storage. Defaults to ~/.sidestage.
        """
        self.base_dir = base_dir or (Path.home() / ".sidestage")
        
        # API Dispatching: SyncManager owned by Orchestrator
        self.sync_manager = SyncManager()

        # Manage multiple campaigns
        self.campaigns: Dict[str, Campaign] = {}
        self.active_campaign_name = campaign_name
        
        # Active scenes across all campaigns (scene_id -> SceneLogic)
        self.active_scenes: Dict[str, Any] = {}
        
        # Initialize the requested campaign
        self._load_campaign(campaign_name)
        
        # Initialize FastAPI app
        self.fastapi_app = FastAPI(
            title="Sidestage Core",
            version="0.1.0",
        )
        
        self._setup_routes()
        self._mount_frontend()

    def _load_campaign(self, name: str) -> Campaign:
        """
        Load a campaign by name, creating it if it doesn't exist.

        Args:
            name (str): The name of the campaign.

        Returns:
            Campaign: The campaign instance.
        """
        if name not in self.campaigns:
            self.campaigns[name] = Campaign(name, self.base_dir)
        return self.campaigns[name]

    @property
    def campaign(self) -> Campaign:
        """Helper to access the currently active campaign."""
        return self.campaigns[self.active_campaign_name]

    async def get_active_scene(self, scene_id: str) -> Optional[Any]:
        """
        Retrieve or activate a scene by ID.
        
        If the scene is not already active in memory, it loads it from the campaign
        and activates it (starting its message bus and agents).

        Args:
            scene_id (str): The ID of the scene.

        Returns:
            Optional[Any]: The active SceneLogic instance, or None if not found.
        """
        if scene_id in self.active_scenes:
            return self.active_scenes[scene_id]
        
        scene_logic = self.campaign.get_scene_object(scene_id)
        if scene_logic:
            await scene_logic.activate()
            # Subscribe for broadcasting
            scene_logic.bus.subscribe(self._on_scene_event)
            self.active_scenes[scene_id] = scene_logic
            return scene_logic
        return None

    async def _on_scene_event(self, event: Any) -> None:
        """
        Callback for scene events. Broadcasts chat messages to all connected WebSocket clients.

        Args:
            event (Any): The event received from a scene bus.
        """
        from sidestage.schemas import ChatMessage
        if isinstance(event, ChatMessage):
            await self.sync_manager.broadcast({
                "type": "chat_message",
                "message": event.model_dump(),
                "scene_id": event.scene_id
            })

    async def _handle_ws_message(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """
        Internal handler for incoming WebSocket messages from clients.
        
        Routes 'chat_message' type messages to the appropriate active Scene bus.

        Args:
            websocket (WebSocket): The client connection.
            message (Dict[str, Any]): The parsed JSON message.
        """
        msg_type = message.get("type")
        scene_id = message.get("scene_id")
        
        if msg_type == "chat_message" and scene_id:
            scene = await self.get_active_scene(scene_id)
            if scene:
                # Convert dict to ChatMessage schema
                # This assumes the frontend sends a format that matches ChatMessage or can be adapted
                from sidestage.schemas import ChatMessage
                try:
                    # If it's a raw text from user, we need to create a proper ChatMessage
                    text = message.get("text")
                    if text:
                        user_msg = scene.create_message(actor_id="user", text=text)
                        await scene.chat(user_msg)
                except Exception as e:
                    logger.error(f"Error publishing to scene bus: {e}")

    def _setup_routes(self) -> None:
        """Define and register all FastAPI routes."""
        # WebSocket
        @self.fastapi_app.websocket("/v1/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.sync_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await self.sync_manager.handle_message(websocket, data, handler=self._handle_ws_message)
            except WebSocketDisconnect:
                self.sync_manager.disconnect(websocket)

        # Entities
        @self.fastapi_app.get("/v1/entities")
        async def list_entities():
            """List all entities in the active campaign."""
            return await self.campaign.list_entities()

        @self.fastapi_app.get("/v1/entities/{entity_id}/markdown")
        async def get_entity_markdown(entity_id: str):
            """Get the markdown body of a specific entity."""
            markdown = await self.campaign.get_entity_markdown(entity_id)
            if not markdown:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"markdown": markdown}

        @self.fastapi_app.post("/v1/entities/export")
        async def export_entities():
            """Export all entities to the file system."""
            count = await self.campaign.export_entities()
            return {"message": f"Exported {count} entities to disk"}

        @self.fastapi_app.post("/v1/entities/import")
        async def import_entities():
            """Import entities from the file system, updating the database."""
            count = await self.campaign.import_entities()
            if count > 0:
                await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"message": f"Successfully imported {count} entities."}

        @self.fastapi_app.post("/v1/entities/{entity_id}/markdown")
        async def update_entity_markdown(entity_id: str, request: EntityMarkdownUpdateRequest):
            """Update the markdown body of an entity."""
            success = await self.campaign.update_entity_markdown(entity_id, request.markdown)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"status": "ok"}

        @self.fastapi_app.post("/v1/entities/{entity_id}")
        async def update_entity(entity_id: str, data: Dict[str, Any]):
            """Update arbitrary fields of an entity."""
            success = await self.campaign.update_entity(entity_id, data)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"status": "ok"}

        @self.fastapi_app.post("/v1/campaign/reload-defaults")
        async def reload_defaults():
            """Reload default characters and prompts from the data directory."""
            self.campaign.reload_defaults()
            await self.sync_manager.broadcast({"type": "entities_updated"})
            return {"status": "ok"}

        # Campaign migration (import/backup)
        @self.fastapi_app.post("/v1/campaign/import")
        async def import_campaign_route(
            request: MigrationImportRequest,
        ) -> MigrationImportResponse:
            """Import entities and memories from the markdown directory into FalkorDB.

            Two-phase operation:
            - action='validate': Parse and validate the markdown directory, return report.
            - action='execute': Parse, validate, and execute the full import.

            Returns 409 if campaign health is DEGRADED (another import is in progress).
            """
            if self.campaign.health.status == HealthStatus.DEGRADED:
                raise HTTPException(
                    status_code=409,
                    detail="Campaign operation already in progress",
                )

            markdown_dir = self.campaign.campaign_dir / "markdown"
            if not markdown_dir.exists():
                return MigrationImportResponse(
                    action=request.action,
                    validation=MigrationValidationReport(
                        valid=False,
                        entities_found=0,
                        memories_found=0,
                        entity_counts={},
                        errors=[
                            MigrationValidationIssue(
                                file_path=str(markdown_dir),
                                severity="error",
                                message="Markdown directory does not exist",
                            )
                        ],
                        warnings=[],
                    ),
                )

            parse_result = parse_directory(markdown_dir)
            validation_report = validate_parse_result(parse_result)

            if request.action == "validate":
                return MigrationImportResponse(
                    action="validate",
                    validation=validation_report,
                )

            # action == "execute"
            if not validation_report.valid and not request.force:
                return MigrationImportResponse(
                    action="execute",
                    validation=validation_report,
                )

            result = await import_campaign(
                campaign=self.campaign,
                parse_result=parse_result,
                sync_manager=self.sync_manager,
                active_scenes=self.active_scenes,
            )
            return MigrationImportResponse(
                action="execute",
                validation=validation_report,
                result=result,
            )

        @self.fastapi_app.post("/v1/campaign/backup")
        async def backup_campaign_route() -> MigrationBackupResult:
            """Backup all entities, memories, and chat logs to the markdown directory.

            Returns 409 if campaign health is DEGRADED (import in progress).
            """
            if self.campaign.health.status == HealthStatus.DEGRADED:
                raise HTTPException(
                    status_code=409,
                    detail="Campaign operation already in progress",
                )

            result = await export_campaign(self.campaign)
            if result.phase == "complete":
                await self.sync_manager.broadcast({"type": "entities_updated"})
            return result

        # Scenes
        @self.fastapi_app.get("/v1/scenes")
        async def list_scenes():
            """List all scenes."""
            return await self.campaign.list_scenes()

        @self.fastapi_app.post("/v1/scenes")
        async def create_scene(request: SceneCreateRequest):
            """Create a new scene."""
            scene = await self.campaign.create_scene(
                name=request.name,
                description=request.description,
                current_gametime=request.current_gametime
            )
            await self.sync_manager.broadcast({"type": "scene_updated"})
            return scene.model_dump()

        @self.fastapi_app.get("/v1/scenes/{scene_id}/messages")
        async def get_scene_messages(scene_id: str):
            """Get message history for a scene."""
            messages = self.campaign.get_scene_messages(scene_id)
            if messages is None:
                raise HTTPException(status_code=404, detail="Scene not found")
            return messages

        # Chat
        @self.fastapi_app.post("/v1/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            """
            Send a chat message to a scene.
            
            This endpoint handles the user's message, creating a ChatMessage event
            and publishing it to the scene's message bus. Agent responses occur asynchronously.
            """
            # 1. Get Scene object (Ensures it's activated)
            scene = await self.get_active_scene(request.scene_id)
            if not scene:
                raise HTTPException(status_code=404, detail="Scene not found")

            # 2. Create user message object (Logic handled by Scene factory)
            user_msg = scene.create_message(actor_id="user", text=request.message)
            
            # 3. Call chat (which publishes to bus)
            # This is now fire-and-forget regarding the agent response.
            # Persistence and broadcasting (via _on_scene_event) will happen automatically.
            await scene.chat(user_msg)
            
            return ChatResponse(user_message=user_msg)

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

    def _mount_frontend(self) -> None:
        """Mount the frontend static files if they exist."""
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "frontend" / "dist"
        
        if dist_dir.exists():
            # Mount static files at /sidestage
            # This handles /sidestage/assets/... and /sidestage/index.html
            self.fastapi_app.mount("/sidestage", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
            logger.info(f"Frontend mounted from: {dist_dir} at /sidestage")
        else:
            logger.warning(f"Built frontend directory not found at {dist_dir}. No frontend will be served.")
