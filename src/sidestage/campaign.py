import logging
import asyncio
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator

from opentelemetry import trace

from sidestage.agent import LiteLLMAgent
from sidestage.storage import Storage
from sidestage.tools import WorldTools
from sidestage.scene import Scene
from sidestage.models import SceneModel, CharacterModel, LocationModel, ItemModel, EntityModel, EventModel
from sidestage.schemas import ChatResponse, ChatRequest
from sidestage.actors import NPCActor, User
from sidestage.character import Character
from sidestage.entities import entity_to_markdown, markdown_to_entity
from sidestage.migration.parser import parse_directory
from sidestage.graph import GraphConfig, GraphClient, connect, close
from sidestage.health import CampaignHealth, HealthStatus
from sidestage.graph import create_entity as graph_create_entity
from sidestage.graph import get_entity as graph_get_entity
from sidestage.graph import update_entity as graph_update_entity
from sidestage.graph import list_entities as graph_list_entities
from sidestage.config import LLMConfig, SidestageConfig
from sidestage import config

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.campaign")

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

        self.config = config.get()
        
        # Storage handles SQLite connection
        self.storage = Storage(db_path=self.campaign_dir / "sidestage.db")

        self.graph_client: GraphClient | None = None
        self.health = CampaignHealth()
        self.world_tools = WorldTools(storage=self.storage, graph_client=self.graph_client)

        # Actor infrastructure
        self.characters: Dict[str, Character] = {}
        self.user = User(actor_id="user")

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

    def get_llm_config(self, name: str = "default") -> LLMConfig:
        """Get a named LLM configuration.

        Args:
            name: The LLM config name (e.g. 'default', 'embed').

        Raises:
            KeyError: If the named LLM config doesn't exist.
        """
        if name not in self.config.llms:
            raise KeyError(f"LLM config '{name}' not found. Available: {list(self.config.llms.keys())}")
        return self.config.llms[name]

    def create_agent(self) -> LiteLLMAgent:
        """
        Instantiate the main Co-Author agent based on campaign config.

        Returns:
            LiteLLMAgent: The configured agent instance.
        """
        llm = self.get_llm_config("default")
        provider = llm.provider.lower()

        if provider == "llama_cpp":
            model_name = f"openai/{llm.model}"
        elif provider == "gemini":
            model_name = f"gemini/{llm.model}"
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        return LiteLLMAgent(
            name="Sidestage Co-Author",
            model=model_name,
            api_base=llm.base_url,
            api_key=llm.api_key,
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
        self.reload_defaults()

    def reload_defaults(self) -> None:
        """
        Load default entities from data/campaign_defaults/markdown/.

        Uses the migration parser to read all entity types (characters, scenes,
        locations, items, events) and upserts them into the database.
        """
        with tracer.start_as_current_span("campaign.reload_defaults") as span:
            span.set_attribute("sidestage.scene.id", "campaign_planning")

            logger.info("Reloading default content from data directory...")

            project_root = Path(__file__).parent.parent.parent
            defaults_dir = project_root / "data" / "campaign_defaults" / "markdown"

            if not defaults_dir.exists():
                logger.warning(f"Defaults directory not found at {defaults_dir}. Skipping.")
                span.set_attribute("entities.loaded_count", 0)
                return

            result = parse_directory(defaults_dir)

            for issue in result.errors:
                logger.error(f"Error loading default: {issue.message} ({issue.file_path})")
            for issue in result.warnings:
                logger.warning(f"Warning loading default: {issue.message} ({issue.file_path})")

            count = 0
            for entity in result.entities:
                try:
                    if isinstance(entity, CharacterModel):
                        self.storage.add_character(entity)
                    elif isinstance(entity, LocationModel):
                        self.storage.add_location(entity)
                    elif isinstance(entity, ItemModel):
                        self.storage.add_item(entity)
                    elif isinstance(entity, SceneModel):
                        self.storage.add_scene(entity)
                    elif isinstance(entity, EventModel):
                        self.storage.add_event(entity)
                    count += 1
                    logger.info(f"Loaded default {entity.entity_type}: {entity.name} ({entity.id})")
                except Exception as e:
                    logger.error(f"Error loading default entity {entity.id}: {e}")

            span.set_attribute("entities.loaded_count", count)

    def _ensure_llm_availability(self) -> None:
        """
        Verify that the default LLM endpoint is reachable and the model exists.

        Checks /health for liveness, then /models for model availability.

        Raises:
            RuntimeError: If the LLM is unreachable or the model is missing.
        """
        llm = self.get_llm_config("default")
        provider = llm.provider.lower()

        if provider == "gemini":
            # Cloud providers: assume available unless credentials fail at call time.
            return

        base_url = llm.base_url.rstrip("/")
        # Derive server root from base_url (strip /v1 suffix if present)
        server_root = base_url.rsplit("/v1", 1)[0] if "/v1" in base_url else base_url

        # 1. Health check
        health_url = f"{server_root}/health"
        try:
            logger.info(f"Checking LLM health at {health_url}...")
            resp = httpx.get(health_url, timeout=10.0)
            resp.raise_for_status()
        except httpx.RequestError as e:
            raise RuntimeError(f"LLM unreachable at {health_url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"LLM health check failed at {health_url}: {e}") from e

        # 2. Model availability
        models_url = f"{base_url}/models"
        target_model = llm.model
        try:
            logger.info(f"Checking model '{target_model}' at {models_url}...")
            resp = httpx.get(models_url, timeout=10.0)
            resp.raise_for_status()

            data = resp.json()
            available_models = data.get("data", [])
            available_ids = [m.get("id") for m in available_models if m.get("id")]

            if target_model not in available_ids:
                raise RuntimeError(
                    f"Model '{target_model}' not found at {models_url}. Available: {available_ids}"
                )

            logger.info(f"LLM verified: '{target_model}' is online.")

        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to query models at {models_url}: {e}") from e

        # 3. Completions probe — catches dead backend workers behind a proxy
        completions_url = f"{base_url}/chat/completions"
        try:
            logger.info(f"Probing completions endpoint at {completions_url}...")
            resp = httpx.post(
                completions_url,
                json={
                    "model": target_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                headers={"Authorization": f"Bearer {llm.api_key}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            logger.info("Completions probe succeeded.")
        except httpx.RequestError as e:
            raise RuntimeError(
                f"LLM completions probe failed at {completions_url} (server may have a dead worker): {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"LLM completions probe returned error at {completions_url}: {e}"
            ) from e

    async def start_graph(self) -> None:
        """Initialize the FalkorDB graph connection.

        Must be called after __init__ and before any graph operations.
        Derives graph_name from campaign name if not configured.
        """
        config = self.config.graph
        self.graph_client = await connect(config, campaign_name=self.name)
        self.world_tools.graph_client = self.graph_client

        # Validate embed config if present
        if "embed" in self.config.llms:
            embed_llm = self.get_llm_config("embed")
            from sidestage.memory.embeddings import validate_embed_config
            dimension = await validate_embed_config(embed_llm)
            if dimension is not None:
                config.vector_dimension = dimension
                logger.info("Embedding validated: dimension=%d", dimension)
            else:
                logger.warning("Embedding validation failed")
                await self.health.set_status(HealthStatus.DEGRADED, "Embedding unavailable")

        logger.info("Graph connection established for campaign '%s'", self.name)

    async def shutdown(self) -> None:
        """Shut down the campaign, closing graph connections."""
        self.characters = {}
        if self.graph_client is not None:
            await close(self.graph_client)
            self.graph_client = None
            self.world_tools.graph_client = None
            logger.info("Graph connection closed for campaign '%s'", self.name)

    # --- Character Registry ---

    def get_character(self, model: CharacterModel) -> Character:
        """Get or create a Character instance for the given model."""
        if model.id in self.characters:
            return self.characters[model.id]
        actor = self._resolve_actor(model)
        char = Character(model=model, actor=actor)
        self.characters[model.id] = char
        return char

    def _resolve_actor(self, model: CharacterModel):
        """Determine which Actor controls this character."""
        if model.owner == "npc":
            return NPCActor(
                actor_id=f"agent:{model.id}",
                system_actor=model.system_actor,
            )
        else:
            return self.user

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
            d["type"] = e.entity_type
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
                if isinstance(entity, CharacterModel):
                    self.storage.update_character(entity)
                elif isinstance(entity, LocationModel):
                    self.storage.update_location(entity)
                elif isinstance(entity, ItemModel):
                    self.storage.update_item(entity)
                elif isinstance(entity, SceneModel):
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
                    entity_type = existing.entity_type

            if entity_type == "Character":
                obj = CharacterModel(**data)
            elif entity_type == "Location":
                obj = LocationModel(**data)
            elif entity_type == "Item":
                obj = ItemModel(**data)
            elif entity_type == "Scene":
                obj = SceneModel(**data)
            else:
                raise ValueError(f"Unknown entity type: {entity_type}")

            if isinstance(obj, CharacterModel):
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
                    if isinstance(entity, CharacterModel):
                        self.storage.add_character(entity)
                    elif isinstance(entity, LocationModel):
                        self.storage.add_location(entity)
                    elif isinstance(entity, ItemModel):
                        self.storage.add_item(entity)
                    elif isinstance(entity, SceneModel):
                        self.storage.add_scene(entity)
                    elif isinstance(entity, EventModel):
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

    async def create_scene(self, name: str, description: str, current_gametime: Optional[int]) -> SceneModel:
        """Create and persist a new scene."""
        import uuid
        scene_id = f"scene_{str(uuid.uuid4())[:8]}"
        scene = SceneModel(
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

    def get_scene_events(self, scene_id: str) -> Optional[List[str]]:
        """Get the event IDs for a specific scene."""
        scene_schema = self.storage.get_scene(scene_id)
        if not scene_schema:
            return None
        return scene_schema.events

    def get_scene_object(self, scene_id: str) -> Optional[Scene]:
        """
        Factory to get a Scene object for the given ID.
        
        Args:
            scene_id (str): The scene ID.

        Returns:
            Optional[Scene]: The logic object, or None if scene doesn't exist.
        """
        data = self.storage.get_scene(scene_id)
        if not data:
            return None
        embed_config = self.config.llms.get("embed")
        default_llm = self.get_llm_config("default")
        context_limit = getattr(default_llm, "context_limit", None) or 4096
        return Scene(
            self.storage, self.agent, data,
            graph_client=self.graph_client,
            embed_config=embed_config,
            health=self.health,
            context_limit=context_limit,
        )
