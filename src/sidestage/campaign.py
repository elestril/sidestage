import logging
import yaml
import asyncio
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator
from pydantic import BaseModel, Field

from sidestage.agent import LiteLLMAgent
from sidestage.storage import Storage
from sidestage.tools import WorldTools
from sidestage.scene import SceneLogic
from sidestage.schemas import Scene, Character, Location, Item, Entity, Event, ChatResponse, ChatMessage, ChatRequest
from sidestage.entities import entity_to_markdown, markdown_to_entity
from sidestage.graph import GraphConfig, GraphClient, connect, close
from sidestage.graph import create_entity as graph_create_entity
from sidestage.graph import get_entity as graph_get_entity
from sidestage.graph import update_entity as graph_update_entity
from sidestage.graph import list_entities as graph_list_entities

logger = logging.getLogger(__name__)

class SidestageConfig(BaseModel):
    """
    Configuration model for Sidestage settings, primarily LLM connection details.
    """
    # LLM Configuration
    llm_provider: str = Field(default="llama_cpp", description="LLM provider to use: 'llama_cpp' or 'gemini'")
    
    # Llama.cpp Configuration
    llama_cpp_base_url: str = Field(default="http://medusa:8080/v1", description="Base URL for Llama.cpp server")
    llama_cpp_api_key: str = Field(default="sk-no-key-required", description="API Key for Llama.cpp (if required)")
    llama_cpp_model: str = Field(default="default", description="Model name to request (e.g. 'gpt-3.5-turbo' or filename)")

    # Gemini Configuration
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

    # Graph Database Configuration
    graph: GraphConfig = Field(default_factory=GraphConfig, description="FalkorDB graph database configuration")

class Campaign:
    """
    Represents a specific Campaign (a distinct save/world).
    
    The Campaign class serves as the container for:
    - Configuration (LLM settings)
    - Storage (Database connection)
    - World Tools (Entity manipulation logic)
    - The 'Co-Author' Agent (System-level assistant)
    - Defaults/Seeding (Characters, Scenes)
    """
    def __init__(self, name: str, base_dir: Path):
        """
        Initialize the Campaign.

        Args:
            name (str): The name of the campaign.
            base_dir (Path): The root directory where campaign data is stored.
        """
        self.name = name
        self.base_dir = base_dir
        self.campaign_dir = self.base_dir / name
        self._ensure_campaign_dir()
        
        # Setup logging to campaign directory
        self._setup_logging()

        self.config_path = self.campaign_dir / "config.yml"
        self.config = self._load_or_create_config()
        
        # Storage handles SQLite connection
        self.storage = Storage(db_path=self.campaign_dir / "sidestage.db")

        self.graph_client: GraphClient | None = None
        self.world_tools = WorldTools(storage=self.storage, graph_client=self.graph_client)

        # Ensure LLM is available before proceeding
        self._ensure_llm_availability()
        
        self.agent = self.create_agent()

        # Ensure default scene and characters exist
        self._ensure_defaults()

    def _ensure_campaign_dir(self) -> None:
        """Create the campaign directory if it doesn't exist."""
        if not self.campaign_dir.exists():
            logger.info(f"Creating new campaign directory: {self.campaign_dir}")
            self.campaign_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(f"Loading campaign from: {self.campaign_dir}")

    def _setup_logging(self) -> None:
        """Configure file-based logging to the campaign directory."""
        log_file = self.campaign_dir / "server.log"
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file.absolute()) for h in root_logger.handlers):
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            root_logger.addHandler(file_handler)
            
            logger.info(f"Logging initialized. Output redirected to: {log_file}")

    def _load_or_create_config(self) -> SidestageConfig:
        """Load configuration from config.yml or create default."""
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
        
        self._save_config(config)
        return config

    def _save_config(self, config: SidestageConfig) -> None:
        """Save the current configuration to config.yml."""
        with open(self.config_path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

    def create_agent(self) -> LiteLLMAgent:
        """
        Instantiate the main Co-Author agent based on campaign config.
        
        Returns:
            LiteLLMAgent: The configured agent instance.
        """
        provider = self.config.llm_provider.lower()
        model_name = ""
        api_base = None
        api_key = None

        if provider == "llama_cpp":
            model_name = f"openai/{self.config.llama_cpp_model}"
            api_base = self.config.llama_cpp_base_url
            api_key = self.config.llama_cpp_api_key
        elif provider == "gemini":
             model_name = f"gemini/{self.config.gemini_model}"
             api_key = self.config.gemini_api_key
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        return LiteLLMAgent(
            name="Sidestage Co-Author",
            model=model_name,
            api_base=api_base,
            api_key=api_key,
            instructions=[
                "You are the Sidestage Co-Author, a world-building assistant.",
                "STRICT PERSONA: NEVER identify as a 'large language model'. You are strictly the Sidestage Co-Author.",
                "DATABASE-ONLY KNOWLEDGE: You know NOTHING about Characters, locations, or items except what is in your database.",
                "TOOL-FIRST: If asked about characters, world details, or 'which characters do you know?', you MUST call `list_characters` immediately.",
                "NEVER list famous characters from other games (like Fallout or Elder Scrolls) unless they were created in THIS campaign.",
                "TONE: Helpful and collaborative."
            ],
            tools=[
                self.world_tools.create_character,
                self.world_tools.update_character,
                self.world_tools.get_character,
                self.world_tools.list_characters,
                self.world_tools.create_location,
                self.world_tools.update_location,
                self.world_tools.list_locations,
                self.world_tools.create_item,
                self.world_tools.update_item,
                self.world_tools.list_items,
            ],
            debug_mode=False
        )

    def _ensure_defaults(self) -> None:
        """Ensure that necessary default entities (scenes, characters) exist in the database."""
        # Ensure default scene exists
        planning_scene = self.storage.get_scene("campaign_planning")
        if not planning_scene:
            logger.info("Creating default 'Campaign Planning' scene.")
            self.storage.add_scene(Scene(
                id="campaign_planning",
                name="Campaign Planning",
                body="The default space for discussing the campaign world, characters, and plot.",
                current_gametime=None
            ))
        
        # Ensure default characters from data directory are loaded
        self.reload_defaults()

    def reload_defaults(self) -> None:
        """
        Load default characters and other entities from the project's data directory.
        
        This scans the 'data/characters' folder for markdown files and upserts them
        into the database.
        """
        logger.info("Reloading default content from data directory...")
        
        # Use project root to find data directory
        project_root = Path(__file__).parent.parent.parent
        data_dir = project_root / "data"
        
        if not data_dir.exists():
            logger.warning(f"Data directory not found at {data_dir}. Skipping default content loading.")
            return

        # Load Characters
        char_dir = data_dir / "characters"
        if char_dir.exists():
            for char_file in char_dir.glob("*.md"):
                try:
                    content = char_file.read_text()
                    char = markdown_to_entity(content)
                    if isinstance(char, Character):
                        # Use add_character which is INSERT OR REPLACE
                        self.storage.add_character(char)
                        logger.info(f"Loaded default character: {char.name} ({char.id})")
                except Exception as e:
                    logger.error(f"Error loading default character from {char_file}: {e}")

    def _ensure_llm_availability(self) -> None:
        """
        Verify that the configured LLM endpoint is reachable and the model exists.
        
        Raises:
            RuntimeError: If the LLM is unreachable or the model is missing.
        """
        provider = self.config.llm_provider.lower()
        
        if provider == "llama_cpp":
            base_url = self.config.llama_cpp_base_url.rstrip("/")
            url = f"{base_url}/models"
            target_model = self.config.llama_cpp_model
            
            try:
                logger.info(f"Checking LLM availability at {url}...")
                resp = httpx.get(url, timeout=10.0)
                resp.raise_for_status()
                
                data = resp.json()
                # OpenAI /v1/models format usually has 'data' list
                available_models = data.get("data", [])
                available_ids = [m.get("id") for m in available_models if m.get("id")]
                
                if target_model not in available_ids:
                    # If there's only one model and it's not named 'default', but user asked for 'default', 
                    # we might be permissive if it's llama.cpp, but here we enforce as requested.
                    error_msg = f"Specified model '{target_model}' not found at {url}. Available models: {available_ids}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                
                logger.info(f"Verified LLM availability: '{target_model}' is online.")
                
            except httpx.RequestError as e:
                error_msg = f"Failed to connect to LLM provider at {url}: {e}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
            except Exception as e:
                error_msg = f"Error verifying LLM availability: {e}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
        
        elif provider == "gemini":
            # For Gemini, we could check via litellm or google-generativeai, 
            # but usually we assume cloud providers are 'available' unless credentials fail.
            # Skipping for now as it doesn't fit the /v1/models requirement as cleanly.
            pass

    async def start_graph(self) -> None:
        """Initialize the FalkorDB graph connection.

        Must be called after __init__ and before any graph operations.
        Derives graph_name from campaign name if not configured.
        """
        config = self.config.graph
        self.graph_client = await connect(config, campaign_name=self.name)
        self.world_tools.graph_client = self.graph_client
        logger.info("Graph connection established for campaign '%s'", self.name)

    async def shutdown(self) -> None:
        """Shut down the campaign, closing graph connections."""
        if self.graph_client is not None:
            await close(self.graph_client)
            self.graph_client = None
            self.world_tools.graph_client = None
            logger.info("Graph connection closed for campaign '%s'", self.name)

    # --- Campaign Logic Methods ---

    async def list_entities(self) -> List[Dict[str, Any]]:
        """List all entities as dictionaries with an added 'type' field."""
        if self.graph_client is not None:
            entities = await graph_list_entities(self.graph_client)
        else:
            entities = self.storage.list_all_entities()
        result = []
        for e in entities:
            d = e.model_dump()
            d["type"] = e.__class__.__name__
            result.append(d)
        return result

    async def get_entity_markdown(self, entity_id: str) -> Optional[str]:
        """Retrieve the markdown representation of an entity by ID."""
        if self.graph_client is not None:
            entity = await graph_get_entity(self.graph_client, entity_id)
        else:
            entities = self.storage.list_all_entities()
            entity = next((e for e in entities if e.id == entity_id), None)
        if not entity:
            return None
        return entity_to_markdown(entity)

    async def update_entity_markdown(self, entity_id: str, markdown: str) -> bool:
        """Update an entity based on its markdown representation."""
        try:
            entity = markdown_to_entity(markdown, override_id=entity_id)
            if self.graph_client is not None:
                from sidestage.graph.entities import entity_to_properties
                props = entity_to_properties(entity)
                props.pop("id", None)
                if props:
                    await graph_update_entity(self.graph_client, entity_id, props)
            else:
                if isinstance(entity, Character):
                    self.storage.update_character(entity)
                elif isinstance(entity, Location):
                    self.storage.update_location(entity)
                elif isinstance(entity, Item):
                    self.storage.update_item(entity)
                elif isinstance(entity, Scene):
                    self.storage.update_scene(entity)
            return True
        except Exception as e:
            logger.error(f"Error updating entity {entity_id}: {e}")
            return False

    async def update_entity(self, entity_id: str, data: Dict[str, Any]) -> bool:
        """Update an entity with a dictionary of fields."""
        try:
            if self.graph_client is not None:
                updates = {k: v for k, v in data.items() if k not in ("id", "type")}
                if updates:
                    await graph_update_entity(self.graph_client, entity_id, updates)
                return True

            data["id"] = entity_id
            entity_type = data.get("type")
            if not entity_type:
                existing = next((e for e in self.storage.list_all_entities() if e.id == entity_id), None)
                if existing:
                    entity_type = existing.__class__.__name__

            if entity_type == "Character":
                obj = Character(**data)
            elif entity_type == "Location":
                obj = Location(**data)
            elif entity_type == "Item":
                obj = Item(**data)
            elif entity_type == "Scene":
                obj = Scene(**data)
            else:
                raise ValueError(f"Unknown entity type: {entity_type}")

            if isinstance(obj, Character):
                self.storage.update_character(obj)
            return True
        except Exception as e:
            logger.error(f"Error updating entity {entity_id}: {e}")
            return False

    async def export_entities(self) -> int:
        """Export all entities to markdown files in the campaign directory."""
        logger.info("Exporting entities...")
        entities_dir = self.campaign_dir / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)
        if self.graph_client is not None:
            entities = await graph_list_entities(self.graph_client)
        else:
            entities = self.storage.list_all_entities()
        count = 0
        for entity in entities:
            md_content = entity_to_markdown(entity)
            filename = f"{entity.id}.md"
            (entities_dir / filename).write_text(md_content)
            count += 1
        return count

    async def import_entities(self) -> int:
        """Import all entities from markdown files in the campaign directory."""
        logger.info("Importing entities...")
        entities_dir = self.campaign_dir / "entities"
        if not entities_dir.exists():
            return 0
        count = 0
        for md_file in entities_dir.glob("*.md"):
            try:
                md_content = md_file.read_text()
                entity = markdown_to_entity(md_content)
                if self.graph_client is not None:
                    await graph_create_entity(self.graph_client, entity)
                else:
                    if isinstance(entity, Character):
                        self.storage.add_character(entity)
                    elif isinstance(entity, Location):
                        self.storage.add_location(entity)
                    elif isinstance(entity, Item):
                        self.storage.add_item(entity)
                    elif isinstance(entity, Scene):
                        self.storage.add_scene(entity)
                    elif isinstance(entity, Event):
                        self.storage.add_event(entity)
                count += 1
            except Exception as e:
                logger.error(f"Error importing {md_file.name}: {e}")
        return count

    async def list_scenes(self) -> List[Dict[str, Any]]:
        """List all scenes in the campaign."""
        if self.graph_client is not None:
            scenes = await graph_list_entities(self.graph_client, entity_type="Scene")
        else:
            scenes = self.storage.list_scenes()
        return [s.model_dump() for s in scenes]

    async def create_scene(self, name: str, description: str, current_gametime: Optional[int]) -> Scene:
        """Create and persist a new scene."""
        import uuid
        scene_id = f"scene_{str(uuid.uuid4())[:8]}"
        scene = Scene(
            id=scene_id,
            name=name,
            body=description,
            current_gametime=current_gametime
        )
        if self.graph_client is not None:
            await graph_create_entity(self.graph_client, scene)
        else:
            self.storage.add_scene(scene)
        return scene

    def get_scene_messages(self, scene_id: str) -> Optional[List[ChatMessage]]:
        """Get the message history for a specific scene."""
        scene_schema = self.storage.get_scene(scene_id)
        if not scene_schema:
            return None
        return scene_schema.messages

    def get_scene_object(self, scene_id: str) -> Optional[SceneLogic]:
        """
        Factory to get a SceneLogic object for the given ID.
        
        Args:
            scene_id (str): The scene ID.

        Returns:
            Optional[SceneLogic]: The logic object, or None if scene doesn't exist.
        """
        data = self.storage.get_scene(scene_id)
        if not data:
            return None
        return SceneLogic(self.storage, self.agent, data, graph_client=self.graph_client)
