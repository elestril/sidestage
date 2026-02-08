import logging
import yaml
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field

from sidestage.graph import GraphConfig

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    """Configuration for a single LLM endpoint."""
    provider: str = Field(default="llama_cpp", description="LLM provider: 'llama_cpp' or 'gemini'")
    base_url: str = Field(default="http://localhost:8080/v1", description="Base URL for OpenAI-compatible API")
    api_key: str = Field(default="sk-no-key-required", description="API key")
    model: str = Field(default="default", description="Model name to request")
    context_limit: int | None = Field(default=None, ge=1, description="Max context tokens (validated at startup)")
    memory_token_budget: int | None = Field(default=None, ge=1, description="Tokens allocated for memory context (optional override)")


class TraceConfig(BaseModel):
    """Configuration for the tracing subsystem."""
    enabled: bool = False
    capture_prompts: bool = True
    capture_tool_args: bool = True
    capture_memory_content: bool = True
    max_attribute_length: int = Field(default=4096, ge=1)
    max_traces_in_memory: int = Field(default=500, ge=1)
    max_traces_stored: int = Field(default=5000, ge=1)
    max_trace_age_hours: int = Field(default=72, ge=1)


class SidestageConfig(BaseModel):
    """Configuration model for Sidestage settings."""
    loglevel: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    llms: Dict[str, LLMConfig] = Field(
        default_factory=lambda: {"default": LLMConfig()},
        description="Named LLM configurations"
    )

    # Graph Database Configuration
    graph: GraphConfig = Field(default_factory=GraphConfig, description="FalkorDB graph database configuration")

    # Tracing Configuration
    tracing: TraceConfig = Field(default_factory=TraceConfig, description="Tracing configuration")


_instance: Optional[SidestageConfig] = None


def init(sidestage_dir: Path) -> SidestageConfig:
    """Load config from sidestage_dir/config.yml and set as global singleton.

    Creates the config file with defaults if it doesn't exist.
    """
    global _instance
    config_path = sidestage_dir / "config.yml"

    if config_path.exists():
        with open(config_path, "r") as f:
            try:
                data = yaml.safe_load(f) or {}
                config = SidestageConfig(**data)
            except Exception as e:
                logger.warning(f"Error loading config.yml ({e}). Using defaults.")
                config = SidestageConfig()
    else:
        logger.info(f"Creating default configuration at: {config_path}")
        sidestage_dir.mkdir(parents=True, exist_ok=True)
        config = SidestageConfig()

    # Persist the config (fills in defaults for new fields)
    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)

    _instance = config
    return config


def get() -> SidestageConfig:
    """Get the global config singleton.

    Raises:
        RuntimeError: If init() has not been called yet.
    """
    if _instance is None:
        raise RuntimeError("SidestageConfig not initialized. Call config.init() first.")
    return _instance
