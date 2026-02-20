import atexit
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Union, Callable, AsyncIterator, MutableMapping
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel as _BaseModel
import json
import asyncio

from sidestage.campaign import Campaign
from sidestage import config
from sidestage.health import HealthStatus
from sidestage.request_context import RequestContext, set_request_context, reset_request_context
from sidestage.request_context_middleware import RequestContextMiddleware
from sidestage.tracing import (
    init_tracing,
    toggle_tracing,
    shutdown_tracing,
    get_tracing_enabled,
    get_tracing_error,
)
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
from sidestage.scene import Scene
from sidestage.models import EventModel

logger = logging.getLogger(__name__)


class _LoggingASGIWrapper:
    """ASGI wrapper that logs exceptions from a mounted sub-app.

    Mounted Starlette sub-apps swallow exceptions at the ASGI level,
    so errors only appear on uvicorn stderr. This wrapper ensures they
    also reach the application logger.
    """

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: MutableMapping[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        try:
            await self.app(scope, receive, send)
        except Exception:
            if scope.get("type") != "lifespan":
                logger.exception("MCP endpoint error")
            raise


class SidestageOrchestrator:
    """
    The central coordinator for the Sidestage application.
    
    The Orchestrator is responsible for:
    1. Initializing the FastAPI application and routes.
    2. Managing the lifecycle of Campaigns.
    3. Handling WebSocket connections via User actor.
    4. Routing API requests to the appropriate Campaign or Scene components.
    5. Serving the frontend static assets.
    """
    def __init__(self, campaign_name: str):
        """
        Initialize the Orchestrator.

        Args:
            campaign_name (str): The name of the campaign to load/create.
            base_dir (Optional[Path]): The base directory for data storage. Defaults to ~/.sidestage.
        """

        # Manage multiple campaigns
        self.campaigns: Dict[str, Campaign] = {}
        self.active_campaign_name = campaign_name
        self.base_dir: Path = config.SIDESTAGE_DIR

        # Active scenes across all campaigns (scene_id -> Scene)
        self.active_scenes: Dict[str, Scene] = {}

        # Initialize the requested campaign
        self._load_campaign(campaign_name)
        self._mcp_server: Any = None

        # Initialize FastAPI app
        self.fastapi_app: FastAPI = FastAPI(
            title="Sidestage Core",
            version="0.1.0",
            lifespan=self._lifespan,
        )
        
        self.fastapi_app.add_middleware(RequestContextMiddleware)
        self._setup_routes()
        self._setup_mcp()
        self._mount_frontend()

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Startup: connect graph, init tracing, run MCP. Shutdown: cleanup."""
        await self.campaign.start_graph()
        self._init_tracing()
        try:
            async with self._mcp_server.session_manager.run():
                yield
        finally:
            try:
                await self.campaign.shutdown()
            except Exception:
                logger.exception("Error during campaign shutdown")
            try:
                shutdown_tracing()
            except Exception:
                logger.exception("Error during tracing shutdown")


    def _init_tracing(self) -> None:
        """Initialize the tracing subsystem with OTLP exporter."""
        campaign = self.campaign
        trace_config = campaign.config.tracing
        init_tracing(config=trace_config, campaign_name=campaign.name)
        logger.info("Tracing initialized (enabled=%s)", trace_config.enabled)

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

    async def get_active_scene(self, scene_id: str) -> Optional[Scene]:
        """
        Retrieve or activate a scene by ID.
        
        If the scene is not already active in memory, it loads it from the campaign
        and activates it (starting its event queue and agents).

        Args:
            scene_id (str): The ID of the scene.

        Returns:
            Optional[Scene]: The active Scene instance, or None if not found.
        """
        if scene_id in self.active_scenes:
            return self.active_scenes[scene_id]
        
        scene_logic = self.campaign.get_scene_object(scene_id)
        if scene_logic:
            await scene_logic.activate()
            self.active_scenes[scene_id] = scene_logic
            return scene_logic
        return None

    async def _handle_ws_message(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Handle incoming WebSocket messages from clients."""
        ctx = RequestContext(
            user=message.get("actor", "user"),
            request_id=message.get("request_id", uuid.uuid4().hex[:8]),
            origin="ws",
        )
        token = set_request_context(ctx)
        try:
            await self._dispatch_ws_message(websocket, message)
        finally:
            reset_request_context(token)

    async def _dispatch_ws_message(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Dispatch a WebSocket message after request context is set."""
        msg_type = message.get("type")
        scene_id = message.get("scene_id")

        if msg_type == "chat_message" and scene_id:
            scene = await self.get_active_scene(scene_id)
            if scene:
                try:
                    text = message.get("text", "")
                    character_id = message.get("character_id")
                    await scene.chat(actor_id="user", text=text, character_id=character_id)
                except Exception as e:
                    logger.error(f"Error processing chat message: {e}")

        elif msg_type == "entity_content_sync":
            await self.campaign.user.send(message, exclude=websocket)

    def _setup_mcp(self) -> None:
        """Create and mount the MCP Streamable HTTP endpoint at /v1/mcp.

        The MCP session manager lifespan is run by _lifespan() rather than
        the mounted sub-app, because Starlette does not propagate lifespans
        to mounted sub-applications.
        """
        from sidestage.mcp_bridge import create_mcp_server

        self._mcp_server = create_mcp_server(self)
        mcp_app = self._mcp_server.streamable_http_app()
        self.fastapi_app.mount("/v1/mcp", _LoggingASGIWrapper(mcp_app))
        logger.info("MCP endpoint mounted at /v1/mcp")

    def _setup_routes(self) -> None:
        """Define and register all FastAPI routes."""
        # WebSocket
        @self.fastapi_app.websocket("/v1/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            user = self.campaign.user
            await user.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_json()
                    await self._handle_ws_message(websocket, data)
            except WebSocketDisconnect:
                user.disconnect(websocket)

        # Entities
        @self.fastapi_app.get("/v1/entities")
        async def list_entities() -> List[Dict[str, Any]]:
            """List all entities in the active campaign."""
            return await self.campaign.list_entities()

        @self.fastapi_app.get("/v1/entities/{entity_id}/markdown")
        async def get_entity_markdown(entity_id: str) -> Dict[str, str]:
            """Get the markdown body of a specific entity."""
            markdown = await self.campaign.get_entity_markdown(entity_id)
            if not markdown:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"markdown": markdown}

        @self.fastapi_app.post("/v1/entities/export")
        async def export_entities() -> Dict[str, str]:
            """Export all entities to the file system."""
            count = await self.campaign.export_entities()
            return {"message": f"Exported {count} entities to disk"}

        @self.fastapi_app.post("/v1/entities/import")
        async def import_entities() -> Dict[str, str]:
            """Import entities from the file system, updating the database."""
            count = await self.campaign.import_entities()
            if count > 0:
                await self.campaign.user.send({"type": "entities_updated"})
            return {"message": f"Successfully imported {count} entities."}

        @self.fastapi_app.post("/v1/entities/{entity_id}/markdown")
        async def update_entity_markdown(entity_id: str, request: EntityMarkdownUpdateRequest) -> Dict[str, str]:
            """Update the markdown body of an entity."""
            success = await self.campaign.update_entity_markdown(entity_id, request.markdown)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.campaign.user.send({"type": "entities_updated"})
            return {"status": "ok"}

        @self.fastapi_app.post("/v1/entities/{entity_id}")
        async def update_entity(entity_id: str, data: Dict[str, Any]) -> Dict[str, str]:
            """Update arbitrary fields of an entity."""
            success = await self.campaign.update_entity(entity_id, data)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to update entity")
            await self.campaign.user.send({"type": "entities_updated"})
            return {"status": "ok"}

        @self.fastapi_app.post("/v1/campaign/reload-defaults")
        async def reload_defaults() -> Dict[str, str]:
            """Reload default characters and prompts from the data directory."""
            await self.campaign.reload_defaults()
            await self.campaign.user.send({"type": "entities_updated"})
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
                active_scenes=self.active_scenes,
            )
            if result.phase == "complete":
                await self.campaign.user.send({"type": "entities_updated"})
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
                await self.campaign.user.send({"type": "entities_updated"})
            return result

        # Scenes
        @self.fastapi_app.get("/v1/scenes")
        async def list_scenes() -> List[Dict[str, Any]]:
            """List all scenes."""
            return await self.campaign.list_scenes()

        @self.fastapi_app.post("/v1/scenes")
        async def create_scene(request: SceneCreateRequest) -> Dict[str, Any]:
            """Create a new scene."""
            scene = await self.campaign.create_scene(
                name=request.name,
                description=request.description,
                current_gametime=request.current_gametime
            )
            await self.campaign.user.send({"type": "scene_updated"})
            return scene.model_dump()

        @self.fastapi_app.get("/v1/scenes/{scene_id}/characters")
        async def get_scene_characters(scene_id: str) -> List[Dict[str, Any]]:
            """List characters in a scene."""
            chars = await self.campaign.list_scene_characters(scene_id)
            return [c.model_dump() for c in chars]

        @self.fastapi_app.post("/v1/scenes/{scene_id}/characters/{character_id}", status_code=201)
        async def add_character_to_scene(scene_id: str, character_id: str) -> Dict[str, str]:
            """Add a character to a scene."""
            await self.campaign.add_character_to_scene(scene_id, character_id)
            return {"status": "ok"}

        @self.fastapi_app.delete("/v1/scenes/{scene_id}/characters/{character_id}")
        async def remove_character_from_scene(scene_id: str, character_id: str) -> Dict[str, str]:
            """Remove a character from a scene."""
            await self.campaign.remove_character_from_scene(scene_id, character_id)
            return {"status": "ok"}

        @self.fastapi_app.get("/v1/scenes/{scene_id}/messages")
        async def get_scene_messages(scene_id: str) -> List[EventModel]:
            """Get message history for a scene."""
            messages = self.campaign.get_scene_messages(scene_id)
            if messages is None:
                raise HTTPException(status_code=404, detail="Scene not found")
            return messages

        # Chat
        @self.fastapi_app.post("/v1/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest) -> ChatResponse:
            """
            Send a chat message to a scene.
            
            This endpoint handles the user's message, creating a ChatMessage event
            and publishing it to the scene's message bus. Agent responses occur asynchronously.
            """
            scene = await self.get_active_scene(request.scene_id)
            if not scene:
                raise HTTPException(status_code=404, detail="Scene not found")

            event = await scene.chat(actor_id="user", text=request.message, character_id="user")
            if event is None:
                raise HTTPException(status_code=503, detail="Chat unavailable")

            return ChatResponse(event=event.model)

        # --- Tracing endpoints ---

        class _TracingToggleRequest(_BaseModel):
            enabled: bool

        @self.fastapi_app.post("/v1/tracing/toggle")
        async def toggle_tracing_endpoint(body: _TracingToggleRequest) -> Dict[str, bool]:
            """Toggle tracing on or off."""
            enabled, error = toggle_tracing(body.enabled)
            if error is not None:
                raise HTTPException(status_code=502, detail=error)
            return {"tracing_enabled": enabled}

        @self.fastapi_app.get("/v1/tracing/status")
        async def tracing_status() -> Dict[str, Any]:
            """Return current tracing status."""
            from sidestage import config as sidestage_config
            trace_config = sidestage_config.get_config().tracing

            return {
                "enabled": get_tracing_enabled(),
                "config": trace_config.model_dump(),
                "error": get_tracing_error(),
            }

        # Test-only routes (mock agent configuration)
        if os.environ.get("SIDESTAGE_MOCK_AGENT"):
            from sidestage.testing.routes import register_test_routes
            register_test_routes(self.fastapi_app, self)

        # Redirect root to /sidestage
        @self.fastapi_app.get("/")
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/sidestage")

        # Redirect legacy routes
        @self.fastapi_app.get("/scenes")
        @self.fastapi_app.get("/scenes/{rest:path}")
        async def scenes_redirect(rest: str = "") -> RedirectResponse:
            return RedirectResponse(url=f"/sidestage/scenes/{rest}")

        @self.fastapi_app.get("/entities")
        @self.fastapi_app.get("/entities/{rest:path}")
        async def entities_redirect(rest: str = "") -> RedirectResponse:
            return RedirectResponse(url=f"/sidestage/entities/{rest}")

        # UI Catch-all for SPA routing
        @self.fastapi_app.get("/sidestage/{full_path:path}")
        async def ui_catch_all(full_path: str) -> FileResponse:
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
