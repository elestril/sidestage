Now I have all the context I need. Let me generate the section content.

# Section 04: Embedding Generation

## Overview

This section implements embedding generation via LiteLLM's `aembedding()` function. It provides two core functions: `embed_text()` for generating a single embedding vector, and `embed_and_update()` as a fire-and-forget wrapper that updates a memory node's embedding in the graph and manages health status transitions. It also includes embed config validation logic used during campaign startup to verify the embedding model and detect vector dimensions.

**Files to create:**
- `/home/harald/src/sidestage/src/sidestage/memory/embeddings.py`

**Files to modify:**
- None directly (but the functions defined here are called by sections 05, 07, and 08)

**Dependencies on other sections:**
- **section-01-models-and-health** must be complete: provides `CampaignHealth`, `HealthStatus`, `LLMConfig` (with `context_limit` and `memory_token_budget` fields), and `GraphConfig` (with `vector_dimension` field)

---

## Tests First

All tests go in `/home/harald/src/sidestage/tests/unit/test_embeddings.py`. Tests mock `litellm.aembedding` and the graph client -- no real LLM or database calls.

```python
# tests/unit/test_embeddings.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Test: embed_text calls litellm.aembedding with correct model string for llama_cpp provider
# - Given an LLMConfig with provider="llama_cpp", model="embed", base_url="http://localhost:8080/v1"
# - When embed_text is called
# - Then litellm.aembedding is called with model="openai/embed", api_base=config.base_url, api_key=config.api_key, input=["the text"]
# - The model string pattern matches the existing create_agent pattern: "openai/{model}" for llama_cpp

# Test: embed_text calls litellm.aembedding with correct model string for gemini provider
# - Given an LLMConfig with provider="gemini", model="text-embedding-004"
# - When embed_text is called
# - Then litellm.aembedding is called with model="gemini/text-embedding-004"

# Test: embed_text returns list of floats from successful response
# - Mock litellm.aembedding to return a response object with data[0].embedding = [0.1, 0.2, 0.3]
# - Assert embed_text returns [0.1, 0.2, 0.3]

# Test: embed_text raises EmbeddingError on litellm failure
# - Mock litellm.aembedding to raise an Exception
# - Assert embed_text raises EmbeddingError with the original message

# Test: embed_text raises EmbeddingError on timeout
# - Mock litellm.aembedding to raise asyncio.TimeoutError
# - Assert embed_text raises EmbeddingError

# Test: embed_and_update updates memory node embedding on success (mock store)
# - Mock embed_text to return a vector
# - Mock the graph client's query method
# - Assert the graph is queried with a MATCH/SET to update the Memory node's embedding field
# - Assert the memory_id is used correctly in the query parameters

# Test: embed_and_update transitions health to DEGRADED on failure
# - Mock embed_text to raise EmbeddingError
# - Provide a CampaignHealth instance (from section-01)
# - After embed_and_update runs, assert health.status == HealthStatus.DEGRADED

# Test: embed_and_update transitions health back to HEALTHY on success after prior failure
# - Create CampaignHealth, set it to DEGRADED
# - Mock embed_text to succeed
# - After embed_and_update runs, assert health.status == HealthStatus.HEALTHY

# Test: embed_and_update does not crash when health callback is None
# - Create CampaignHealth with on_change=None
# - Mock embed_text to raise EmbeddingError
# - Assert embed_and_update completes without raising
```

### Key testing notes

- The `litellm.aembedding` response object follows the OpenAI embedding response format: the response has a `data` attribute which is a list; each item has an `embedding` attribute containing a `list[float]`.
- Use `unittest.mock.patch("litellm.aembedding", new_callable=AsyncMock)` to mock the async call.
- `embed_and_update` is designed to be called as a fire-and-forget `asyncio.Task`. In tests, call it directly (awaited) to verify behavior.
- The `CampaignHealth` class comes from section-01 (`/home/harald/src/sidestage/src/sidestage/health.py`). For tests, import it directly; it is a plain Python class with no external dependencies.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/memory/embeddings.py`

#### EmbeddingError Exception

```python
class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
```

A simple exception class. All embedding failures (network errors, provider errors, timeouts) are wrapped into this exception type by `embed_text()`.

#### `embed_text()` Function

```python
async def embed_text(config: LLMConfig, text: str) -> list[float]:
    """Generate embedding for a single text using LiteLLM aembedding().

    Builds model string from config provider and model name using
    the same pattern as Campaign.create_agent():
      - provider="llama_cpp" -> model="openai/{config.model}"
      - provider="gemini"    -> model="gemini/{config.model}"

    Calls litellm.aembedding() with:
      - model: the constructed model string
      - input: [text]  (single-element list)
      - api_base: config.base_url (for local providers)
      - api_key: config.api_key

    Returns the embedding vector (list[float]) from response.data[0].embedding.

    Raises:
        EmbeddingError: On any failure (provider error, timeout, network error).
    """
```

**Model string construction logic** (mirrors `Campaign.create_agent()`):

| Provider | Model string |
|----------|-------------|
| `llama_cpp` | `openai/{config.model}` |
| `gemini` | `gemini/{config.model}` |
| Other | Raise `EmbeddingError(f"Unknown provider: {provider}")` |

**LiteLLM aembedding call pattern:**
- Import `litellm` at the module level
- Call `await litellm.aembedding(model=model_string, input=[text], api_base=config.base_url, api_key=config.api_key)`
- Extract the vector: `response.data[0].embedding`
- Wrap any exception in `EmbeddingError`

**Error handling:**
- Catch `Exception` broadly (LiteLLM can raise various error types)
- Also catch `asyncio.TimeoutError` explicitly
- Re-raise as `EmbeddingError` with a descriptive message including the original error

#### `embed_and_update()` Function

```python
async def embed_and_update(
    client: GraphClient,
    config: LLMConfig,
    memory_id: str,
    text: str,
    health: CampaignHealth,
) -> None:
    """Generate embedding and update the memory node. Fire-and-forget.

    Steps:
    1. Call embed_text(config, text) to generate the embedding vector
    2. On success:
       a. Update the Memory node in FalkorDB:
          MATCH (m:Memory {id: $memory_id}) SET m.embedding = vecf32($embedding)
       b. If health was DEGRADED, transition to HEALTHY
    3. On failure (EmbeddingError):
       a. Log warning with memory_id and error message
       b. Transition health to DEGRADED with reason
       c. Do NOT re-raise — the memory remains without embedding

    This function is designed to be wrapped in asyncio.create_task() by callers
    (memory tools). It must never raise — all errors are caught and logged.

    Args:
        client: Active FalkorDB graph client
        config: LLM configuration for embedding provider
        memory_id: ID of the Memory node to update
        text: Text content to embed
        health: CampaignHealth instance for status transitions
    """
```

**Cypher query for updating embedding:**

The embedding vector must be stored using FalkorDB's `vecf32()` function for proper vector serialization. The Cypher query:

```cypher
MATCH (m:Memory {id: $memory_id})
SET m.embedding = vecf32($embedding)
```

Where `$embedding` is the list of floats returned by `embed_text()`.

**Important note on `vecf32()`:** FalkorDB requires vector data to be wrapped in `vecf32()` within the Cypher query for proper binary vector storage. Check whether the Python client version supports passing a list directly as a parameter or whether the vector needs to be serialized differently. If parameterized `vecf32()` does not work, construct the vector literal inline (comma-separated floats inside `vecf32([...])`) -- but prefer parameterized form for safety.

**Health transitions:**
- On success: call `await health.set_status(HealthStatus.HEALTHY, "Embedding generation succeeded")` -- but only if health is currently DEGRADED. The `set_status` method already handles no-op when the status hasn't changed, so calling it unconditionally is safe.
- On failure: call `await health.set_status(HealthStatus.DEGRADED, f"Embedding failed: {error_message}")`

**Logging:**
- On success: `logger.debug("Embedding updated for memory %s", memory_id)`
- On failure: `logger.warning("Embedding failed for memory %s: %s", memory_id, error_message)`

**Error containment:**
- The entire function body is wrapped in a `try/except Exception` to ensure it never raises.
- This is critical because callers fire it as a background task via `asyncio.create_task()`.

#### Embed Config Validation (helper for Campaign startup)

This logic is called from `Campaign.start_graph()` (implemented in section-07/08) but the validation function itself lives in the embeddings module.

```python
async def validate_embed_config(config: LLMConfig) -> int | None:
    """Validate embed configuration and detect vector dimension.

    Steps:
    1. Build model string from config (same pattern as embed_text)
    2. For local providers (llama_cpp):
       - Hit {base_url}/models to verify the embedding model is available
       - If model not found, return None (caller should degrade gracefully)
    3. For cloud providers (gemini): skip endpoint validation
    4. Make a test embedding call with probe text "dimension probe"
    5. Return len(embedding) as the detected vector dimension

    Returns:
        The vector dimension (int) on success, or None on failure.
        Logs warnings on failure but does not raise.
    """
```

This function:
- Uses `httpx` for the `/models` endpoint check (same pattern as `Campaign._ensure_llm_availability()`)
- Calls `embed_text()` with a short probe string
- Returns the length of the resulting vector (this is the dimension)
- Catches all exceptions, logs warnings, and returns `None` on failure
- The caller (`Campaign.start_graph()` in section-07/08) uses the returned dimension to set `GraphConfig.vector_dimension` and decide whether to create the vector index

---

## Module Structure

The file should import from:

```python
import asyncio
import logging

import httpx
import litellm

from sidestage.campaign import LLMConfig  # From section-01 (LLMConfig with new fields)
from sidestage.graph.client import GraphClient
from sidestage.health import CampaignHealth, HealthStatus  # From section-01
```

Note: The `LLMConfig` import path is `sidestage.campaign` since that is where it is currently defined. If section-01 moves it, adjust accordingly. The `CampaignHealth` and `HealthStatus` imports come from `sidestage.health` (created in section-01).

---

## Package Init

The `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` file should be created (if not already by a prior section) and should export:

```python
from sidestage.memory.embeddings import embed_text, embed_and_update, EmbeddingError, validate_embed_config
```

If this file already exists from section-01 or section-03, add these exports to it.

---

## How Callers Use These Functions

For context (implemented in other sections, not this one):

1. **Memory tools** (section-05) call `embed_and_update()` via `asyncio.create_task()` after each memory upsert:
   ```python
   asyncio.create_task(embed_and_update(client, config, memory.id, memory.content, health))
   ```

2. **Campaign startup** (section-07/08) calls `validate_embed_config()` to detect dimensions:
   ```python
   if "embed" in self.config.llms:
       dim = await validate_embed_config(self.get_llm_config("embed"))
       if dim:
           self.config.graph.vector_dimension = dim
   ```

3. **Vector search** (section-03) uses `embed_text()` to embed a query string before calling `search_similar()`.

---

## Error Handling Philosophy

- **embed_text()** raises `EmbeddingError` -- callers are expected to handle it
- **embed_and_update()** catches all errors internally -- never raises, safe for fire-and-forget
- **validate_embed_config()** catches all errors, returns `None` on failure -- campaign starts gracefully without embeddings
- Health status transitions communicate embedding availability to the rest of the system without exceptions