import yaml
import logging
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.base import Model
from agno.models.llama_cpp import LlamaCpp
from agno.models.message import Message
from agno.os import AgentOS
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
import json
import asyncio

from sidestage.storage import Storage
from sidestage.tools import WorldTools
from sidestage.entities import entity_to_markdown, markdown_to_entity, NPC, Location, Item

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        logger.info(f"Broadcasting message: {message.get('type')}")
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to a client: {e}")
                # We don't remove here to avoid modifying list during iteration
                # Disconnect will handle it or next broadcast will fail too

class SidestageConfig(BaseModel):
    # LLM Configuration
    llm_provider: str = Field(default="llama_cpp", description="LLM provider to use: 'llama_cpp' or 'gemini'")
    
    # Llama.cpp Configuration
    llama_cpp_base_url: str = "http://medusa:8080/v1"
    llama_cpp_api_key: str = "sk-no-key-required"
    llama_cpp_model: str = "default"

    # Gemini Configuration
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

class SidestageOrchestrator:
    def __init__(self, campaign_name: str, base_dir: Optional[Path] = None):
        self.campaign_name = campaign_name
        self.base_dir = base_dir or (Path.home() / ".sidestage")
        self.campaign_dir = self.base_dir / campaign_name
        self._ensure_campaign_dir()
        
        # Setup logging to campaign directory
        self._setup_logging()

        self.config_path = self.campaign_dir / "config.yml"
        self.config = self._load_or_create_config()
        
        # Single database for everything
        self.db = SqliteDb(db_file=str(self.campaign_dir / "sidestage.db"))
        self.storage = Storage(db=self.db)
        self.manager = ConnectionManager()

        # Define a callback for WorldTools to notify of changes
        def on_world_change():
            if self.manager:
                # We need to bridge sync tool call to async broadcast
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self.manager.broadcast({"type": "entities_updated"}))
                    else:
                        asyncio.run(self.manager.broadcast({"type": "entities_updated"}))
                except Exception as e:
                    logger.error(f"Error broadcasting world change: {e}")

        self.world_tools = WorldTools(storage=self.storage, on_change=on_world_change)
        self.model = self.get_llm_model()
        self.agent = self.create_agent()

        self.app = AgentOS(
            name="Sidestage Core",
            version="0.1.0",
            agents=[self.agent],
            db=self.db,
            tracing=True
        )
        
        # Cache the FastAPI app instance to ensure modifications (like mounting) persist
        self.fastapi_app = self.app.get_app()

        # Add custom endpoints
        @self.fastapi_app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.manager.connect(websocket)
            try:
                while True:
                    # Keep connection alive, we mostly use it for server-to-client broadcast
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.manager.disconnect(websocket)

        @self.fastapi_app.get("/entities")
        async def list_entities():
            entities = self.storage.list_all_entities()
            # Add type to the response for the UI
            result = []
            for e in entities:
                d = e.model_dump()
                d["type"] = e.__class__.__name__
                result.append(d)
            return result

        @self.fastapi_app.get("/entities/{entity_id}/markdown")
        async def get_entity_markdown(entity_id: str):
            entities = self.storage.list_all_entities()
            entity = next((e for e in entities if e.id == entity_id), None)
            if not entity:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"markdown": entity_to_markdown(entity)}

        @self.fastapi_app.post("/entities/export")
        async def export_entities():
            logger.info("Exporting entities...")
            entities_dir = self.campaign_dir / "entities"
            entities_dir.mkdir(parents=True, exist_ok=True)
            
            entities = self.storage.list_all_entities()
            count = 0
            for entity in entities:
                md_content = entity_to_markdown(entity)
                # Use a safe filename
                filename = f"{entity.id}.md"
                (entities_dir / filename).write_text(md_content)
                count += 1
            
            logger.info(f"Successfully exported {count} entities.")
            return {"message": f"Exported {count} entities to {entities_dir}"}

        @self.fastapi_app.post("/entities/import")
        async def import_entities():
            logger.info("Importing entities...")
            entities_dir = self.campaign_dir / "entities"
            if not entities_dir.exists():
                logger.warning("Import failed: entities directory does not exist.")
                return {"message": "No entities directory found for import.", "count": 0}
            
            count = 0
            for md_file in entities_dir.glob("*.md"):
                try:
                    md_content = md_file.read_text()
                    entity = markdown_to_entity(md_content)
                    
                    if isinstance(entity, NPC):
                        self.storage.add_npc(entity)
                    elif isinstance(entity, Location):
                        self.storage.add_location(entity)
                    elif isinstance(entity, Item):
                        self.storage.add_item(entity)
                    count += 1
                except Exception as e:
                    logger.error(f"Error importing {md_file.name}: {e}")
            
            logger.info(f"Successfully imported {count} entities.")
            # Broadcast update
            await self.manager.broadcast({"type": "entities_updated"})
            return {"message": f"Imported {count} entities from {entities_dir}", "count": count}

        class ChatRequest(BaseModel):
            message: str

        @self.fastapi_app.post("/chat")
        async def chat_endpoint(request: ChatRequest):
            message = request.message
            logger.info(f"Chat request received: {message[:20]}...")
            # Broadcast user message
            await self.manager.broadcast({
                "type": "chat_message",
                "text": message,
                "sender": "user"
            })
            
            # Run agent asynchronously
            response = await self.agent.arun(message, stream=False)
            response_content = str(response.content) if hasattr(response, 'content') and response.content is not None else str(response)

            # Detect entities in response to send widgets
            widget = None
            entities = self.storage.list_all_entities()
            for e in entities:
                if e.id in response_content:
                    widget = e.model_dump()
                    widget["type"] = "entity"
                    widget["entity_type"] = e.__class__.__name__
                    break # Just one widget for now

            # Broadcast agent message
            await self.manager.broadcast({
                "type": "chat_message",
                "text": response_content,
                "sender": "agent",
                "widget": widget
            })
            
            return {"status": "ok"}

        # Mount frontend static files
        self._mount_frontend()

    def _setup_logging(self):
        log_file = self.campaign_dir / "server.log"
        
        # Configure the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Avoid adding multiple handlers if the orchestrator is re-initialized in the same process
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file.absolute()) for h in root_logger.handlers):
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            root_logger.addHandler(file_handler)
            
            logger.info(f"Logging initialized. Output redirected to: {log_file}")

    def _mount_frontend(self):
        project_root = Path(__file__).parent.parent.parent
        static_dir = project_root / "static"
        
        if static_dir.exists():
            fastapi_app = self.fastapi_app
            
            # Remove default AgentOS root route to allow frontend to serve index.html
            for route in list(fastapi_app.routes):
                if getattr(route, "path", None) == "/":
                    fastapi_app.routes.remove(route)
                    break

            # Mount the static directory
            fastapi_app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
            logger.info(f"Frontend mounted from: {static_dir}")
        else:
            logger.warning(f"Static directory not found at {static_dir}. No frontend will be served.")

    def _ensure_campaign_dir(self):
        if not self.campaign_dir.exists():
            logger.info(f"Creating new campaign directory: {self.campaign_dir}")
            self.campaign_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(f"Loading campaign from: {self.campaign_dir}")

    def _load_or_create_config(self) -> SidestageConfig:
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                try:
                    data = yaml.safe_load(f) or {}
                    config = SidestageConfig(**data)
                except Exception as e:
                    logger.warning(f"Error loading config.yml ({e}). Using defaults.")
                    config = SidestageConfig()
        else:
            logger.info(f"Creating default configuration at: {self.config_path}")
            config = SidestageConfig()
        
        # Always save back to ensure any new defaults are populated and formatting is consistent
        self._save_config(config)
        return config

    def _save_config(self, config: SidestageConfig):
        with open(self.config_path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

    def get_llm_model(self) -> Model:
        """
        Factory to return the configured LLM model instance.
        """
        provider = self.config.llm_provider.lower()

        if provider == "llama_cpp":
            return LlamaCpp(
                id=self.config.llama_cpp_model,
                base_url=self.config.llama_cpp_base_url,
            )
        
        elif provider == "gemini":
            raise NotImplementedError("Gemini provider not yet enabled. Please install google-generativeai.")

        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def create_agent(self) -> Agent:
        """
        Initializes the Co-Author agent with the configured model and tools.
        """
        return Agent(
            name="Sidestage Co-Author",
            model=self.model,
            # description="Sidestage Co-Author: RPG World-Building Assistant",
            debug_mode=True,
            add_datetime_to_context=False,
            add_name_to_context=False,
            instructions=[
                "You are the Sidestage Co-Author, a world-building assistant.",
                "STRICT PERSONA: NEVER identify as a 'large language model'. You are strictly the Sidestage Co-Author.",
                "DATABASE-ONLY KNOWLEDGE: You know NOTHING about NPCs, locations, or items except what is in your database.",
                "TOOL-FIRST: If asked about characters, world details, or 'which NPCs do you know?', you MUST call `list_npcs` immediately.",
                "NEVER list famous characters from other games (like Fallout or Elder Scrolls) unless they were created in THIS campaign.",
                "TONE: Helpful and collaborative."
            ],
            tools=[
                self.world_tools.create_npc,
                self.world_tools.update_npc,
                self.world_tools.get_npc,
                self.world_tools.list_npcs,
                self.world_tools.create_location,
                self.world_tools.update_location,
                self.world_tools.list_locations,
                self.world_tools.create_item,
                self.world_tools.update_item,
                self.world_tools.list_items,
            ],
            stream=True,
            markdown=True,
            use_instruction_tags=True,
        )