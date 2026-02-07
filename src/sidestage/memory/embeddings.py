"""Embedding generation via LiteLLM for the sidestage memory system."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import litellm

from sidestage.campaign import LLMConfig
from sidestage.health import CampaignHealth, HealthStatus

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

_PROVIDER_PREFIX: dict[str, str] = {
    "llama_cpp": "openai",
    "gemini": "gemini",
}


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


def _build_model_string(config: LLMConfig) -> str:
    """Build LiteLLM model string from config provider and model name."""
    prefix = _PROVIDER_PREFIX.get(config.provider)
    if prefix is None:
        raise EmbeddingError(f"Unknown provider: {config.provider}")
    return f"{prefix}/{config.model}"


async def embed_text(config: LLMConfig, text: str) -> list[float]:
    """Generate embedding for a single text using LiteLLM aembedding().

    Returns the embedding vector (list[float]).

    Raises:
        EmbeddingError: On any failure (provider error, timeout, network error).
    """
    model_string = _build_model_string(config)

    try:
        response = await litellm.aembedding(
            model=model_string,
            input=[text],
            api_base=config.base_url,
            api_key=config.api_key,
        )
    except asyncio.TimeoutError as exc:
        raise EmbeddingError(f"Embedding timed out: {exc}") from exc
    except Exception as exc:
        raise EmbeddingError(f"Embedding failed: {exc}") from exc

    return response.data[0].embedding


async def embed_and_update(
    client: GraphClient,
    config: LLMConfig,
    memory_id: str,
    text: str,
    health: CampaignHealth,
) -> None:
    """Generate embedding and update the memory node. Fire-and-forget.

    Never raises -- all errors are caught and logged. Designed to be
    wrapped in asyncio.create_task() by callers.
    """
    try:
        embedding = await embed_text(config, text)

        cypher = (
            "MATCH (m:Memory {id: $memory_id})\n"
            "SET m.embedding = vecf32($embedding)"
        )
        await client.graph.query(cypher, params={
            "memory_id": memory_id,
            "embedding": embedding,
        })

        logger.debug("Embedding updated for memory %s", memory_id)
        if health.status == HealthStatus.DEGRADED:
            await health.set_status(HealthStatus.HEALTHY, "Embedding generation succeeded")

    except EmbeddingError as exc:
        logger.warning("Embedding failed for memory %s: %s", memory_id, exc)
        await health.set_status(HealthStatus.DEGRADED, f"Embedding failed: {exc}")

    except Exception as exc:
        logger.warning("Unexpected error in embed_and_update for memory %s: %s", memory_id, exc)
        await health.set_status(HealthStatus.DEGRADED, f"Embedding failed: {exc}")


async def validate_embed_config(config: LLMConfig) -> int | None:
    """Validate embed configuration and detect vector dimension.

    Makes a test embedding call with probe text. Returns the vector
    dimension on success, or None on failure.
    """
    try:
        embedding = await embed_text(config, "dimension probe")
        return len(embedding)
    except EmbeddingError as exc:
        logger.warning("Embed config validation failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error validating embed config: %s", exc)
        return None
