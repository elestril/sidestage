Now I have comprehensive context. Let me generate the section content.

# Section 07: Importer

## Overview

This section implements `src/sidestage/migration/importer.py`, which orchestrates the full campaign import process: setting health to DEGRADED, dropping and recreating the FalkorDB graph, inserting entities with their relationships, inserting memories with HAS_MEMORY/ABOUT edges, restoring chat logs from parsed chatlog.log files, verifying counts, and restoring health to HEALTHY. The importer consumes the output of the parser (section-04) and validator (section-05) and interacts with the graph layer, memory store, and SQLite storage.

### Dependencies

- **section-01-data-models**: Provides `MigrationImportResult`, `MigrationValidationReport`, `ParseResult` from `migration/models.py`
- **section-02-serialization**: Provides `frontmatter_dict_to_entity()`, `frontmatter_dict_to_memory()` from `migration/serialization.py`
- **section-04-parser**: Provides `parse_directory()` from `migration/parser.py`, which returns a `ParseResult` containing entities, memories, chatlogs, and errors
- **section-05-validator**: Provides `validate()` from `migration/validator.py`, which returns a `MigrationValidationReport`

All four must be implemented before this section.

### What This Section Produces

- **File**: `/home/harald/src/sidestage/src/sidestage/migration/importer.py`
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_importer.py`

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_importer.py` with the following test stubs. Tests use `pytest` with `pytest-anyio` for async tests. All FalkorDB and SQLite interactions are mocked; no real database is required.

```python
"""Tests for migration/importer.py -- import campaign from parsed data into FalkorDB."""

from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path

import pytest

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.importer import import_campaign
from sidestage.schemas import Character, Location, Item, Scene, Event, JoinEvent, ChatMessage


# --- Fixtures ---

@pytest.fixture
def mock_graph_client():
    """Mock GraphClient with graph.query and graph.delete capabilities."""
    client = MagicMock()
    client.graph = AsyncMock()
    client.graph.query = AsyncMock()
    client.graph.delete = AsyncMock()
    client.db = MagicMock()
    client.graph_name = "test_campaign"
    # db.select_graph returns a new mock graph
    client.db.select_graph = MagicMock(return_value=client.graph)
    return client


@pytest.fixture
def mock_campaign(mock_graph_client, tmp_path):
    """Mock Campaign object with graph_client, storage, health, and campaign_dir."""
    campaign = MagicMock()
    campaign.graph_client = mock_graph_client
    campaign.campaign_dir = tmp_path
    campaign.health = CampaignHealth()
    campaign.storage = MagicMock()
    campaign.storage.update_scene = MagicMock()
    campaign.name = "test_campaign"
    campaign.config = MagicMock()
    campaign.config.graph = MagicMock()
    campaign.config.graph.vector_dimension = None
    return campaign


@pytest.fixture
def mock_sync_manager():
    """Mock SyncManager for broadcast assertions."""
    sm = MagicMock()
    sm.broadcast = AsyncMock()
    return sm


@pytest.fixture
def sample_parse_result():
    """Return a ParseResult with representative entities, memories, and chatlogs.

    Should contain:
    - Characters (one with location_id, one without)
    - Locations (with connected_locations forming a pair)
    - Items
    - A Scene with location_id
    - A JoinEvent with scene_id
    - Memories with various owner_id/target_id combos
    - A chatlog dict mapping scene_id -> list of ChatMessage
    """
    ...


# --- Concurrency guard tests ---

@pytest.mark.anyio
async def test_sets_health_degraded_before_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """import_campaign sets campaign.health to DEGRADED with reason before starting graph operations."""
    ...


@pytest.mark.anyio
async def test_restores_health_healthy_after_successful_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """After a successful import, campaign.health is restored to HEALTHY."""
    ...


@pytest.mark.anyio
async def test_restores_health_healthy_after_failed_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """If import fails (e.g., graph drop raises), health is still restored to HEALTHY."""
    ...


# --- Graph lifecycle tests ---

@pytest.mark.anyio
async def test_drops_and_recreates_graph(mock_campaign, sample_parse_result, mock_sync_manager):
    """import_campaign calls graph.delete() then db.select_graph() and initialize_schema()."""
    ...


@pytest.mark.anyio
async def test_graph_drop_failure_aborts_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """If graph.delete() raises, the import aborts and returns a failed result."""
    ...


# --- Entity insertion tests ---

@pytest.mark.anyio
async def test_inserts_all_entities_via_create_entity(mock_campaign, sample_parse_result, mock_sync_manager):
    """Every entity in the ParseResult is inserted via graph create_entity()."""
    ...


# --- Relationship creation tests ---

@pytest.mark.anyio
async def test_creates_located_in_edges_for_characters(mock_campaign, mock_sync_manager):
    """Characters with a location_id get a LOCATED_IN edge to that location."""
    ...


@pytest.mark.anyio
async def test_creates_connects_to_edges_deduplicated(mock_campaign, mock_sync_manager):
    """CONNECTS_TO edges are created once per pair, not twice for A->B and B->A."""
    ...


@pytest.mark.anyio
async def test_creates_at_location_edges_for_scenes(mock_campaign, mock_sync_manager):
    """Scenes with a location_id get an AT_LOCATION edge to that location."""
    ...


@pytest.mark.anyio
async def test_creates_has_event_edges_for_events(mock_campaign, mock_sync_manager):
    """Events with a scene_id get a HAS_EVENT edge from the scene."""
    ...


# --- Memory insertion tests ---

@pytest.mark.anyio
async def test_inserts_memories_with_has_memory_and_about(mock_campaign, sample_parse_result, mock_sync_manager):
    """All memories from ParseResult are inserted via upsert_memory with correct relationships."""
    ...


@pytest.mark.anyio
async def test_skips_embedding_generation_during_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """Embedding generation is not triggered during import (health is DEGRADED, is_embedding_available=False)."""
    ...


# --- Chat log restoration tests ---

@pytest.mark.anyio
async def test_restores_chat_logs_via_storage(mock_campaign, mock_sync_manager):
    """Chat logs from ParseResult are restored via campaign.storage.update_scene()."""
    ...


# --- Post-import verification tests ---

@pytest.mark.anyio
async def test_verifies_entity_counts_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """After import, the importer queries entity counts and includes them in the result."""
    ...


@pytest.mark.anyio
async def test_clears_active_scenes_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """Active scenes dict on the orchestrator is cleared after import completes."""
    ...


@pytest.mark.anyio
async def test_broadcasts_entities_updated_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
    """After import, a WebSocket broadcast of entities_updated is sent."""
    ...
```

### Key testing principles

- **Mock the graph layer**: Mock `create_entity` from `sidestage.graph.entities`, `link` from `sidestage.graph.relationships`, and `upsert_memory` from `sidestage.memory.store`. Patch these at the module level where they are imported in `importer.py`.
- **Use a real `CampaignHealth`**: The `CampaignHealth` class from `sidestage.health` is lightweight and has no external dependencies. Use a real instance to test status transitions (HEALTHY -> DEGRADED -> HEALTHY).
- **Mock storage**: `campaign.storage.update_scene()` is synchronous. Mock it to capture calls for chat log restoration verification.
- **Mock SyncManager**: Pass a mock with `broadcast = AsyncMock()` to verify the `entities_updated` message is sent.
- **ParseResult fixture**: Build a `ParseResult` (from `migration/models.py`) containing entities, memories, and chatlogs. The importer receives this already-parsed data; it does not read the filesystem itself.
- **Relationship deduplication**: For the CONNECTS_TO test, set up two locations each referencing the other in their `connected_locations` list and verify only one CONNECTS_TO edge is created (not two).

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/migration/importer.py`

The importer module provides a single top-level async function `import_campaign()` that orchestrates the entire import process. It receives a pre-parsed `ParseResult` (from `migration/parser.py`) and a validated `MigrationValidationReport` (from `migration/validator.py`), rather than reading the filesystem directly.

### Function signature

```python
async def import_campaign(
    campaign,
    parse_result: ParseResult,
    sync_manager=None,
    active_scenes: dict | None = None,
) -> MigrationImportResult:
    """Import parsed entities and memories into FalkorDB, replacing the existing graph.

    This is a destructive operation: the existing graph is dropped and recreated.

    Args:
        campaign: The Campaign object (provides graph_client, storage, health, config).
        parse_result: The parsed directory tree (entities, memories, chatlogs, errors).
        sync_manager: Optional SyncManager for broadcasting entities_updated.
        active_scenes: Optional dict of active scenes to clear after import.

    Returns:
        MigrationImportResult with counts of processed entities and memories.
    """
```

### Import process (step by step)

**Step 1 -- Set health to DEGRADED**

```python
await campaign.health.set_status(HealthStatus.DEGRADED, "Importing campaign data")
```

This signals to the rest of the application that the graph is being rebuilt. Key effects:
- `campaign.health.is_accepting_chat` remains `True` (DEGRADED still allows reads)
- `campaign.health.is_embedding_available` becomes `False` (blocks embedding generation during import)

The entire remainder of the import must be wrapped in a `try/finally` block to ensure health is restored to HEALTHY regardless of success or failure.

**Step 2 -- Drop the existing graph**

The FalkorDB async graph object exposes a `delete()` method that drops the entire graph (all nodes, edges, indexes, constraints). Call:

```python
await campaign.graph_client.graph.delete()
```

After deletion, re-select the graph to get a fresh handle:

```python
campaign.graph_client.graph = campaign.graph_client.db.select_graph(
    campaign.graph_client.graph_name
)
```

If `graph.delete()` raises an exception, the import aborts immediately. The old graph data may still be intact (FalkorDB delete is atomic). Catch the exception, restore health, and return a failed `MigrationImportResult`.

**Step 3 -- Recreate schema**

After dropping the graph, all indexes and constraints are gone. Re-run schema initialization:

```python
from sidestage.graph.schema import initialize_schema

await initialize_schema(
    campaign.graph_client,
    vector_dimension=campaign.config.graph.vector_dimension,
)
```

This recreates all Entity indexes/constraints (v1 migration) and Memory indexes/vector index (v2 migration) as defined in `graph/schema.py`. The `vector_dimension` comes from the campaign's graph config and may be `None` if no embedding model is configured.

**Step 4 -- Insert entities**

Iterate over `parse_result.entities` (a list of `Entity` objects, already deserialized by the parser). For each entity, call:

```python
from sidestage.graph.entities import create_entity

await create_entity(campaign.graph_client, entity)
```

`create_entity()` converts the entity to graph node properties (via `entity_to_properties()`) and runs a `CREATE` Cypher query. It handles label assignment (e.g., `Entity:Character`) and raises `DuplicateEntityError` on constraint violations.

Track successfully inserted count in `processed_entities`. If an individual insert fails, log the error, add to the errors list, and continue with the next entity.

**Step 5 -- Create entity-to-entity relationships**

After all entities are inserted, create the relationship edges. There are four types, each derived from entity fields:

1. **LOCATED_IN** (Character -> Location): For each Character entity that has a non-None `location_id`, create an edge:
   ```python
   from sidestage.graph.relationships import link
   await link(client, character.id, "LOCATED_IN", character.location_id)
   ```

2. **CONNECTS_TO** (Location <-> Location): For each Location entity, iterate its `connected_locations` list. To avoid duplicating bidirectional edges (A->B and B->A), maintain a `set` of `frozenset({a_id, b_id})` pairs already linked. Only create the edge if the pair is not already in the set:
   ```python
   connected_pairs: set[frozenset[str]] = set()
   for location in locations:
       for other_id in location.connected_locations:
           pair = frozenset({location.id, other_id})
           if pair not in connected_pairs:
               await link(client, location.id, "CONNECTS_TO", other_id)
               connected_pairs.add(pair)
   ```

3. **AT_LOCATION** (Scene -> Location): For each Scene with a non-None `location_id`:
   ```python
   await link(client, scene.id, "AT_LOCATION", scene.location_id)
   ```

4. **HAS_EVENT** (Scene -> Event): For each Event (including ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent) with a `scene_id`:
   ```python
   await link(client, event.scene_id, "HAS_EVENT", event.id)
   ```

Wrap each `link()` call in try/except. If the target entity does not exist (e.g., a Character references a Location ID that was not in the import set), `link()` raises `EntityNotFoundError`. Log the error and continue.

**Step 6 -- Insert memories**

For each memory in `parse_result.memories` (a list of `Memory` objects), insert it into the graph. The `upsert_memory()` function in `memory/store.py` handles creating the Memory node AND the HAS_MEMORY/ABOUT relationships in a single Cypher MERGE query. However, `upsert_memory()` generates a new `id` and uses MERGE keys that may not match the imported memory's existing id.

Instead, the importer should insert memories using a direct Cypher query that preserves the original memory ID, content, and all fields from the parsed `Memory` object. Create a helper function `_insert_memory()` that:

1. Creates the Memory node with the sublabel from `MemoryType` (SceneMemory, CharacterMemory, WorldFact)
2. Sets all properties from the `Memory` model (id, content, memory_type, visibility, owner_id, target_id, gametime, created_at, updated_at, access_count)
3. Does NOT set `embedding` (embeddings are regenerated later, not stored on disk)
4. Creates HAS_MEMORY relationship from owner entity (if owner_id is not None)
5. Creates ABOUT relationship to target entity

```python
async def _insert_memory(client: GraphClient, memory: Memory) -> None:
    """Insert a memory node with HAS_MEMORY and ABOUT relationships.

    Uses CREATE (not MERGE) since we are starting from an empty graph.
    Preserves the original memory ID from the import data.
    """
```

The sublabel mapping follows `memory/store.py`:
- `MemoryType.SCENE` -> `SceneMemory`
- `MemoryType.CHARACTER` -> `CharacterMemory`
- `MemoryType.WORLD_FACT` -> `WorldFact`

Embedding generation is intentionally skipped during import. The `is_embedding_available` property on `CampaignHealth` returns `False` when status is DEGRADED, so any background embedding tasks that check this flag will skip processing. The importer itself never calls any embedding function.

Track `processed_memories` count. If an individual insert fails, log the error, add to errors, continue.

**Step 7 -- Restore chat logs**

The `parse_result.chatlogs` dict maps scene IDs to lists of `ChatMessage` objects (parsed from `chatlog.log` files by the parser). For each scene with chat messages:

1. Retrieve the existing Scene from SQLite storage: `scene = campaign.storage.get_scene(scene_id)`.
2. If the scene exists in storage, update its messages: `scene.messages = messages`, then `campaign.storage.update_scene(scene)`.
3. If the scene does not exist in storage (but was inserted into the graph in step 4), create a minimal Scene object and save it: use `campaign.storage.add_scene(scene_with_messages)`.

This restores the SQLite-stored chat history, which the graph does not store (messages are in `EXCLUDED_FIELDS` for Scene nodes).

**Step 8 -- Verify counts**

After all inserts, query the graph to verify the expected number of entities and memories were inserted:

```python
from sidestage.graph.entities import list_entities
inserted_entities = await list_entities(campaign.graph_client)
```

For memories, run a count query:
```
MATCH (m:Memory) RETURN count(m) as count
```

Compare against expected counts from `parse_result`. Log warnings if counts do not match but do not treat as a fatal error.

**Step 9 -- Post-import cleanup and notification**

1. Restore health:
   ```python
   await campaign.health.set_status(HealthStatus.HEALTHY, "")
   ```

2. Clear active scenes (if the `active_scenes` dict was provided):
   ```python
   if active_scenes is not None:
       active_scenes.clear()
   ```

3. Broadcast `entities_updated` via WebSocket (if sync_manager was provided):
   ```python
   if sync_manager is not None:
       await sync_manager.broadcast({"type": "entities_updated"})
   ```

**Step 10 -- Return result**

Return a `MigrationImportResult` with:
- `phase`: `"complete"` on success, `"failed"` on error
- `total_entities`: `len(parse_result.entities)`
- `total_memories`: `len(parse_result.memories)`
- `processed_entities`: count of successfully inserted entities
- `processed_memories`: count of successfully inserted memories
- `errors`: accumulated error message strings

### Internal helper functions

```python
async def _drop_and_recreate_graph(campaign) -> None:
    """Drop the existing graph and reinitialize the schema.

    Calls graph.delete(), re-selects the graph, and runs initialize_schema().
    Raises on failure (caller handles cleanup).
    """
    ...


async def _insert_entities(client: GraphClient, entities: list[Entity]) -> tuple[int, list[str]]:
    """Insert all entities into the graph. Returns (success_count, errors)."""
    ...


async def _create_relationships(client: GraphClient, entities: list[Entity]) -> list[str]:
    """Create all entity-to-entity relationship edges. Returns list of error messages.

    Handles LOCATED_IN, CONNECTS_TO (deduplicated), AT_LOCATION, HAS_EVENT.
    """
    ...


async def _insert_memories(client: GraphClient, memories: list[Memory]) -> tuple[int, list[str]]:
    """Insert all memories with HAS_MEMORY/ABOUT relationships. Returns (success_count, errors)."""
    ...


async def _insert_memory(client: GraphClient, memory: Memory) -> None:
    """Insert a single memory node with relationships. Uses CREATE, not MERGE."""
    ...


def _restore_chatlogs(campaign, chatlogs: dict[str, list[ChatMessage]]) -> list[str]:
    """Restore chat logs to SQLite storage. Returns list of error messages."""
    ...
```

### CONNECTS_TO deduplication explained

Locations store `connected_locations` as a list of IDs. If Location A lists Location B, and Location B lists Location A, only ONE CONNECTS_TO edge should be created (A -> B). The deduplication strategy uses a set of frozensets:

```python
connected_pairs: set[frozenset[str]] = set()
for location in locations:
    for other_id in location.connected_locations:
        pair = frozenset({location.id, other_id})
        if pair not in connected_pairs:
            await link(client, location.id, "CONNECTS_TO", other_id)
            connected_pairs.add(pair)
```

The `get_related()` function in `graph/relationships.py` uses direction `"both"` when querying CONNECTS_TO, so a single directional edge (A -> B) is traversable from both sides.

### Memory insertion Cypher pattern

The `_insert_memory()` helper constructs a Cypher query similar to `upsert_memory()` in `memory/store.py` but uses `CREATE` instead of `MERGE` (since the graph was just recreated and is empty). The query preserves the original memory `id` from the import data:

```cypher
CREATE (m:Memory:{sublabel} {
    id: $id, content: $content, memory_type: $memory_type,
    visibility: $visibility, owner_id: $owner_id, target_id: $target_id,
    gametime: $gametime, created_at: $created_at, updated_at: $updated_at,
    access_count: $access_count
})
WITH m
OPTIONAL MATCH (owner:Entity {id: $owner_id})
FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |
  CREATE (owner)-[:HAS_MEMORY]->(m)
)
WITH m
OPTIONAL MATCH (target:Entity {id: $target_id})
FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |
  CREATE (m)-[:ABOUT]->(target)
)
```

This pattern is taken directly from the existing `upsert_memory()` Cypher in `memory/store.py`, adapted to use CREATE and preserve the original ID.

### Imports needed

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sidestage.graph.entities import create_entity, list_entities
from sidestage.graph.relationships import link
from sidestage.graph.schema import initialize_schema
from sidestage.health import HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import MigrationImportResult, ParseResult
from sidestage.schemas import Character, Entity, Event, Location, Scene, ChatMessage

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.graph.client import GraphClient
    from sidestage.sync import SyncManager

logger = logging.getLogger(__name__)
```

### Error recovery details

The import function wraps the entire process in a `try/finally` to guarantee health restoration:

```python
async def import_campaign(campaign, parse_result, sync_manager=None, active_scenes=None):
    errors: list[str] = []
    processed_entities = 0
    processed_memories = 0

    try:
        await campaign.health.set_status(HealthStatus.DEGRADED, "Importing campaign data")

        # Step 2: Drop graph
        try:
            await _drop_and_recreate_graph(campaign)
        except Exception as exc:
            errors.append(f"Graph drop failed: {exc}")
            return MigrationImportResult(
                phase="failed", total_entities=len(parse_result.entities),
                total_memories=len(parse_result.memories),
                processed_entities=0, processed_memories=0, errors=errors,
            )

        # Steps 4-8 ...
        ...

    finally:
        await campaign.health.set_status(HealthStatus.HEALTHY, "")
```

Specific failure scenarios:
- **Graph drop failure**: Abort immediately. Old graph is intact (FalkorDB delete is atomic). Return failed result.
- **Schema initialization failure**: Abort. Graph is empty but unindexed. Return failed result.
- **Individual entity insert failure**: Log error, skip entity, continue with remaining entities. Partial import is allowed.
- **Individual relationship creation failure**: Log error, continue. Missing edges are non-fatal.
- **Individual memory insert failure**: Log error, continue. Missing memories are non-fatal.
- **Chat log restoration failure**: Log error, continue. Chat history can be lost in a partial import.
- **Health is always restored**: The `finally` block guarantees HEALTHY status even on unhandled exceptions.

### Relationship to existing code

- **`campaign.import_entities()` in `campaign.py`**: The old import function reads flat `.md` files from `campaign_dir/entities/` and inserts entities one by one without dropping the graph first. The new importer replaces this behavior entirely for the migration workflow but the old function remains in place for backward compatibility.
- **`create_entity()` from `graph/entities.py`**: Reused directly. Handles label assignment via `MODEL_TO_LABELS` and property conversion via `entity_to_properties()` (which excludes fields like `connected_locations`, `messages`, `widget`).
- **`link()` from `graph/relationships.py`**: Reused for LOCATED_IN, CONNECTS_TO, AT_LOCATION, HAS_EVENT edges. Validates rel_type against `VALID_REL_TYPES` (all four are included). Checks entity existence before creating the edge and raises `EntityNotFoundError` if source or target is missing.
- **`upsert_memory()` from `memory/store.py`**: NOT reused directly because it generates a new UUID for the memory ID and uses MERGE semantics. The importer uses a custom `_insert_memory()` that preserves the original memory ID and uses CREATE.
- **`initialize_schema()` from `graph/schema.py`**: Reused to recreate indexes and constraints after dropping the graph. Accepts `vector_dimension` parameter for the optional vector index.
- **`CampaignHealth` from `health.py`**: Used directly (not mocked) in the importer. `set_status()` is async and uses a lock. The `is_embedding_available` property automatically returns False when DEGRADED.
- **`campaign.storage` (SQLite `Storage` class)**: `update_scene()` and `add_scene()` are synchronous methods on the `Storage` class. Used to restore chat logs.

### Edge cases to handle

1. **Empty parse result**: No entities, no memories. Still drop and recreate the graph (clean slate). Return result with zero counts.
2. **No graph client**: If `campaign.graph_client` is None, return a failed result immediately.
3. **Duplicate entity IDs in parse result**: The parser resolves duplicates (last-wins) before the importer receives them. If a `DuplicateEntityError` is raised by `create_entity()`, it is caught and logged but should not happen in practice.
4. **Memory with owner_id referencing a non-imported entity**: The `_insert_memory()` Cypher uses `OPTIONAL MATCH` for the owner, so a missing owner simply means no HAS_MEMORY edge is created. The memory node itself is still created.
5. **Events referencing non-imported scenes**: `link()` raises `EntityNotFoundError`. Caught and logged; the event is still in the graph, just without the HAS_EVENT edge.
6. **Chatlog references a scene not in storage**: The importer creates a minimal Scene in storage to hold the messages.
7. **Re-import idempotency**: Because the graph is dropped and recreated, re-importing the same data produces the same result. This is by design (no merge/upsert complexity).