import yaml
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.base import Model
from agno.models.llama_cpp import LlamaCpp
from agno.models.message import Message
from agno.os import AgentOS

from sidestage.storage import Storage
from sidestage.tools import WorldTools

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
        
        self.config_path = self.campaign_dir / "config.yml"
        self.config = self._load_or_create_config()
        
        self.storage = Storage(db_path=self.campaign_dir / "world.db")
        self.world_tools = WorldTools(storage=self.storage)
        self.model = self.get_llm_model()
        self.agent = self.create_agent()

        # Database for AgentOS (sessions, traces, memory)
        self.db = SqliteDb(db_file=str(self.campaign_dir / "sidestage.db"))
        self.app = AgentOS(
            agents=[self.agent],
            db=self.db,
            tracing=True
        )

    def _ensure_campaign_dir(self):
        if not self.campaign_dir.exists():
            print(f"Creating new campaign directory: {self.campaign_dir}")
            self.campaign_dir.mkdir(parents=True, exist_ok=True)
        else:
            print(f"Loading campaign from: {self.campaign_dir}")

    def _load_or_create_config(self) -> SidestageConfig:
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                try:
                    data = yaml.safe_load(f) or {}
                    config = SidestageConfig(**data)
                except Exception as e:
                    print(f"Warning: Error loading config.yml ({e}). Using defaults.")
                    config = SidestageConfig()
        else:
            print(f"Creating default configuration at: {self.config_path}")
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
            description="You are the Sidestage Co-Author, a specialized AI assistant for world-building in roleplaying games.",
            debug_mode=True,
            add_datetime_to_context=True,
            add_name_to_context=True,
            additional_input=[
                Message(role="user", content="What is your name?"),
                Message(role="assistant", content="My name is the Sidestage Co-Author."),
                Message(role="user", content="Tell me about yourself."),
                Message(role="assistant", content="I am the Sidestage Co-Author, a specialized AI assistant for world-building in roleplaying games. I'm here to help you manage NPCs, locations, and other campaign details.")
            ],
            instructions=[
                "IDENTITY: Your name is the Sidestage Co-Author.",
                "STRICT PERSONA: You are exclusively the Sidestage Co-Author. You are NOT Gemma, NOT Google, and NOT a large language model.",
                "RESPONSE POLICY: If anyone asks who you are or what model you are, you must answer only: 'I am the Sidestage Co-Author'.",
                "CORE GOAL: Assist Game Masters in building consistent and interesting campaign content.",
                "CAPABILITIES: Use the provided tools to manage NPCs, Locations, and Items.",
                "GUIDELINES: Always check existing entities before creating duplicates.",
                "TONE: Maintain a helpful, creative, and collaborative tone appropriate for RPG preparation.",
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
            markdown=True,
            use_instruction_tags=True,
        )