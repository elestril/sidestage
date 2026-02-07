"""Unit tests for embedding generation and update logic."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sidestage.campaign import LLMConfig
from sidestage.health import CampaignHealth, HealthStatus
from sidestage.memory.embeddings import (
    EmbeddingError,
    embed_text,
    embed_and_update,
    validate_embed_config,
)


# --- Fixtures ---


@pytest.fixture
def llama_config():
    return LLMConfig(
        provider="llama_cpp",
        model="embed",
        base_url="http://localhost:8080/v1",
        api_key="sk-no-key-required",
    )


@pytest.fixture
def gemini_config():
    return LLMConfig(
        provider="gemini",
        model="text-embedding-004",
        base_url="",
        api_key="test-api-key",
    )


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client


@pytest.fixture
def health():
    return CampaignHealth()


def _make_embedding_response(embedding):
    """Create a mock LiteLLM embedding response."""
    data_item = MagicMock()
    data_item.embedding = embedding
    response = MagicMock()
    response.data = [data_item]
    return response


# --- embed_text tests ---


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.litellm.aembedding", new_callable=AsyncMock)
async def test_embed_text_llama_cpp_model_string(mock_aembedding, llama_config):
    """embed_text calls litellm.aembedding with correct model string for llama_cpp provider."""
    mock_aembedding.return_value = _make_embedding_response([0.1, 0.2, 0.3])

    await embed_text(llama_config, "hello world")

    mock_aembedding.assert_awaited_once()
    call_kwargs = mock_aembedding.call_args[1]
    assert call_kwargs["model"] == "openai/embed"
    assert call_kwargs["api_base"] == "http://localhost:8080/v1"


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.litellm.aembedding", new_callable=AsyncMock)
async def test_embed_text_gemini_model_string(mock_aembedding, gemini_config):
    """embed_text calls litellm.aembedding with correct model string for gemini provider."""
    mock_aembedding.return_value = _make_embedding_response([0.1, 0.2])

    await embed_text(gemini_config, "hello")

    call_kwargs = mock_aembedding.call_args[1]
    assert call_kwargs["model"] == "gemini/text-embedding-004"


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.litellm.aembedding", new_callable=AsyncMock)
async def test_embed_text_returns_float_list(mock_aembedding, llama_config):
    """embed_text returns list of floats from successful response."""
    mock_aembedding.return_value = _make_embedding_response([0.1, 0.2, 0.3])

    result = await embed_text(llama_config, "test text")

    assert result == [0.1, 0.2, 0.3]


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.litellm.aembedding", new_callable=AsyncMock)
async def test_embed_text_raises_on_failure(mock_aembedding, llama_config):
    """embed_text raises EmbeddingError on litellm failure."""
    mock_aembedding.side_effect = Exception("API error")

    with pytest.raises(EmbeddingError, match="API error"):
        await embed_text(llama_config, "test")


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.litellm.aembedding", new_callable=AsyncMock)
async def test_embed_text_raises_on_timeout(mock_aembedding, llama_config):
    """embed_text raises EmbeddingError on timeout."""
    mock_aembedding.side_effect = asyncio.TimeoutError()

    with pytest.raises(EmbeddingError):
        await embed_text(llama_config, "test")


# --- embed_and_update tests ---


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_embed_and_update_updates_memory(mock_embed, mock_client, llama_config, health):
    """embed_and_update updates memory node embedding on success."""
    mock_embed.return_value = [0.1, 0.2, 0.3]

    await embed_and_update(mock_client, llama_config, "mem-1", "test text", health)

    mock_client.graph.query.assert_awaited_once()
    cypher = mock_client.graph.query.call_args[0][0]
    assert "Memory" in cypher
    assert "embedding" in cypher
    params = mock_client.graph.query.call_args[1].get("params", {})
    assert params["memory_id"] == "mem-1"


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_embed_and_update_degrades_health_on_failure(mock_embed, mock_client, llama_config, health):
    """embed_and_update transitions health to DEGRADED on failure."""
    mock_embed.side_effect = EmbeddingError("failed")

    await embed_and_update(mock_client, llama_config, "mem-1", "test", health)

    assert health.status == HealthStatus.DEGRADED


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_embed_and_update_recovers_health_on_success(mock_embed, mock_client, llama_config, health):
    """embed_and_update transitions health back to HEALTHY on success after prior failure."""
    await health.set_status(HealthStatus.DEGRADED, "prior failure")
    mock_embed.return_value = [0.1, 0.2]

    await embed_and_update(mock_client, llama_config, "mem-1", "test", health)

    assert health.status == HealthStatus.HEALTHY


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_embed_and_update_no_crash_without_callback(mock_embed, mock_client, llama_config):
    """embed_and_update does not crash when health callback is None."""
    health = CampaignHealth(on_change=None)
    mock_embed.side_effect = EmbeddingError("failed")

    # Should not raise
    await embed_and_update(mock_client, llama_config, "mem-1", "test", health)


# --- validate_embed_config tests ---


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_validate_embed_config_returns_dimension(mock_embed, llama_config):
    """validate_embed_config returns vector dimension on success."""
    mock_embed.return_value = [0.1] * 384

    result = await validate_embed_config(llama_config)

    assert result == 384


@pytest.mark.anyio
@patch("sidestage.memory.embeddings.embed_text", new_callable=AsyncMock)
async def test_validate_embed_config_returns_none_on_failure(mock_embed, llama_config):
    """validate_embed_config returns None on embed failure."""
    mock_embed.side_effect = EmbeddingError("no model")

    result = await validate_embed_config(llama_config)

    assert result is None
