Now I have all the necessary context. Let me generate the section content.

# Section 06: Context Assembly

## Overview

This section implements the context assembly system in `/home/harald/src/sidestage/src/sidestage/memory/context.py`. The context assembly function fetches all applicable memories for a given character, formats them into structured text sections, trims recent chat history to fit within a token budget, and returns a `ContextResult` ready for injection into the agent's LLM prompt.

Context assembly is the bridge between the memory store (section 03) and the agent integration (section 07). It does not modify the agent or scene code -- it only reads from the memory store and formats the result.

## Dependencies

- **Section 01 (Models and Health):** Provides `Memory`, `MemoryType`, `ContextResult`, `ContextMemories` models used throughout this module.
- **Section 03 (Memory Store):** Provides `get_memories_for_context()` and `touch_memory()` functions that this module calls to fetch memories from FalkorDB.

These sections must be implemented before this one. This section does not depend on sections 04 (Embeddings) or 05 (Memory Tools).

## Background

### What Context Assembly Does

When an NPC character needs to respond to a chat message, the system assembles a "context" -- everything the character currently "knows" -- and injects it into the LLM prompt as a system message. The context consists of:

1. **World facts** -- generally known facts (visibility="common") about entities relevant to the scene
2. **Common scene memory** -- what everyone knows happened in this scene (visibility="common")
3. **Personal scene memory** -- this character's private scene memory (visibility="private", owner=self)
4. **Character memories** -- this character's private memories about other characters present in the scene
5. **Recent chat history** -- verbatim recent messages, trimmed to a token budget

### Visibility Filter Rule

The context assembly fetches memories where:
```
visibility == "common" OR owner_id == this_character_id
```

This single rule handles all current cases. A character never sees another character's private memories.

### Context Window Budget

Chat history is allocated a percentage of the LLM's context window:
```
chat_history_words = context_limit_tokens * chat_history_ratio / avg_tokens_per_word
```

- `context_limit` comes from the `default` LLM config
- `chat_history_ratio` defaults to 0.20 (20% of context window)
- `avg_tokens_per_word` is approximately 1.3 (for English text)

### Output Format

The assembled context is formatted as structured markdown sections. Sections with no content are omitted entirely:

```
## World Knowledge
- [Fact about entity relevant to this scene]
- [Another generally known fact]

## Scene Memory (General)
[Common scene memory content -- what everyone knows]

## My Scene Memory
[Character's private scene memory, or omitted if none]

## People I Know
### [Character Name]
[Memory about this character]

### [Character Name]
[Memory about this character]

## Recent Events
[Character A]: message text
[Character B]: message text
```

## Tests

All tests go in `/home/harald/src/sidestage/tests/unit/test_context.py`. Tests mock the memory store functions so no FalkorDB instance is required.

```python
# tests/unit/test_context.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# --- Assembly ---
# Test: assemble_context returns ContextResult with all sections populated
# Test: assemble_context includes common scene memory in output
# Test: assemble_context includes private scene memory for the owner
# Test: assemble_context excludes other characters' private scene memories
# Test: assemble_context includes character memories about present characters only
# Test: assemble_context includes common world facts
# Test: assemble_context excludes private world facts owned by other characters
# Test: assemble_context returns empty memory_text when no memories exist
# Test: assemble_context omits sections with no content

# --- Chat history trimming ---
# Test: chat history trimmed to 20% of context_limit by default
# Test: chat history ratio is configurable
# Test: chat history preserves most recent messages (trims oldest)
# Test: chat history formats messages as "[CharacterName]: message text"
# Test: empty message list produces empty chat_text

# --- Token estimation ---
# Test: token_estimate is roughly chars / 4
# Test: token_estimate accounts for both memory_text and chat_text

# --- Visibility filter ---
# Test: visibility filter includes visibility="common" memories
# Test: visibility filter includes visibility="private" where owner_id matches
# Test: visibility filter excludes visibility="private" where owner_id doesn't match
```

### Test Details

Tests should construct `Memory` objects directly (using the Pydantic model from section 01) and mock `get_memories_for_context()` to return a `ContextMemories` object with the desired memories. Tests should also construct `ChatMessage` objects (from `sidestage.schemas`) for chat history tests.

Key patterns:

- Mock `memory.store.get_memories_for_context` as an `AsyncMock` returning a `ContextMemories` instance.
- Mock `memory.store.touch_memory` as an `AsyncMock` (fire-and-forget, just verify it is called).
- The `GraphClient` parameter can be a `MagicMock` since the store functions are mocked.
- `ChatMessage` objects require `id`, `name`, `body`, `scene_id`, `gametime`, `walltime`, `character_id`, and `message` fields.

For the trimming tests, construct a list of `ChatMessage` objects that exceeds the word budget and verify that only the most recent messages appear in the output. The budget calculation is: `context_limit * chat_history_ratio / 1.3`, yielding an approximate word count.

For the "omits sections with no content" test, return a `ContextMemories` with empty/None values and verify the corresponding headers do not appear in `memory_text`.

For the visibility tests, these verify the logic at the `assemble_context` level: the function delegates to `get_memories_for_context()` (which handles graph-level filtering), so the tests here confirm that `assemble_context` passes the correct `character_id` and `scene_id` to the store function and correctly includes/excludes the returned results.

## Implementation

### File: `/home/harald/src/sidestage/src/sidestage/memory/context.py`

This is a new file in the `memory` package.

### ContextResult Model

The `ContextResult` model is defined in `memory/models.py` (section 01). It has three fields:

```python
class ContextResult(BaseModel):
    memory_text: str     # World facts + scene memories + character memories
    chat_text: str       # Recent verbatim chat history, trimmed to budget
    token_estimate: int  # Rough token estimate of total context
```

### ContextMemories Model

Also defined in `memory/models.py` (section 01):

```python
class ContextMemories(BaseModel):
    common_scene_memory: Memory | None = None
    private_scene_memory: Memory | None = None
    character_memories: dict[str, Memory] = {}   # character_id -> Memory
    world_facts: list[Memory] = []
```

### assemble_context Function

```python
async def assemble_context(
    client: GraphClient,
    owner_id: str,
    scene_id: str,
    present_character_ids: list[str],
    recent_messages: list[ChatMessage],
    context_limit: int,
    chat_history_ratio: float = 0.20,
) -> ContextResult:
    """Assemble memory context for an agent prompt.

    1. Call get_memories_for_context() to fetch all applicable memories
    2. Touch accessed memories (update access_count and last_accessed_at)
    3. Format memories into structured markdown sections
    4. Trim chat history to budget
    5. Return combined context as ContextResult

    Args:
        client: The FalkorDB graph client.
        owner_id: Character ID of the agent whose context is being built.
        scene_id: Current scene ID.
        present_character_ids: IDs of characters present in the scene (for character memory lookup).
        recent_messages: Full list of recent ChatMessage objects from the scene.
        context_limit: Total context window size in tokens (from LLM config).
        chat_history_ratio: Fraction of context_limit allocated to chat history. Default 0.20.

    Returns:
        ContextResult with memory_text, chat_text, and token_estimate.
    """
```

### Internal Helper Functions

The implementation should include internal helpers for clarity:

**`_format_memories(memories: ContextMemories) -> str`**

Formats the `ContextMemories` object into the structured markdown text. Each section is only included if it has content:

- "## World Knowledge" section: each world fact as a bullet point (`- content`)
- "## Scene Memory (General)" section: the common scene memory content
- "## My Scene Memory" section: the private scene memory content
- "## People I Know" section: each character memory as a sub-heading (`### CharacterName`) followed by the memory content

Returns an empty string if no memories exist at all.

**`_trim_chat_history(messages: list[ChatMessage], word_budget: int) -> str`**

Takes the full list of recent messages and trims to fit the word budget. Works from the end of the list (most recent messages) backwards, accumulating words until the budget is reached. Formats each message as `[character_id]: message_text`. Returns the formatted string, or empty string if no messages or zero budget.

The word budget is calculated by the caller as:
```python
AVG_TOKENS_PER_WORD = 1.3
word_budget = int(context_limit * chat_history_ratio / AVG_TOKENS_PER_WORD)
```

**`_estimate_tokens(text: str) -> int`**

Simple token estimation: `len(text) // 4`. This is a rough approximation sufficient for budget management. Counts both `memory_text` and `chat_text`.

### Touch Semantics

After fetching memories via `get_memories_for_context()`, the function should call `touch_memory()` for each memory that was returned. This updates `access_count` and `last_accessed_at` for future cleanup/analytics. The touch calls should be non-blocking -- use `asyncio.gather()` to execute them concurrently, or fire them as background tasks. If a touch call fails, log a warning but do not fail the context assembly.

### Character Name Resolution

The `_format_memories` function needs character names for the "People I Know" section headings. The `ContextMemories.character_memories` dict is keyed by `character_id`. The function should use the character_id as the heading text. If the caller wants display names, this can be enhanced later -- for now, the character_id is sufficient and avoids additional graph queries.

Alternatively, `assemble_context` can accept an optional `character_names: dict[str, str] | None` parameter mapping character IDs to display names. If provided, use the display name; otherwise fall back to the character_id. This is a minor enhancement that keeps the function flexible without adding complexity.

### Edge Cases

- **No memories exist:** Return `ContextResult(memory_text="", chat_text=..., token_estimate=...)`. The agent runs with just its system prompt and chat history.
- **No chat messages:** Return `ContextResult(memory_text=..., chat_text="", token_estimate=...)`.
- **Both empty:** Return `ContextResult(memory_text="", chat_text="", token_estimate=0)`.
- **context_limit is 0 or very small:** The word budget calculation may yield 0 words. In this case, `chat_text` is empty.
- **get_memories_for_context fails:** The caller (in section 07's agent integration) is responsible for catching exceptions and falling back to no-context mode. The `assemble_context` function itself should let exceptions propagate.

### Module Constants

```python
AVG_TOKENS_PER_WORD = 1.3
DEFAULT_CHAT_HISTORY_RATIO = 0.20
```

### Package Export

The `assemble_context` function and `ContextResult` model should be exported from `/home/harald/src/sidestage/src/sidestage/memory/__init__.py`. If the `__init__.py` already exists from section 01, add `assemble_context` to it. If not, create it with at minimum:

```python
from sidestage.memory.context import assemble_context
```

## Implementation Checklist

1. Write all tests in `/home/harald/src/sidestage/tests/unit/test_context.py`
2. Create `/home/harald/src/sidestage/src/sidestage/memory/context.py` with:
   - Module constants (`AVG_TOKENS_PER_WORD`, `DEFAULT_CHAT_HISTORY_RATIO`)
   - `_format_memories()` helper
   - `_trim_chat_history()` helper
   - `_estimate_tokens()` helper
   - `assemble_context()` main function
3. Update `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` to export `assemble_context`
4. Run tests: `uv run pytest tests/unit/test_context.py -v`
5. Verify all tests pass