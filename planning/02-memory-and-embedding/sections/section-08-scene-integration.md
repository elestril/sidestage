Now I have all the context needed. Let me generate the section content.

# Section 08: Scene Integration

## Overview

This is the final section of the memory and embedding implementation. It wires the memory system into `SceneLogic` so that when a scene activates, each character receives the graph client, embed config, health status, and context limit needed for memory operations. After this section, the full end-to-end flow works: a scene activates, characters get `MemoryTools` in their tool list, context is assembled before each LLM call, and memory tool calls persist to FalkorDB with background embedding.

**Dependencies (must be completed first):**
- Section 07 (Agent Integration) -- `AgentActor` and `CharacterLogic` already accept memory-related keyword arguments (`graph_client`, `embed_config`, `health`, `scene_id`, `present_character_ids`, `context_limit`); `Campaign` already has a `CampaignHealth` instance and embed validation logic
- Section 06 (Context Assembly) -- `assemble_context()` exists in `src/sidestage/memory/context.py`
- Section 05 (Memory Tools) -- `MemoryTools` class exists in `src/sidestage/memory/tools.py`
- Section 01 (Models and Health) -- `CampaignHealth`, `HealthStatus`, `LLMConfig` with extended fields

**Blocks:** Nothing. This is the final section.

---

## Background

### Current State (Before This Section)

After section 07, the following is true:

- `AgentActor.__init__` accepts optional keyword arguments: `graph_client`, `embed_config`, `health`, `scene_id`, `present_character_ids`, `context_limit`. When these are provided, it creates `MemoryTools` for the agent and calls `assemble_context()` in `on_event()`.
- `CharacterLogic.__init__` accepts the same optional keyword arguments and forwards them to `AgentActor` during `activate()`.
- `Campaign` has a `self.health` (`CampaignHealth`) instance, embed validation in `start_graph()`, and is ready to supply memory dependencies to `SceneLogic`.

However, `SceneLogic` itself does not yet accept or forward these memory dependencies. It still constructs `CharacterLogic` with just `(char_data, self)` -- no memory parameters. This section closes that gap.

### What This Section Does

1. **Modifies `SceneLogic.__init__`** to accept `embed_config`, `health`, and `context_limit` parameters.
2. **Modifies `SceneLogic.activate()`** to pass these memory dependencies through to `CharacterLogic`, along with `graph_client`, `scene_id`, and the list of present character IDs.
3. **Modifies `Campaign.get_scene_object()`** to pass the memory dependencies when constructing `SceneLogic`.
4. **Adds integration tests** verifying the full wiring chain from `SceneLogic` down to `AgentActor`.

### Data Flow After This Section

```
Campaign.get_scene_object()
    |
    v
SceneLogic(storage, agent, data,
           graph_client=..., embed_config=..., health=..., context_limit=...)
    |
    v (on activate)
CharacterLogic(char_data, scene_logic,
               graph_client=..., embed_config=..., health=...,
               scene_id=..., present_character_ids=..., context_limit=...)
    |
    v (on activate)
AgentActor(character, scene_logic,
           graph_client=..., embed_config=..., health=...,
           scene_id=..., present_character_ids=..., context_limit=...)
    |
    v (on_event)
    1. assemble_context() -> ContextResult
    2. agent.arun(message, context=context_text)
    3. LLM may call update_scene_memory / update_character_memory
```

---

## Tests First

All tests for this section live in a new integration test file. These tests verify the wiring -- that `SceneLogic` correctly passes memory dependencies to `CharacterLogic` and `AgentActor`, and that the full flow from scene activation to context assembly works.

### File: `/home/harald/src/sidestage/tests/integration/test_memory_integration.py`

```python
# tests/integration/test_memory_integration.py

"""Integration tests for memory system wiring through scene activation."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from sidestage.schemas import Scene, Character, ChatMessage
from sidestage.scene import SceneLogic
from sidestage.character import CharacterLogic, AgentActor
from sidestage.agent import LiteLLMAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scene(**overrides) -> Scene:
    defaults = dict(
        id="scene_test",
        name="Test Scene",
        body="A test scene.",
        current_gametime=100,
    )
    defaults.update(overrides)
    return Scene(**defaults)


def _make_character(**overrides) -> Character:
    defaults = dict(
        id="char_alice",
        name="Alice",
        body="A brave warrior.",
    )
    defaults.update(overrides)
    return Character(**defaults)


def _make_agent() -> MagicMock:
    """Create a mock LiteLLMAgent with expected attributes."""
    agent = MagicMock(spec=LiteLLMAgent)
    agent.model = "openai/default"
    agent.api_base = "http://localhost:8080/v1"
    agent.api_key = "sk-no-key-required"
    agent.tools = []
    agent.debug_mode = False
    return agent


# ---------------------------------------------------------------------------
# Test: SceneLogic passes graph_client to CharacterLogic when available
# ---------------------------------------------------------------------------

# Construct a SceneLogic with a mock graph_client, mock embed_config, mock
# health, and a context_limit. Call activate(). Verify that each
# CharacterLogic created during activation received the graph_client as an
# attribute. Use patch to mock list_entities to return a list of Character
# objects.


# ---------------------------------------------------------------------------
# Test: AgentActor receives MemoryTools when graph_client exists
# ---------------------------------------------------------------------------

# Construct an AgentActor with graph_client, embed_config, health, scene_id,
# and present_character_ids all set (non-None). Verify that the agent's tool
# list includes methods named "update_scene_memory" and
# "update_character_memory" (from the MemoryTools instance).


# ---------------------------------------------------------------------------
# Test: AgentActor tool list includes update_scene_memory and
#       update_character_memory
# ---------------------------------------------------------------------------

# Similar to above but specifically check the tool_map or tool_schemas of
# the resulting LiteLLMAgent to confirm memory tool names appear.


# ---------------------------------------------------------------------------
# Test: AgentActor.on_event calls assemble_context before arun
# ---------------------------------------------------------------------------

# Create an AgentActor with memory dependencies set. Mock
# assemble_context to return a ContextResult. Mock agent.arun to return
# an AgentResponse. Create a ChatMessage event and call on_event().
# Verify assemble_context was called (assert_awaited_once), and that
# agent.arun was called with a context= keyword argument containing the
# assembled text.


# ---------------------------------------------------------------------------
# Test: AgentActor.on_event passes context to arun
# ---------------------------------------------------------------------------

# Create an AgentActor with memory dependencies. Mock assemble_context
# to return a ContextResult with memory_text="memories" and
# chat_text="chat history". Call on_event with a ChatMessage. Verify
# that agent.arun() was called with context containing both "memories"
# and "chat history".


# ---------------------------------------------------------------------------
# Test: AgentActor.on_event gracefully degrades when assemble_context fails
# ---------------------------------------------------------------------------

# Create an AgentActor with memory dependencies. Mock assemble_context
# to raise an Exception. Call on_event with a ChatMessage. Verify that
# agent.arun() was still called (without context or with context=None),
# i.e., the character still responds even when memory assembly fails.


# ---------------------------------------------------------------------------
# Test: AgentActor works without memory system (graph_client=None)
# ---------------------------------------------------------------------------

# Create an AgentActor without any memory dependencies (all None/default).
# Call on_event with a ChatMessage. Verify that assemble_context is NOT
# called and agent.arun() is called without a context parameter (or with
# context=None). This verifies backwards compatibility.
```

### Test Design Notes

- These are integration-level tests that verify wiring between components, not individual unit behavior.
- All external dependencies (graph database, LLM, embedding service) are mocked. The tests verify that the correct parameters flow through the object hierarchy.
- `list_entities` is mocked via `patch("sidestage.graph.list_entities")` to return test `Character` objects during scene activation.
- `assemble_context` is mocked via `patch("sidestage.memory.context.assemble_context")` or `patch("sidestage.character.assemble_context")` depending on the import style used in `character.py`.
- The mock `LiteLLMAgent` should have the attributes `model`, `api_base`, `api_key`, `tools`, and `debug_mode` that `AgentActor._update_prompt()` reads from `self.scene_logic.agent`.

---

## Implementation Details

### 1. Modify `SceneLogic.__init__` -- Accept Memory Dependencies

**File:** `/home/harald/src/sidestage/src/sidestage/scene.py`

**Current signature (line 29-30):**

```python
def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene,
             graph_client: "GraphClient | None" = None):
```

**New signature:**

```python
def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene,
             graph_client: "GraphClient | None" = None,
             embed_config: "LLMConfig | None" = None,
             health: "CampaignHealth | None" = None,
             context_limit: int = 4096):
```

Store the new parameters as instance attributes:

```python
self.embed_config = embed_config
self.health = health
self.context_limit = context_limit
```

Add the necessary type imports at the top of the file. Since `LLMConfig` and `CampaignHealth` may create circular imports, use the `TYPE_CHECKING` pattern already present in the file:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.campaign import LLMConfig
    from sidestage.health import CampaignHealth
```

The `GraphClient` import is already there under `TYPE_CHECKING`. Add `LLMConfig` and `CampaignHealth` alongside it.

### 2. Modify `SceneLogic.activate()` -- Pass Dependencies to CharacterLogic

**File:** `/home/harald/src/sidestage/src/sidestage/scene.py`

**Current code (lines 96-104):**

```python
if self.graph_client is not None:
    from sidestage.graph import list_entities
    all_chars = await list_entities(self.graph_client, entity_type="Character")
else:
    all_chars = self.storage.list_characters()
for char_data in all_chars:
    char_logic = CharacterLogic(char_data, self)
    self.characters[char_data.id] = char_logic
    await char_logic.activate()
```

**New code:**

The key change is passing memory dependencies to `CharacterLogic` and computing the `present_character_ids` list. The list of present character IDs must be computed after loading all characters but before activating any of them:

```python
# Load characters
if self.graph_client is not None:
    from sidestage.graph import list_entities
    all_chars = await list_entities(self.graph_client, entity_type="Character")
else:
    all_chars = self.storage.list_characters()

# Compute present character IDs for context assembly
present_character_ids = [c.id for c in all_chars]

# Create and activate character logic instances
for char_data in all_chars:
    char_logic = CharacterLogic(
        char_data, self,
        graph_client=self.graph_client,
        embed_config=self.embed_config,
        health=self.health,
        scene_id=self.data.id,
        present_character_ids=present_character_ids,
        context_limit=self.context_limit,
    )
    self.characters[char_data.id] = char_logic
    await char_logic.activate()
```

The `present_character_ids` list is shared by reference across all `CharacterLogic` instances. This means if the list were modified later (e.g., a character joins or leaves), all actors would see the update. For this initial implementation, the list is computed once at activation time and not modified during the scene.

### 3. Modify `Campaign.get_scene_object()` -- Supply Memory Dependencies

**File:** `/home/harald/src/sidestage/src/sidestage/campaign.py`

**Current code (lines 466-479):**

```python
def get_scene_object(self, scene_id: str) -> Optional[SceneLogic]:
    data = self.storage.get_scene(scene_id)
    if not data:
        return None
    return SceneLogic(self.storage, self.agent, data, graph_client=self.graph_client)
```

**New code:**

```python
def get_scene_object(self, scene_id: str) -> Optional[SceneLogic]:
    data = self.storage.get_scene(scene_id)
    if not data:
        return None
    embed_config = self.config.llms.get("embed")
    default_llm = self.get_llm_config("default")
    context_limit = getattr(default_llm, "context_limit", None) or 4096
    return SceneLogic(
        self.storage, self.agent, data,
        graph_client=self.graph_client,
        embed_config=embed_config,
        health=self.health,
        context_limit=context_limit,
    )
```

This method reads the embed config from the campaign's LLM configs (returns `None` if no "embed" config exists), gets the `context_limit` from the default LLM config (falling back to 4096 if not set), and passes the campaign's `CampaignHealth` instance.

Note: `self.health` is the `CampaignHealth` instance created in `Campaign.__init__` (added in section 07). If section 07 has not been implemented yet at the time this code runs, `self.health` would not exist. The implementer should ensure section 07 is complete before this section.

### 4. Add Health Check to `SceneLogic.chat()`

**File:** `/home/harald/src/sidestage/src/sidestage/scene.py`

The `chat()` method should optionally check health before processing. If health is UNHEALTHY, the chat should not proceed (the graph database is down and nothing will work correctly).

**Current code (line 178-188):**

```python
async def chat(self, user_message: ChatMessage) -> None:
    await self.bus.publish(user_message)
```

**New code:**

```python
async def chat(self, user_message: ChatMessage) -> None:
    if self.health is not None and not self.health.is_accepting_chat:
        logger.warning("Chat rejected: campaign health is UNHEALTHY")
        return
    await self.bus.publish(user_message)
```

This is a lightweight guard. When health is `None` (no health system configured), the chat proceeds unconditionally (backwards compatibility). When health is HEALTHY or DEGRADED, chat proceeds. Only UNHEALTHY blocks chat.

### 5. No Changes to Deactivation

The `deactivate()` method in `SceneLogic` does not need special cleanup for the memory system. Memories are already persisted to FalkorDB during tool calls. Background embedding tasks (started via `asyncio.create_task` in `MemoryTools`) will complete on their own as long as the event loop is running. The existing deactivation flow -- unsubscribing actors from the bus and clearing the `characters` dict -- is sufficient.

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `/home/harald/src/sidestage/src/sidestage/scene.py` | Accept `embed_config`, `health`, `context_limit` in `__init__`; pass memory dependencies to `CharacterLogic` in `activate()`; add health check to `chat()` |
| `/home/harald/src/sidestage/src/sidestage/campaign.py` | Update `get_scene_object()` to pass `embed_config`, `health`, `context_limit` to `SceneLogic` |
| `/home/harald/src/sidestage/tests/integration/test_memory_integration.py` | New integration test file verifying the full wiring chain |

## Key Design Decisions

1. **Dependencies flow top-down.** The `Campaign` creates the health instance and embed config; `SceneLogic` stores and forwards them; `CharacterLogic` forwards them to `AgentActor`. No component reaches upward to get dependencies from a parent -- everything is passed via constructor parameters.

2. **All new parameters are optional with defaults.** Every new parameter defaults to `None` or a sensible value (4096 for context_limit). This preserves backwards compatibility. Code that constructs `SceneLogic(storage, agent, data)` without memory parameters continues to work exactly as before -- memory features are simply disabled.

3. **`present_character_ids` computed at activation time.** The list of characters present in a scene is determined during `activate()` from the loaded character list. This is a snapshot -- if characters are added or removed after activation, the list would need to be refreshed. For the initial implementation, this is acceptable. Future work could make this dynamic.

4. **Health check in `chat()` is non-blocking.** The health guard returns immediately without raising an exception. The caller (orchestrator/server) should detect the empty response or check health status proactively for user-facing error messages. This keeps `SceneLogic` simple and avoids coupling it to HTTP error handling.

5. **No modification to the bus or event flow.** The message bus, publish hooks, and event listener patterns are unchanged. Memory tools are executed as part of the normal tool-call loop inside `LiteLLMAgent.arun()`, which is already wired up by section 07.

## Implementation Checklist

1. Write integration tests in `/home/harald/src/sidestage/tests/integration/test_memory_integration.py`
2. Update `/home/harald/src/sidestage/src/sidestage/scene.py`:
   - Add `embed_config`, `health`, `context_limit` parameters to `__init__`
   - Add `LLMConfig` and `CampaignHealth` to `TYPE_CHECKING` imports
   - Update `activate()` to compute `present_character_ids` and pass all memory deps to `CharacterLogic`
   - Add health guard to `chat()`
3. Update `/home/harald/src/sidestage/src/sidestage/campaign.py`:
   - Update `get_scene_object()` to supply `embed_config`, `health`, `context_limit` to `SceneLogic`
4. Run tests: `cd /home/harald/src/sidestage && uv run pytest tests/integration/test_memory_integration.py -v`
5. Run full test suite to verify no regressions: `cd /home/harald/src/sidestage && uv run pytest -v`