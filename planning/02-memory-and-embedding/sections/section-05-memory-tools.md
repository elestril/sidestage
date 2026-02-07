Now I have all the context I need. Let me produce the section content.

# Section 05: Memory Tools (Agent-Callable)

## Overview

This section implements agent-callable memory tools that allow NPC characters and the DM/Co-Author to create and update memories during gameplay. The `MemoryTools` class provides tools bound to a specific character and scene. A separate `DmMemoryTools` class provides world-state management tools for the Co-Author agent. Each tool call persists the memory via the store, then fires off a background embedding task.

## Dependencies

- **section-01-models-and-health** (complete): Provides `Memory`, `MemoryType`, `CampaignHealth`, `HealthStatus`, and the `LLMConfig` model with extended fields.
- **section-03-memory-store** (complete): Provides `upsert_scene_memory`, `upsert_common_scene_memory`, `upsert_character_memory`, `upsert_world_fact`, and the `upsert_memory` function in `/home/harald/src/sidestage/src/sidestage/memory/store.py`.
- **section-04-embeddings** (complete): Provides `embed_and_update` in `/home/harald/src/sidestage/src/sidestage/memory/embeddings.py`.

## File to Create

`/home/harald/src/sidestage/src/sidestage/memory/tools.py`

## Test File to Create

`/home/harald/src/sidestage/tests/unit/test_memory_tools.py`

---

## Tests (Write First)

All tests go in `/home/harald/src/sidestage/tests/unit/test_memory_tools.py`. Tests use `pytest` with `pytest-anyio` for async tests, and `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`) for mocking dependencies.

The tests mock out `memory.store` upsert functions and `memory.embeddings.embed_and_update` so that no real database or embedding service is needed.

```python
# /home/harald/src/sidestage/tests/unit/test_memory_tools.py

"""Unit tests for memory tools (NPC and DM agent-callable tools)."""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sidestage.memory.models import Memory, MemoryType
from sidestage.memory.tools import MemoryTools, DmMemoryTools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_memory(**overrides) -> Memory:
    """Helper to build a Memory with sensible defaults."""
    defaults = dict(
        id="mem_test123",
        content="test content",
        memory_type=MemoryType.SCENE,
        visibility="private",
        embedding=None,
        owner_id="char_alice",
        target_id="scene_01",
        created_at=1000.0,
        updated_at=1000.0,
        gametime=None,
        access_count=0,
        last_accessed_at=None,
    )
    defaults.update(overrides)
    return Memory(**defaults)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_embed_config():
    """A minimal LLMConfig-like object for embedding."""
    cfg = MagicMock()
    cfg.provider = "llama_cpp"
    cfg.model = "embed"
    cfg.base_url = "http://localhost:8080/v1"
    cfg.api_key = "sk-no-key-required"
    return cfg


@pytest.fixture
def mock_health():
    health = MagicMock()
    health.is_embedding_available = True
    return health


@pytest.fixture
def npc_tools(mock_client, mock_embed_config, mock_health):
    return MemoryTools(
        client=mock_client,
        embed_config=mock_embed_config,
        health=mock_health,
        owner_id="char_alice",
        scene_id="scene_01",
    )


@pytest.fixture
def dm_tools(mock_client, mock_embed_config, mock_health):
    return DmMemoryTools(
        client=mock_client,
        embed_config=mock_embed_config,
        health=mock_health,
        dm_actor_id="dm_001",
    )


# ---------------------------------------------------------------------------
# NPC MemoryTools tests
# ---------------------------------------------------------------------------

class TestMemoryToolsBinding:
    """Test that MemoryTools binds to specific owner_id and scene_id at construction."""

    def test_binds_owner_id(self, npc_tools):
        assert npc_tools.owner_id == "char_alice"

    def test_binds_scene_id(self, npc_tools):
        assert npc_tools.scene_id == "scene_01"


class TestUpdateSceneMemory:
    """Tests for MemoryTools.update_scene_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_correct_params(self, mock_embed, mock_upsert, npc_tools):
        """update_scene_memory calls upsert_scene_memory with correct owner_id and scene_id."""
        mock_upsert.return_value = _make_memory()
        result = await npc_tools.update_scene_memory(content="The tavern exploded")
        mock_upsert.assert_awaited_once_with(
            npc_tools.client, "char_alice", "scene_01", "The tavern exploded", gametime=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_fires_embed_as_background_task(self, mock_embed, mock_upsert, npc_tools):
        """update_scene_memory fires embed_and_update as a background asyncio.Task."""
        mem = _make_memory()
        mock_upsert.return_value = mem
        await npc_tools.update_scene_memory(content="something happened")
        # embed_and_update should have been scheduled (we check it was called)
        # Allow the event loop to process the background task
        await asyncio.sleep(0)
        mock_embed.assert_awaited_once()

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_returns_json_with_memory_id(self, mock_embed, mock_upsert, npc_tools):
        """update_scene_memory returns JSON confirmation with memory ID."""
        mock_upsert.return_value = _make_memory(id="mem_abc")
        result = await npc_tools.update_scene_memory(content="noted")
        parsed = json.loads(result)
        assert parsed["memory_id"] == "mem_abc"
        assert parsed["status"] == "ok"

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    async def test_returns_error_json_on_graph_failure(self, mock_upsert, npc_tools):
        """update_scene_memory returns error JSON when the store raises an exception."""
        mock_upsert.side_effect = Exception("graph down")
        result = await npc_tools.update_scene_memory(content="crash")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "graph down" in parsed["message"]


class TestUpdateCharacterMemory:
    """Tests for MemoryTools.update_character_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_character_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_correct_params(self, mock_embed, mock_upsert, npc_tools):
        """update_character_memory calls upsert_character_memory with correct parameters."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.CHARACTER, target_id="char_bob")
        await npc_tools.update_character_memory(
            about_character_id="char_bob", content="Bob seems trustworthy",
        )
        mock_upsert.assert_awaited_once_with(
            npc_tools.client, "char_alice", "char_bob", "Bob seems trustworthy", gametime=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_character_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_returns_json_with_memory_id(self, mock_embed, mock_upsert, npc_tools):
        """update_character_memory returns JSON with memory ID."""
        mock_upsert.return_value = _make_memory(id="mem_xyz")
        result = await npc_tools.update_character_memory(
            about_character_id="char_bob", content="Bob is shady",
        )
        parsed = json.loads(result)
        assert parsed["memory_id"] == "mem_xyz"
        assert parsed["status"] == "ok"


class TestNpcToolsEmbedSkippedWhenNoConfig:
    """Embedding is skipped when embed_config is None."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_no_embed_when_config_none(self, mock_embed, mock_upsert, mock_client, mock_health):
        tools = MemoryTools(
            client=mock_client,
            embed_config=None,
            health=mock_health,
            owner_id="char_alice",
            scene_id="scene_01",
        )
        mock_upsert.return_value = _make_memory()
        await tools.update_scene_memory(content="noted")
        await asyncio.sleep(0)
        mock_embed.assert_not_awaited()


# ---------------------------------------------------------------------------
# DM Tools tests
# ---------------------------------------------------------------------------

class TestUpdateCommonMemory:
    """Tests for DmMemoryTools.update_common_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_common_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_common(self, mock_embed, mock_upsert, dm_tools):
        """update_common_memory calls upsert_common_scene_memory."""
        mock_upsert.return_value = _make_memory(visibility="common", owner_id=None)
        await dm_tools.update_common_memory(scene_id="scene_01", content="A brawl broke out")
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "scene_01", "A brawl broke out", gametime=None,
        )


class TestUpdateCanonicalMemory:
    """Tests for DmMemoryTools.update_canonical_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_dm_owner(self, mock_embed, mock_upsert, dm_tools):
        """update_canonical_memory calls upsert_scene_memory with DM owner_id (visibility=private)."""
        mock_upsert.return_value = _make_memory(owner_id="dm_001")
        await dm_tools.update_canonical_memory(scene_id="scene_01", content="The assassin was there")
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "dm_001", "scene_01", "The assassin was there", gametime=None,
        )


class TestAddWorldFact:
    """Tests for DmMemoryTools.add_world_fact."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_world_fact", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_common_world_fact(self, mock_embed, mock_upsert, dm_tools):
        """add_world_fact with visibility='common' creates common world fact."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.WORLD_FACT, visibility="common")
        await dm_tools.add_world_fact(
            about_entity_id="loc_tavern", content="The tavern is haunted", visibility="common",
        )
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "loc_tavern", "The tavern is haunted",
            visibility="common", owner_id=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_world_fact", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_private_world_fact(self, mock_embed, mock_upsert, dm_tools):
        """add_world_fact with visibility='private' creates private world fact."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.WORLD_FACT, visibility="private")
        await dm_tools.add_world_fact(
            about_entity_id="loc_tavern", content="Secret passage exists",
            visibility="private",
        )
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "loc_tavern", "Secret passage exists",
            visibility="private", owner_id=None,
        )


class TestDmToolsFireEmbed:
    """DM tools fire embed_and_update as a background task."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_common_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_embed_fired_for_common_memory(self, mock_embed, mock_upsert, dm_tools):
        mem = _make_memory(visibility="common", owner_id=None)
        mock_upsert.return_value = mem
        await dm_tools.update_common_memory(scene_id="scene_01", content="stuff")
        await asyncio.sleep(0)
        mock_embed.assert_awaited_once()
```

### Test Design Notes

- Each NPC tool method (`update_scene_memory`, `update_character_memory`) is tested for: correct store call arguments, background embedding task firing, JSON return format, and error handling.
- Each DM tool method (`update_common_memory`, `update_canonical_memory`, `add_world_fact`) is tested for correct store call delegation and embedding task firing.
- The `MemoryTools` construction binding is verified (owner_id and scene_id are stored).
- The "no embed_config" case verifies that `embed_and_update` is not called when embedding is not configured.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/memory/tools.py`

This module defines two tool classes: `MemoryTools` for NPC character agents and `DmMemoryTools` for the DM/Co-Author agent. Both follow the existing tool pattern in the codebase (see `/home/harald/src/sidestage/src/sidestage/tools.py` -- `WorldTools`): methods are async, take simple typed parameters (strings, optionally ints), and return JSON strings.

#### Imports

The module imports from sibling modules within `sidestage.memory`:

- `upsert_scene_memory`, `upsert_common_scene_memory`, `upsert_character_memory`, `upsert_world_fact` from `sidestage.memory.store`
- `embed_and_update` from `sidestage.memory.embeddings`

It also imports `asyncio` for background task creation, `json` for response formatting, `logging`, and types from `sidestage.memory.models` and the graph client.

#### MemoryTools Class

```python
class MemoryTools:
    """Memory update tools for character agents.

    Each instance is bound to a specific character (owner_id) and scene.
    All memories created are private (visibility="private").
    """

    def __init__(
        self,
        client: GraphClient,
        embed_config: LLMConfig | None,
        health: CampaignHealth,
        owner_id: str,
        scene_id: str,
    ): ...

    async def update_scene_memory(self, content: str) -> str:
        """Update your memory of the current scene. ..."""

    async def update_character_memory(self, about_character_id: str, content: str) -> str:
        """Update your memory about another character. ..."""
```

Key implementation patterns for each method:

1. **Call the store upsert function** -- pass `self.client`, `self.owner_id`, target ID, content, and `gametime=None` (gametime support is for future use).
2. **Fire background embedding** -- if `self.embed_config` is not None, create an `asyncio.Task` that calls `embed_and_update(self.client, self.embed_config, memory.id, content, self.health)`. This is non-blocking; the tool returns immediately.
3. **Return JSON** -- on success, return `json.dumps({"status": "ok", "memory_id": memory.id})`. On exception, catch, log, and return `json.dumps({"status": "error", "message": str(e)})`.

The background task pattern:

```python
asyncio.create_task(
    embed_and_update(self.client, self.embed_config, memory.id, content, self.health)
)
```

This follows the design in the plan: embedding is fire-and-forget. The task runs in the current event loop. If it fails, `embed_and_update` handles the health transition internally.

#### DmMemoryTools Class

```python
class DmMemoryTools:
    """Memory tools for the DM / Co-Author agent.

    Manages world-state memories: common scene memories, canonical
    (DM-truth) scene memories, and world facts.
    """

    def __init__(
        self,
        client: GraphClient,
        embed_config: LLMConfig | None,
        health: CampaignHealth,
        dm_actor_id: str,
    ): ...

    async def update_common_memory(self, scene_id: str, content: str) -> str:
        """Update the common scene memory -- what everyone generally knows. ..."""

    async def update_canonical_memory(self, scene_id: str, content: str) -> str:
        """Update the canonical (DM truth) scene memory. ..."""

    async def add_world_fact(self, about_entity_id: str, content: str, visibility: str = "common") -> str:
        """Add or update a world fact. ..."""
```

Method implementations:

- **`update_common_memory`**: Calls `upsert_common_scene_memory(client, scene_id, content, gametime=None)`. No owner -- common memories have `owner_id=None`.
- **`update_canonical_memory`**: Calls `upsert_scene_memory(client, self.dm_actor_id, scene_id, content, gametime=None)`. The DM's actor ID is the owner, making this a private scene memory visible only to the DM.
- **`add_world_fact`**: Calls `upsert_world_fact(client, about_entity_id, content, visibility=visibility, owner_id=None)`. The `owner_id` is None for both common and private world facts created by the DM (the visibility field controls access, not the owner). If a future requirement needs DM-owned private facts, the `owner_id` parameter is available.

All three follow the same embed-and-return pattern as the NPC tools.

#### Docstrings as LLM Tool Descriptions

The docstrings on each method serve double duty: they are developer documentation AND the descriptions the LLM sees in the tool schema (via `LiteLLMAgent._function_to_schema()`). The first paragraph of the docstring becomes the function description. Keep them concise and instructive -- they tell the LLM when and how to use the tool.

Example for `update_scene_memory`:

```
Update your memory of the current scene.

Call this when something noteworthy happens that you want to remember
about this scene. Your scene memory is a living document -- include
everything important, as this replaces your previous scene memory.

Args:
    content: Your updated memory of this scene. Include key events,
             decisions, and anything you want to remember.

Returns:
    JSON confirmation with memory ID.
```

#### Error Handling

Tool methods catch all exceptions from the store layer. On failure, they return a JSON error message string rather than raising. This follows the existing pattern in `LiteLLMAgent.arun()` where tool call failures are caught and the error string is sent back to the LLM as the tool result (see `/home/harald/src/sidestage/src/sidestage/agent.py` lines 138-146).

### Updating `__init__.py`

The module `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` should be updated to re-export `MemoryTools` and `DmMemoryTools` from `tools.py`. If the `__init__.py` does not yet exist (created in an earlier section), create it with these exports alongside any existing ones.

---

## Integration Notes

- **How tools are given to agents**: In a later section (section-07/08), `MemoryTools` instances will be created during scene activation and their methods added to the agent's `tools` list. The `LiteLLMAgent._function_to_schema()` introspects each method's signature and docstring to build the OpenAI tool schema.
- **The `self` parameter**: `_function_to_schema` already skips `self` (line 55 of agent.py), so bound methods work correctly as tools.
- **Background tasks and cleanup**: `asyncio.create_task()` keeps the embedding task alive as long as the event loop runs. No explicit task tracking or cancellation is needed; `embed_and_update` is idempotent and handles its own errors.