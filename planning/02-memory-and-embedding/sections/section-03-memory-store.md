Now I have all the context I need. Let me generate the section content.

# Section 03: Memory Store (CRUD + Search)

## Overview

This section implements `src/sidestage/memory/store.py` -- the Memory CRUD operations in FalkorDB. The store uses its own Cypher queries with `:Memory` labels, completely independent of the existing `graph/entities.py` and `graph/relationships.py` modules. It provides upsert, read, delete, touch, and vector search functions for Memory nodes.

## Dependencies

- **Section 01 (Models and Health):** The `Memory`, `MemoryType`, `ContextMemories` Pydantic models from `src/sidestage/memory/models.py` must exist. The `CampaignHealth` class from `src/sidestage/health.py` must exist.
- **Section 02 (Schema Migration):** The v2 schema migration must have created range indexes on `Memory.owner_id`, `Memory.target_id`, `Memory.memory_type`, `Memory.visibility`, and optionally the vector index on `Memory.embedding`.
- **Existing code:** `GraphClient` from `src/sidestage/graph/client.py` and `QueryError` from `src/sidestage/graph/errors.py`.

## File to Create

`/home/harald/src/sidestage/src/sidestage/memory/store.py`

Also update `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` to re-export the public API from this module.

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_memory_store.py`. All tests use a mocked `GraphClient` following the existing pattern in `tests/unit/test_graph_entities.py` and `tests/unit/test_graph_relationships.py`.

```python
# tests/unit/test_memory_store.py

"""Unit tests for memory store CRUD and search operations."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.memory.models import Memory, MemoryType, ContextMemories
from sidestage.memory.store import (
    MEMORY_REL_TYPES,
    upsert_memory,
    upsert_scene_memory,
    upsert_common_scene_memory,
    upsert_character_memory,
    upsert_world_fact,
    get_scene_memory,
    get_common_scene_memory,
    get_character_memory,
    get_memories_for_context,
    get_all_memories,
    delete_memory,
    touch_memory,
    search_similar,
)
from sidestage.graph.errors import QueryError


# --- Fixtures ---


@pytest.fixture
def mock_client():
    """Creates a MagicMock GraphClient with graph.query as AsyncMock."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client


# --- Relationship type validation ---

# Test: MEMORY_REL_TYPES contains exactly HAS_MEMORY and ABOUT

# --- Upsert operations ---

# Test: upsert_memory creates new Memory node with correct labels (Memory:SceneMemory)
# Test: upsert_memory creates HAS_MEMORY and ABOUT relationships for private memory
# Test: upsert_memory for common memory creates ABOUT relationship without HAS_MEMORY (no owner)
# Test: upsert_memory updates content and updated_at when memory already exists
# Test: upsert_memory preserves id and created_at on update
# Test: upsert_scene_memory creates private scene memory with correct owner_id and target_id
# Test: upsert_common_scene_memory creates common scene memory with owner_id=None
# Test: upsert_character_memory creates private character memory
# Test: upsert_world_fact with visibility="common" creates common world fact
# Test: upsert_world_fact with visibility="private" creates private world fact with owner

# --- Read operations ---

# Test: get_scene_memory returns memory for matching owner_id + scene_id
# Test: get_scene_memory returns None when no memory exists
# Test: get_common_scene_memory returns common scene memory
# Test: get_character_memory returns memory for matching owner + about_character
# Test: get_character_memory returns None for non-existent pair
# Test: get_memories_for_context returns all applicable memories in a single call
# Test: get_memories_for_context returns common memories even with no private memories
# Test: get_memories_for_context returns world facts connected to entities in the scene
# Test: get_all_memories returns all memories for an owner
# Test: get_all_memories filters by memory_type when specified

# --- Delete / Touch ---

# Test: delete_memory removes node and all relationships
# Test: delete_memory is no-op for non-existent id
# Test: touch_memory increments access_count
# Test: touch_memory updates last_accessed_at

# --- Vector search ---

# Test: search_similar returns memories ordered by score
# Test: search_similar post-filters by owner_id when specified
# Test: search_similar post-filters by visibility when specified
# Test: search_similar returns empty list when no vector index exists

# --- Cypher safety ---

# Test: store validates relationship types against MEMORY_REL_TYPES
# Test: store uses parameterized queries (no string interpolation of user values)
```

### Test Details and Mock Patterns

The mock pattern matches the existing codebase. Each test creates a `mock_client` fixture with `client.graph.query` as an `AsyncMock`. Query results are set via `return_value` or `side_effect`.

**Upsert tests** verify that:
- The Cypher query sent to `client.graph.query` contains `MERGE` patterns (not `CREATE`, since upserts use MERGE).
- Correct labels appear in the Cypher: `Memory:SceneMemory` for scene memories, `Memory:CharacterMemory` for character memories, `Memory:WorldFact` for world facts.
- For private memories (owner_id is not None), the Cypher creates a `HAS_MEMORY` relationship from owner to Memory and an `ABOUT` relationship from Memory to target.
- For common memories (owner_id is None), only the `ABOUT` relationship is created; no `HAS_MEMORY` edge exists.
- The returned `Memory` object has the expected fields populated.
- On update (memory already exists), `content` and `updated_at` are overwritten but `id` and `created_at` are preserved (verified by inspecting Cypher SET vs ON CREATE SET clauses).

**Convenience wrapper tests** (e.g., `upsert_scene_memory`) should verify they delegate to `upsert_memory` with the correct `memory_type`, `visibility`, `owner_id`, and `target_id`. These can be tested by mocking `upsert_memory` itself or by inspecting the Cypher generated.

**Read tests** verify:
- The correct MATCH + WHERE Cypher is generated with parameterized values.
- When `result_set` is empty, `None` (or empty list) is returned.
- `get_memories_for_context` returns a `ContextMemories` dataclass grouping memories correctly.

**Delete/touch tests** verify:
- `delete_memory` generates `DETACH DELETE` Cypher.
- `touch_memory` generates a SET with `access_count` increment and `last_accessed_at` update.

**Vector search tests** verify:
- `search_similar` generates a Cypher query using `db.idx.vector.queryNodes` (FalkorDB vector search procedure).
- Results are returned as `(Memory, float)` tuples sorted by score descending.
- Post-filtering by `owner_id` and `visibility` appears in the WHERE clause.
- When the vector index does not exist (query raises), an empty list is returned gracefully.

**Cypher safety tests** verify:
- All user-provided values (content, owner_id, target_id, etc.) are passed as Cypher parameters (`$param`), never interpolated into query strings.
- The `MEMORY_REL_TYPES` frozenset is used for any dynamic relationship type reference.

## Implementation Details

### Module Structure

`/home/harald/src/sidestage/src/sidestage/memory/store.py`

```python
"""Memory CRUD operations and vector search for FalkorDB.

All Cypher for Memory nodes lives here. Does NOT use graph/entities.py
or graph/relationships.py. Memory nodes use :Memory labels, not :Entity.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from sidestage.memory.models import Memory, MemoryType, ContextMemories
from sidestage.graph.errors import QueryError

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

MEMORY_REL_TYPES = frozenset({"HAS_MEMORY", "ABOUT"})
```

### Graph Labels

Each memory type gets a dual label:
- `Memory:SceneMemory` for `MemoryType.SCENE`
- `Memory:CharacterMemory` for `MemoryType.CHARACTER`
- `Memory:WorldFact` for `MemoryType.WORLD_FACT`

A helper mapping from `MemoryType` to the sub-label string should be defined:

```python
_TYPE_TO_SUBLABEL: dict[MemoryType, str] = {
    MemoryType.SCENE: "SceneMemory",
    MemoryType.CHARACTER: "CharacterMemory",
    MemoryType.WORLD_FACT: "WorldFact",
}
```

### Core Upsert: `upsert_memory`

This is the single workhorse function. All convenience wrappers delegate to it.

**Uniqueness key:**
- For private memories (owner_id is not None): `(owner_id, memory_type, target_id)`
- For common memories (owner_id is None): `(memory_type, visibility, target_id)`

**Cypher strategy:** Use `MERGE` on the uniqueness key properties. Use `ON CREATE SET` for fields that should only be set on creation (id, created_at, access_count). Use `SET` for fields that update every time (content, updated_at, gametime).

**For private memories (owner_id is not None):**

```
MERGE (m:Memory:SceneMemory {owner_id: $owner_id, memory_type: $memory_type, target_id: $target_id})
ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0
SET m.content = $content, m.updated_at = $now, m.visibility = $visibility, m.gametime = $gametime
WITH m
// Ensure HAS_MEMORY relationship from owner
OPTIONAL MATCH (owner {id: $owner_id})
FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |
  MERGE (owner)-[:HAS_MEMORY]->(m)
)
// Ensure ABOUT relationship to target
OPTIONAL MATCH (target {id: $target_id})
FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |
  MERGE (m)-[:ABOUT]->(target)
)
RETURN m
```

**For common memories (owner_id is None):**

The same pattern but the MERGE key omits `owner_id` and includes `visibility`. The `HAS_MEMORY` relationship is skipped since there is no owner.

```
MERGE (m:Memory:SceneMemory {memory_type: $memory_type, visibility: $visibility, target_id: $target_id})
ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0
SET m.content = $content, m.updated_at = $now, m.gametime = $gametime
WITH m
OPTIONAL MATCH (target {id: $target_id})
FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |
  MERGE (m)-[:ABOUT]->(target)
)
RETURN m
```

The function returns a `Memory` object constructed from the returned node properties. A new UUID is generated for the `id` parameter before the query, but `ON CREATE SET` ensures it is only applied when the node is first created.

**Signature:**

```python
async def upsert_memory(
    client: GraphClient,
    memory_type: MemoryType,
    visibility: str,
    owner_id: str | None,
    target_id: str,
    content: str,
    gametime: int | None = None,
) -> Memory:
    """Create or update a memory.

    Uniqueness key: (owner_id, memory_type, target_id) for private memories,
    or (memory_type, visibility, target_id) for common memories (owner_id is None).

    Uses MERGE in Cypher. Creates HAS_MEMORY and ABOUT relationships
    if this is a new memory. Returns the Memory object.
    """
```

### Convenience Wrappers

Each wrapper delegates to `upsert_memory` with predetermined arguments:

```python
async def upsert_scene_memory(client, owner_id, scene_id, content, gametime=None) -> Memory:
    """Upsert a character's private scene memory."""
    # Calls upsert_memory(client, MemoryType.SCENE, "private", owner_id, scene_id, content, gametime)

async def upsert_common_scene_memory(client, scene_id, content, gametime=None) -> Memory:
    """Upsert the common scene memory (visibility=common, no owner)."""
    # Calls upsert_memory(client, MemoryType.SCENE, "common", None, scene_id, content, gametime)

async def upsert_character_memory(client, owner_id, about_character_id, content, gametime=None) -> Memory:
    """Upsert a character's memory about another character."""
    # Calls upsert_memory(client, MemoryType.CHARACTER, "private", owner_id, about_character_id, content, gametime)

async def upsert_world_fact(client, about_entity_id, content, visibility="common", owner_id=None) -> Memory:
    """Upsert a world fact. Common by default, or private to a specific character."""
    # Calls upsert_memory(client, MemoryType.WORLD_FACT, visibility, owner_id, about_entity_id, content)
```

### Read Operations

**`get_scene_memory`** -- Match by owner_id, memory_type=scene, target_id=scene_id:

```python
async def get_scene_memory(client, owner_id, scene_id) -> Memory | None:
    """Get a character's private scene memory."""
    # MATCH (m:Memory:SceneMemory {owner_id: $owner_id, memory_type: "scene", target_id: $scene_id})
    # RETURN m
```

**`get_common_scene_memory`** -- Match by visibility=common, memory_type=scene, target_id:

```python
async def get_common_scene_memory(client, scene_id) -> Memory | None:
    """Get the common scene memory."""
    # MATCH (m:Memory:SceneMemory {visibility: "common", memory_type: "scene", target_id: $scene_id})
    # WHERE m.owner_id IS NULL
    # RETURN m
```

**`get_character_memory`** -- Match by owner_id, memory_type=character, target_id=about_character_id:

```python
async def get_character_memory(client, owner_id, about_character_id) -> Memory | None:
    """Get a character's memory about another character."""
```

**`get_memories_for_context`** -- This is the key function for context assembly. It fetches all memories applicable to a character in a scene in a single call (or minimal round-trips).

```python
async def get_memories_for_context(
    client: GraphClient,
    character_id: str,
    scene_id: str,
    present_character_ids: list[str],
) -> ContextMemories:
    """Fetch all memories needed for a character's context assembly.

    Returns a ContextMemories object containing:
    - common_scene_memory: The common scene memory (if any)
    - private_scene_memory: This character's private scene memory (if any)
    - character_memories: dict of character_id -> Memory for present characters
    - world_facts: list of common world facts relevant to entities in the scene

    Uses parallel queries or a batch Cypher query internally to minimize
    round-trips to FalkorDB.
    """
```

The implementation strategy for `get_memories_for_context` should use multiple targeted queries (one for common scene memory, one for private scene memory, one for character memories about present characters, one for common world facts). These can be run with `asyncio.gather` for parallelism. Alternatively, a single complex Cypher with `UNION ALL` could be used, but separate queries are easier to test and debug.

The character memories query matches on `owner_id = character_id`, `memory_type = "character"`, and `target_id IN $present_character_ids`.

The world facts query matches on `memory_type = "world_fact"` and `visibility = "common"`. It finds world facts `ABOUT` entities that are related to the scene (connected via `ABOUT` or other entity relationships). A simpler initial implementation can fetch all common world facts and leave scene-relevance filtering for a later optimization.

**`get_all_memories`** -- Fetch all memories for an owner, with optional type filter:

```python
async def get_all_memories(client, owner_id, memory_type=None) -> list[Memory]:
    """Get all memories owned by a character, optionally filtered by type."""
    # MATCH (m:Memory {owner_id: $owner_id})
    # [WHERE m.memory_type = $memory_type]
    # RETURN m
```

### Delete and Touch

```python
async def delete_memory(client, memory_id) -> None:
    """Delete a memory and its relationships.

    Uses DETACH DELETE. Idempotent -- succeeds silently if memory_id does not exist.
    """
    # MATCH (m:Memory {id: $id}) DETACH DELETE m

async def touch_memory(client, memory_id) -> None:
    """Increment access_count and update last_accessed_at.

    Called during context assembly. Separate from get to avoid
    inflating counts during debugging/admin.
    """
    # MATCH (m:Memory {id: $id})
    # SET m.access_count = m.access_count + 1, m.last_accessed_at = $now
```

### Vector Search

```python
async def search_similar(
    client: GraphClient,
    query_embedding: list[float],
    owner_id: str | None = None,
    visibility: str | None = None,
    limit: int = 10,
) -> list[tuple[Memory, float]]:
    """Find memories similar to query embedding.

    Uses FalkorDB vector index via CALL db.idx.vector.queryNodes('Memory', 'embedding', $k, vecf32($vec)).
    Post-filters by owner_id and/or visibility in the WHERE clause.
    Returns (Memory, similarity_score) tuples ordered by score descending.

    Returns empty list if the vector index does not exist or the query fails
    (graceful degradation).
    """
```

The FalkorDB vector search uses the procedure call syntax:

```cypher
CALL db.idx.vector.queryNodes('Memory', 'embedding', $limit, vecf32($vec))
YIELD node, score
WHERE (node.owner_id = $owner_id OR $owner_id IS NULL)
  AND (node.visibility = $visibility OR $visibility IS NULL)
RETURN node, score
ORDER BY score DESC
```

Note: The `vecf32()` function is used to serialize the embedding vector for FalkorDB. The implementer should check whether the FalkorDB Python client version supports passing lists directly or requires explicit serialization. If `vecf32()` is not available as a Cypher function, the vector may need to be serialized using `falkordb.utils.vecf32()` in Python before passing as a parameter.

The function should catch exceptions from the vector query (e.g., index does not exist) and return an empty list, logging a warning. This ensures the system degrades gracefully when no vector index is configured.

### Memory Node Deserialization

A helper function should convert a FalkorDB node (with `.properties` dict) into a `Memory` Pydantic model:

```python
def _node_to_memory(node) -> Memory:
    """Convert a FalkorDB node to a Memory model."""
    # node.properties contains all the stored fields
    # Construct Memory(**node.properties)
```

This is analogous to `node_to_entity` in `graph/entities.py` but simpler since there is only one model type (`Memory`). The `embedding` field may be stored as a special vector type by FalkorDB and might need conversion to a plain `list[float]`.

### Error Handling

Follow the existing pattern from `graph/entities.py`:
- Wrap FalkorDB exceptions in `QueryError` from `sidestage.graph.errors`
- Log at appropriate levels (info for mutations, debug for reads)
- All user-provided values must be passed as Cypher parameters (never string-interpolated)

### Package Init Update

Update `/home/harald/src/sidestage/src/sidestage/memory/__init__.py` to export the public store functions:

```python
from sidestage.memory.store import (
    MEMORY_REL_TYPES,
    upsert_memory,
    upsert_scene_memory,
    upsert_common_scene_memory,
    upsert_character_memory,
    upsert_world_fact,
    get_scene_memory,
    get_common_scene_memory,
    get_character_memory,
    get_memories_for_context,
    get_all_memories,
    delete_memory,
    touch_memory,
    search_similar,
)
```

## Key Design Decisions

1. **Own Cypher, not Entity functions.** Memory nodes use `:Memory` labels (not `:Entity`). The existing Entity operations have constraints (unique id, mandatory name) that do not apply to Memory nodes. All Memory Cypher lives in `memory/store.py`.

2. **MERGE-based upserts.** Each `(owner_id, memory_type, target_id)` tuple is unique. MERGE ensures idempotent create-or-update semantics. `ON CREATE SET` handles initial values; `SET` handles fields that update every time.

3. **Relationships managed inline.** The `HAS_MEMORY` and `ABOUT` relationships are created/maintained within the upsert Cypher itself, using `MERGE` to ensure idempotency. They are not managed via `graph/relationships.py`.

4. **Parameterized queries only.** All user-provided values (`content`, `owner_id`, `target_id`, etc.) must be Cypher parameters. The only dynamic parts of the query string are the label names, which come from the internal `_TYPE_TO_SUBLABEL` mapping (a hardcoded dict of enum values to safe strings).

5. **Vector search is a future-facing feature.** The primary retrieval path for context assembly is `get_memories_for_context`, which uses graph traversal. `search_similar` is available but not used in the core flow yet.