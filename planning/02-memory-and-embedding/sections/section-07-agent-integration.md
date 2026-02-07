Now I have all the context I need. Let me generate the section content.

# Section 07: Agent Integration

## Overview

This section adds a `context` parameter to `LiteLLMAgent.arun()` so that memory context can be injected between the system prompt and the user message. It also modifies `AgentActor.on_event()` to call `assemble_context()` before each LLM invocation and pass the result as `context`. Finally, it wires `MemoryTools` into the agent's tool list when a graph client is available, and adds embed validation and health wiring to the Campaign startup.

**Dependencies (must be completed first):**
- Section 05 (Memory Tools) -- provides `MemoryTools` class in `src/sidestage/memory/tools.py`
- Section 06 (Context Assembly) -- provides `assemble_context()` in `src/sidestage/memory/context.py` and `ContextResult` in `src/sidestage/memory/models.py`
- Section 01 (Models and Health) -- provides `CampaignHealth`, `HealthStatus` in `src/sidestage/health.py`, `LLMConfig` with `context_limit` and `memory_token_budget` fields, `GraphConfig` with `vector_dimension` field

**Blocks:** Section 08 (Scene Integration)

---

## Tests First

All tests for this section live in a new file. The tests verify the `arun()` context parameter and the `AgentActor` context assembly integration.

### File: `/home/harald/src/sidestage/tests/unit/test_agent_context.py`

```python
# tests/unit/test_agent_context.py

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# --- arun context parameter tests ---

# Test: arun without context parameter works as before (backwards compatible)
#   Create a LiteLLMAgent with mock instructions. Call arun(message) without
#   context. Verify litellm.acompletion is called with messages list containing
#   only the system message (from instructions) and the user message. No
#   extra system message should be present between them.

# Test: arun with context inserts system message between system prompt and user message
#   Create a LiteLLMAgent with instructions. Call arun(message, context="some context").
#   Verify litellm.acompletion is called with messages list of length 3:
#     [0] = system message (instructions)
#     [1] = system message (context)
#     [2] = user message
#   The context system message content should equal "some context".

# Test: arun with empty string context is equivalent to no context
#   Call arun(message, context=""). Verify the messages list passed to
#   litellm.acompletion has exactly 2 entries (system + user), same as the
#   no-context case. Empty string context should be skipped.

# Test: arun with context preserves tool calling behavior
#   Create a LiteLLMAgent with tools and instructions. Call arun with
#   context="memory text". Mock litellm.acompletion to return a response
#   with tool_calls on first call, then a final text response on second call.
#   Verify that the initial messages list includes the context system message
#   AND that tool calling proceeds normally (tool is executed, result appended,
#   second acompletion call happens).
```

---

## Implementation Details

### 1. Modify `LiteLLMAgent.arun()` -- Add `context` Parameter

**File:** `/home/harald/src/sidestage/src/sidestage/agent.py`

**What changes:**

The `arun` method signature gains an optional `context: str | None = None` parameter. When `context` is provided and non-empty, a second system message is inserted into the `messages` list between the existing system prompt (from `self.instructions`) and the user message.

**Current signature (line 85):**

```python
async def arun(self, message: str, stream: bool = False) -> AgentResponse:
```

**New signature:**

```python
async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse:
```

**Message construction logic (currently lines 86-91):**

The current code builds messages as:
1. System message from `self.instructions` (if any)
2. User message

The new code should build messages as:
1. System message from `self.instructions` (if any)
2. System message from `context` (if provided and non-empty)
3. User message

The context system message is added with `{"role": "system", "content": context}`. This keeps memory context clearly separated from both the character prompt and user input. The LLM sees it as authoritative context (system role), positioned after the character description but before the user's actual message.

The check should be `if context:` (truthy check), which naturally handles both `None` and empty string `""` -- both are skipped. No other changes to the method are needed. The tool calling loop, error handling, and streaming parameters all remain identical.

### 2. Modify `AgentActor` -- Context Assembly in `on_event()`

**File:** `/home/harald/src/sidestage/src/sidestage/character.py`

**What changes:**

`AgentActor.__init__` gains new optional dependencies for the memory system. `AgentActor.on_event()` is modified to assemble memory context before calling `self.agent.arun()`.

**New `__init__` parameters:**

The `AgentActor.__init__` method currently takes `(self, character, scene_logic)`. It needs additional optional keyword arguments:

- `graph_client: GraphClient | None = None` -- for memory store operations
- `embed_config: LLMConfig | None = None` -- for embedding generation (passed to MemoryTools)
- `health: CampaignHealth | None = None` -- for health status
- `scene_id: str | None = None` -- current scene ID
- `present_character_ids: list[str] | None = None` -- characters in the scene
- `context_limit: int = 4096` -- from default LLM config

These are stored as instance attributes. All are optional so the class remains backwards compatible when memory is not available.

**MemoryTools integration in `_update_prompt()`:**

When `self.graph_client` is not None, create a `MemoryTools` instance bound to this character and scene. The memory tools (`update_scene_memory`, `update_character_memory`) should be appended to the agent's tool list alongside the existing tools from `base_agent.tools`.

```python
from sidestage.memory.tools import MemoryTools

# In _update_prompt(), after creating self.agent:
if self.graph_client is not None and self.scene_id is not None:
    memory_tools = MemoryTools(
        client=self.graph_client,
        embed_config=self.embed_config,
        health=self.health,
        owner_id=self.character.id,
        scene_id=self.scene_id,
    )
    # Add memory tool methods to the agent's tool list
    tools = list(base_agent.tools) + [
        memory_tools.update_scene_memory,
        memory_tools.update_character_memory,
    ]
else:
    tools = base_agent.tools
```

Then pass `tools=tools` when constructing the `LiteLLMAgent`.

**Context assembly in `on_event()`:**

The current `on_event()` method (line 94) calls:

```python
response = await self.agent.arun(event.message)
```

This should be changed to assemble context first when the memory system is available:

```python
context_text = None
if self.graph_client is not None and self.scene_id is not None:
    try:
        from sidestage.memory.context import assemble_context
        result = await assemble_context(
            client=self.graph_client,
            owner_id=self.character.id,
            scene_id=self.scene_id,
            present_character_ids=self.present_character_ids or [],
            recent_messages=self.scene_logic.messages,
            context_limit=self.context_limit,
        )
        context_text = result.memory_text
        if result.chat_text:
            context_text += "\n\n" + result.chat_text
    except Exception:
        logger.exception("Failed to assemble context for %s", self.character.name)
        # Graceful degradation: proceed without context

response = await self.agent.arun(event.message, context=context_text)
```

The graceful degradation is critical: if `assemble_context()` fails for any reason (graph down, query error, etc.), the agent still responds using its static character prompt -- the same behavior as before the memory system existed.

### 3. Modify `CharacterLogic` -- Pass Memory Dependencies

**File:** `/home/harald/src/sidestage/src/sidestage/character.py`

**What changes:**

`CharacterLogic.__init__` gains the same optional memory-related parameters that it passes through to `AgentActor` during `activate()`.

**New `__init__` parameters:**

```python
def __init__(self, character: Character, scene_logic: Any,
             graph_client: GraphClient | None = None,
             embed_config: LLMConfig | None = None,
             health: CampaignHealth | None = None,
             scene_id: str | None = None,
             present_character_ids: list[str] | None = None,
             context_limit: int = 4096):
```

These are stored as instance attributes and forwarded to `AgentActor.__init__` in the `activate()` method:

```python
async def activate(self) -> None:
    if self.actor is None:
        self.actor = AgentActor(
            self.data, self.scene_logic,
            graph_client=self.graph_client,
            embed_config=self.embed_config,
            health=self.health,
            scene_id=self.scene_id,
            present_character_ids=self.present_character_ids,
            context_limit=self.context_limit,
        )
        self.scene_logic.bus.subscribe(self.actor.on_event)
```

### 4. Campaign Embed Validation and Health Wiring

**File:** `/home/harald/src/sidestage/src/sidestage/campaign.py`

**What changes:**

The `Campaign` class gets a `CampaignHealth` instance and embed config validation logic in `start_graph()`.

**In `Campaign.__init__`:**

Add a `CampaignHealth` instance:

```python
from sidestage.health import CampaignHealth

# In __init__, after other initializations:
self.health = CampaignHealth()
```

**In `Campaign.start_graph()`:**

After establishing the graph connection, if an `embed` LLM config exists:

1. Build the LiteLLM model string from provider + model (same pattern as `create_agent`)
2. Make a test embedding call with probe text to determine vector dimension
3. Store the dimension in `GraphConfig.vector_dimension`
4. If validation fails, log warning and set health to DEGRADED (campaign starts without embedding)

```python
async def start_graph(self) -> None:
    config = self.config.graph
    self.graph_client = await connect(config, campaign_name=self.name)
    self.world_tools.graph_client = self.graph_client

    # Validate embed config if present
    if "embed" in self.config.llms:
        embed_llm = self.get_llm_config("embed")
        try:
            from sidestage.memory.embeddings import embed_text
            test_embedding = await embed_text(embed_llm, "dimension probe")
            config.vector_dimension = len(test_embedding)
            logger.info("Embedding validated: dimension=%d", config.vector_dimension)
        except Exception as e:
            logger.warning("Embedding validation failed: %s", e)
            await self.health.set_status(HealthStatus.DEGRADED, f"Embedding unavailable: {e}")

    logger.info("Graph connection established for campaign '%s'", self.name)
```

**In `Campaign.get_scene_object()`:**

Pass memory dependencies to `SceneLogic` so it can forward them to `CharacterLogic`. This requires `SceneLogic` to accept and store these (covered in section 08). For this section, `Campaign` needs to be ready to pass them:

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

Note: The `SceneLogic` constructor does not yet accept `embed_config`, `health`, or `context_limit` -- that wiring is completed in Section 08. For this section, focus on making `Campaign` ready to supply these values. Until Section 08 is complete, the extra kwargs would cause errors unless `SceneLogic.__init__` is updated to accept and ignore them (or use `**kwargs`). The recommended approach is to prepare the `Campaign` code but guard it behind a check or leave the `SceneLogic` call unchanged until Section 08 lands.

### 5. Type Imports

**File:** `/home/harald/src/sidestage/src/sidestage/character.py`

Add necessary type imports at the top of the file under `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.campaign import LLMConfig
    from sidestage.health import CampaignHealth
```

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `/home/harald/src/sidestage/src/sidestage/agent.py` | Add `context: str \| None = None` parameter to `arun()`, insert context as system message |
| `/home/harald/src/sidestage/src/sidestage/character.py` | Add memory dependencies to `AgentActor.__init__`, assemble context in `on_event()`, add `MemoryTools` to tool list, update `CharacterLogic` to pass dependencies through |
| `/home/harald/src/sidestage/src/sidestage/campaign.py` | Add `CampaignHealth` instance, embed validation in `start_graph()`, prepare memory deps for `SceneLogic` |
| `/home/harald/src/sidestage/tests/unit/test_agent_context.py` | New test file for `arun()` context parameter behavior |

## Key Design Decisions

1. **Context as system message, not user message.** The context is injected as a `{"role": "system", ...}` message, not as part of the user message. This gives the LLM clear signal that this is authoritative background knowledge rather than something the user typed. It also avoids polluting the user message with metadata.

2. **Graceful degradation everywhere.** If `assemble_context()` fails, the agent proceeds without context. If embed validation fails, health goes to DEGRADED but the campaign starts. The system never blocks on memory failures.

3. **Backwards compatibility.** All new parameters are optional with sensible defaults. Existing code that creates `AgentActor(character, scene_logic)` or calls `agent.arun(message)` continues to work unchanged.

4. **MemoryTools bound per-actor.** Each `AgentActor` gets its own `MemoryTools` instance bound to its character ID and scene ID. This means the LLM can only create memories owned by its character -- it cannot impersonate other characters.

5. **Recent messages from SceneLogic.** The `on_event()` method reads `self.scene_logic.messages` (the scene's message history) to pass as `recent_messages` to `assemble_context()`. This list is maintained by `SceneLogic` and already includes all persisted messages.