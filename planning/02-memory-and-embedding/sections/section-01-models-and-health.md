Now I have all the context I need. Let me generate the section content.

# Section 01: Models and Health

This section implements the foundational types and health system that all subsequent sections depend on. It covers three areas:

1. **Memory Pydantic models** -- `Memory`, `MemoryType`, `ContextResult`, `ContextMemories`
2. **Campaign health system** -- `HealthStatus` enum and `CampaignHealth` class
3. **Config field extensions** -- new fields on `LLMConfig` and `GraphConfig`

No other section content is duplicated here. Later sections (schema migration, store, embeddings, tools, context assembly, agent and scene integration) build on these types.

---

## Dependencies

- None. This is the first section and has no prerequisites.

---

## Files to Create

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` | Package init with public re-exports |
| `/home/harald/src/sidestage/src/sidestage/memory/models.py` | Memory, MemoryType, ContextResult, ContextMemories |
| `/home/harald/src/sidestage/src/sidestage/health.py` | HealthStatus, CampaignHealth |

## Files to Modify

| File | What Changes |
|------|-------------|
| `/home/harald/src/sidestage/src/sidestage/campaign.py` | Add `context_limit` and `memory_token_budget` fields to `LLMConfig` |
| `/home/harald/src/sidestage/src/sidestage/graph/client.py` | Add `vector_dimension` field to `GraphConfig` |

---

## Tests First

All tests are pure unit tests (no database, no network). They use standard `pytest` and Pydantic model construction.

### Test file: `/home/harald/src/sidestage/tests/unit/test_memory_models.py`

```python
# tests/unit/test_memory_models.py

# Test: Memory model validates all required fields
# - Construct a Memory with all required fields, assert no validation errors.

# Test: Memory model accepts None for optional fields (embedding, owner_id, gametime, last_accessed_at)
# - Construct a Memory with those fields set to None, assert valid.

# Test: MemoryType enum has correct values (scene, character, world_fact)
# - Assert MemoryType.SCENE == "scene", MemoryType.CHARACTER == "character",
#   MemoryType.WORLD_FACT == "world_fact".

# Test: Memory with visibility="common" and owner_id=None is valid
# - Construct such a Memory, assert no error.

# Test: Memory with visibility="private" and owner_id set is valid
# - Construct such a Memory, assert no error.

# Test: Memory serialization round-trip (model_dump / model construction)
# - Construct a Memory, dump to dict, reconstruct from dict, assert equal.

# Test: ContextResult model has memory_text, chat_text, token_estimate fields
# - Construct a ContextResult with sample values, assert fields are accessible.

# Test: ContextMemories model groups memories correctly
# - Construct a ContextMemories with common_scene_memory, private_scene_memory (both Memory | None),
#   character_memories (dict[str, Memory]), and world_facts (list[Memory]).
#   Assert each field returns the correct value.
```

### Test file: `/home/harald/src/sidestage/tests/unit/test_health.py`

```python
# tests/unit/test_health.py

import pytest

# Test: CampaignHealth initializes with HEALTHY status
# - Construct CampaignHealth(), assert status == HealthStatus.HEALTHY.

# Test: set_status transitions status and stores reason
# - Create health, call await health.set_status(HealthStatus.DEGRADED, "embed down"),
#   assert health.status == DEGRADED and health.reason == "embed down".

# Test: set_status fires on_change callback when status changes
# - Create health with an AsyncMock on_change, transition HEALTHY -> DEGRADED,
#   assert on_change was awaited once with (HealthStatus.DEGRADED, "reason").

# Test: set_status does not fire on_change when status unchanged
# - Create health already at HEALTHY, call set_status(HEALTHY, "still fine"),
#   assert on_change was NOT called.

# Test: set_status works when on_change is None
# - Create health without callback, transition status, no crash.

# Test: is_accepting_chat returns True for HEALTHY
# Test: is_accepting_chat returns True for DEGRADED
# Test: is_accepting_chat returns False for UNHEALTHY
# - For each status, set it and check the property.

# Test: is_embedding_available returns True for HEALTHY
# Test: is_embedding_available returns False for DEGRADED
# Test: is_embedding_available returns False for UNHEALTHY
# - For each status, set it and check the property.
```

### Test file: `/home/harald/src/sidestage/tests/unit/test_campaign_config.py`

```python
# tests/unit/test_campaign_config.py

# Test: LLMConfig accepts context_limit field
# - Construct LLMConfig(context_limit=16384), assert context_limit == 16384.

# Test: LLMConfig accepts memory_token_budget field
# - Construct LLMConfig(memory_token_budget=2000), assert memory_token_budget == 2000.

# Test: LLMConfig defaults context_limit and memory_token_budget to None
# - Construct LLMConfig(), assert both are None.

# Test: GraphConfig accepts vector_dimension field
# - Construct GraphConfig(vector_dimension=384), assert vector_dimension == 384.

# Test: GraphConfig defaults vector_dimension to None
# - Construct GraphConfig(), assert vector_dimension is None.

# Test: SidestageConfig serialization includes new fields
# - Construct SidestageConfig with llms containing context_limit and graph with vector_dimension,
#   call model_dump(), assert new fields appear in output.

# Test: Existing config files without new fields load without error (backwards compat)
# - Construct SidestageConfig from a dict that has no context_limit, memory_token_budget,
#   or vector_dimension. Assert no validation error and defaults are None.
```

---

## Implementation Details

### 1. Memory Models (`/home/harald/src/sidestage/src/sidestage/memory/models.py`)

This file defines the core data types used throughout the memory system. All are Pydantic `BaseModel` subclasses.

**`MemoryType` enum:**

```python
class MemoryType(str, Enum):
    SCENE = "scene"
    CHARACTER = "character"
    WORLD_FACT = "world_fact"
```

A `str, Enum` so it serializes cleanly to/from JSON and Cypher property strings.

**`Memory` model:**

```python
class Memory(BaseModel):
    id: str                         # UUID string
    content: str                    # Human-readable text (the "living document")
    memory_type: MemoryType         # Discriminator
    visibility: str                 # "common" or "private" (plain str for future extensibility)
    embedding: list[float] | None   # Vector, None if pending or failed
    owner_id: str | None            # Character/actor ID who owns this. None for common memories.
    target_id: str                  # Scene ID, Character ID, or Entity ID (what this memory is ABOUT)
    created_at: float               # Unix timestamp
    updated_at: float               # Unix timestamp
    gametime: int | None            # Game time when last updated
    access_count: int               # Incremented on retrieval
    last_accessed_at: float | None  # Timestamp of last retrieval
```

All fields are typed with sensible defaults where appropriate. The `visibility` field is deliberately a plain `str` rather than an enum, to allow future extension to richer ACL values without a schema migration.

**`ContextResult` model:**

```python
class ContextResult(BaseModel):
    memory_text: str      # Formatted world facts + scene memories + character memories
    chat_text: str        # Recent verbatim chat history, trimmed to budget
    token_estimate: int   # Rough token estimate of total context
```

Used by the context assembly function (section 06) to return assembled context to the agent.

**`ContextMemories` model:**

```python
class ContextMemories(BaseModel):
    common_scene_memory: Memory | None
    private_scene_memory: Memory | None
    character_memories: dict[str, Memory]  # keyed by character_id
    world_facts: list[Memory]
```

Used as the intermediate result from `get_memories_for_context()` (section 03) before formatting into text.

### 2. Package Init (`/home/harald/src/sidestage/src/sidestage/memory/__init__.py`)

Re-export the public API from the package for convenient imports:

```python
"""Sidestage memory system -- living text documents stored as graph nodes."""

from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
```

Additional re-exports will be added by later sections as they create `embeddings.py`, `store.py`, `context.py`, and `tools.py`. For now, only the models are exported.

### 3. Campaign Health (`/home/harald/src/sidestage/src/sidestage/health.py`)

This is a new top-level module (not inside the memory package) because health applies to the entire campaign, not just memory.

**`HealthStatus` enum:**

```python
class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
```

**`CampaignHealth` class:**

```python
class CampaignHealth:
    """Manages campaign health status with transition logic.

    Attributes:
        status: Current health status.
        reason: Human-readable reason for current status.
    """

    def __init__(self, on_change: Callable[[HealthStatus, str], Awaitable[None]] | None = None):
        """Initialize with HEALTHY status.

        Args:
            on_change: Optional async callback fired when status transitions.
                       Receives (new_status, reason).
        """
        ...

    async def set_status(self, status: HealthStatus, reason: str) -> None:
        """Transition to a new status.

        If the status actually changed (different from current), fires the
        on_change callback (if one was provided). Always updates the stored reason.
        """
        ...

    @property
    def is_accepting_chat(self) -> bool:
        """True if HEALTHY or DEGRADED. Only UNHEALTHY blocks chat."""
        ...

    @property
    def is_embedding_available(self) -> bool:
        """True only if HEALTHY. DEGRADED and UNHEALTHY skip embedding."""
        ...
```

Key design decisions:
- `status` and `reason` are stored as instance attributes, not properties with complex getters.
- The `on_change` callback is `async` because the primary consumer is a WebSocket broadcast, which is async.
- `set_status` is `async` because it awaits the callback. If no callback is provided, it completes synchronously inside the coroutine (no actual I/O).
- The callback is only fired when the status actually *changes* (not on repeated calls with the same status). The reason is always updated regardless.

Health state transition table for reference:

| From | To | Trigger |
|------|-----|---------|
| HEALTHY | DEGRADED | Embedding failure, or embed config missing |
| DEGRADED | HEALTHY | Embedding succeeds after prior failure |
| HEALTHY/DEGRADED | UNHEALTHY | Graph database connection lost |
| UNHEALTHY | HEALTHY | Graph database reconnected |

### 4. LLMConfig Extensions (`/home/harald/src/sidestage/src/sidestage/campaign.py`)

Add two optional fields to the existing `LLMConfig` class:

```python
class LLMConfig(BaseModel):
    """Configuration for a single LLM endpoint."""
    provider: str = Field(default="llama_cpp", description="LLM provider: 'llama_cpp' or 'gemini'")
    base_url: str = Field(default="http://localhost:8080/v1", description="Base URL for OpenAI-compatible API")
    api_key: str = Field(default="sk-no-key-required", description="API key")
    model: str = Field(default="default", description="Model name to request")
    # New fields:
    context_limit: int | None = Field(default=None, description="Max context tokens (validated at startup)")
    memory_token_budget: int | None = Field(default=None, description="Tokens allocated for memory context (optional override)")
```

Both default to `None` so existing config files that lack these fields continue to load without error (backwards compatibility). The `context_limit` is used later by context assembly (section 06) to compute the chat history budget. The `memory_token_budget` provides an optional manual override.

### 5. GraphConfig Extension (`/home/harald/src/sidestage/src/sidestage/graph/client.py`)

Add one optional field to the existing `GraphConfig` dataclass:

```python
@dataclass
class GraphConfig:
    """FalkorDB connection configuration."""
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None
    # New field:
    vector_dimension: int | None = None  # Set at startup from test embedding call
```

This field defaults to `None`. It is populated at campaign startup (by the embed validation logic in section 04/07) after making a test embedding call to determine the actual vector dimension. The schema migration (section 02) uses this value to create the vector index with the correct dimension. If `None`, the vector index creation is skipped.

---

## Verification

After implementing this section, run:

```bash
cd /home/harald/src/sidestage && uv run pytest tests/unit/test_memory_models.py tests/unit/test_health.py tests/unit/test_campaign_config.py -v
```

All tests should pass. Additionally, the existing test suite should continue to pass since the only changes to existing files are additive (new optional fields with defaults):

```bash
cd /home/harald/src/sidestage && uv run pytest tests/unit/test_campaign.py -v
```