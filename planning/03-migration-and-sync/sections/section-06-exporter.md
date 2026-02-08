Good -- `models.py` is just a re-export. Now I have all the context I need. Let me generate the section content.

# Section 06: Exporter

## Overview

This section implements `src/sidestage/migration/exporter.py`, which reads all entities and memories from FalkorDB, retrieves chat logs from SQLite, and writes the complete `markdown/` directory tree using an atomic swap strategy. It also writes a `status.json` summary file.

### Dependencies

- **section-01-data-models**: Provides `MigrationBackupResult`, `BackupStatus` from `migration/models.py`
- **section-02-serialization**: Provides `entity_to_frontmatter_dict()`, `memory_to_frontmatter_dict()`, `sanitize_filename()`, `entity_type_to_subdir()`, `resolve_filename()` from `migration/serialization.py`

Both must be implemented before this section.

### What This Section Produces

- **File**: `/home/harald/src/sidestage/src/sidestage/migration/exporter.py`
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_exporter.py`

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_exporter.py` with the following test stubs. Tests use `pytest` with `pytest-anyio` for async tests and `tmp_path` for filesystem isolation. All FalkorDB and SQLite interactions are mocked.

```python
"""Tests for migration/exporter.py -- backup campaign to markdown directory."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.migration.exporter import export_campaign


# --- Fixtures ---

@pytest.fixture
def mock_graph_client():
    """Mock GraphClient with query capabilities."""
    ...

@pytest.fixture
def mock_campaign(mock_graph_client, tmp_path):
    """Mock Campaign object with graph_client, storage, health, and campaign_dir."""
    ...

@pytest.fixture
def sample_entities():
    """Return a list of sample Entity objects (Character, Location, Item, Scene, Event)."""
    ...

@pytest.fixture
def sample_memories():
    """Return a list of sample Memory objects with various owner_id/target_id combos."""
    ...


# --- Entity export tests ---

# Test: queries all entities from FalkorDB
async def test_queries_all_entities(mock_campaign, sample_entities):
    """export_campaign calls list_entities(client) to retrieve all entities."""
    ...

# Test: queries all memories from FalkorDB
async def test_queries_all_memories(mock_campaign, sample_memories):
    """export_campaign queries all Memory nodes from the graph."""
    ...

# Test: retrieves chat logs from SQLite for scenes
async def test_retrieves_chat_logs_for_scenes(mock_campaign, sample_entities):
    """For each Scene entity, export_campaign reads messages from storage."""
    ...

# Test: writes entity files to correct type subdirectories
async def test_writes_entities_to_correct_subdirs(mock_campaign, sample_entities, tmp_path):
    """Character -> characters/, Location -> locations/, etc."""
    ...

# Test: writes memory files to correct .d/ directories
async def test_writes_memories_to_dot_d_dirs(mock_campaign, sample_entities, sample_memories, tmp_path):
    """Memories placed inside parent entity's .d/ directory."""
    ...

# Test: writes chatlog.log to scene .d/ directories
async def test_writes_chatlog_to_scene_dot_d(mock_campaign, tmp_path):
    """Scene chat logs written as chatlog.log inside scene_name.d/."""
    ...

# Test: creates .d/ only when entity has memories or chat logs
async def test_dot_d_created_only_when_needed(mock_campaign, sample_entities, tmp_path):
    """Entities without memories or chat logs should not have .d/ directories."""
    ...

# Test: writes status.json with correct counts
async def test_writes_status_json(mock_campaign, sample_entities, sample_memories, tmp_path):
    """status.json contains entity counts, memory count, chatlog count, timestamp."""
    ...

# Test: atomic backup via temp dir swap (old files untouched on failure)
async def test_atomic_swap_preserves_old_on_failure(mock_campaign, tmp_path):
    """If export fails mid-write, the original markdown/ dir is preserved."""
    ...

# Test: handles filename collisions with _2, _3 suffix
async def test_filename_collision_handling(mock_campaign, tmp_path):
    """Two entities with the same sanitized name get _2 suffix."""
    ...

# Test: places memory in owner's .d/ when owner_id set
async def test_memory_placed_in_owner_dot_d(mock_campaign, sample_entities, tmp_path):
    """Memory with owner_id goes into the owner entity's .d/ directory."""
    ...

# Test: places memory in target's .d/ when owner_id is null
async def test_memory_placed_in_target_dot_d_when_no_owner(mock_campaign, sample_entities, tmp_path):
    """Memory with owner_id=None goes into target entity's .d/ directory."""
    ...

# Test: queries LOCATED_IN for character location_id in frontmatter
async def test_queries_located_in_for_characters(mock_campaign, tmp_path):
    """Character frontmatter includes location_id from LOCATED_IN relationship."""
    ...

# Test: queries CONNECTS_TO for location connected_locations in frontmatter
async def test_queries_connects_to_for_locations(mock_campaign, tmp_path):
    """Location frontmatter includes connected_locations from CONNECTS_TO edges."""
    ...
```

### Key testing principles

- Mock `list_entities()` from `sidestage.graph.entities` to return test entity lists
- Mock `graph.query()` on the client to simulate Cypher queries for memories and relationships
- Mock `campaign.storage.get_scene()` to return `Scene` objects with `messages` populated
- Use `tmp_path` for all filesystem writes -- never write to real campaign directories
- After calling `export_campaign()`, assert the directory structure and file contents match expectations
- For the atomic swap test, simulate a failure (e.g., an exception in file writing) and verify the original directory is untouched

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/migration/exporter.py`

The exporter module provides a single top-level async function `export_campaign()` that orchestrates the entire backup process.

### Function signature

```python
async def export_campaign(campaign) -> MigrationBackupResult:
    """Backup all entities, memories, and chat logs to the markdown/ directory.

    Reads from FalkorDB (entities, memories, relationships) and SQLite (chat logs).
    Writes a structured markdown/ directory tree with atomic swap.

    Args:
        campaign: The Campaign object (provides graph_client, storage, campaign_dir, health).

    Returns:
        MigrationBackupResult with counts of written entities, memories, and chatlogs.
    """
```

### Export process (step by step)

**Step 1 -- Query all entities from FalkorDB**

Call `list_entities(campaign.graph_client)` from `sidestage.graph.entities` to get all `Entity` objects. This returns Character, Location, Item, Scene, and Event subtypes.

**Step 2 -- Query all memories from FalkorDB**

Run a Cypher query directly on `campaign.graph_client.graph`:
```
MATCH (m:Memory) RETURN m
```
Convert each result node to a `Memory` model using the same `_node_to_memory` pattern from `memory/store.py`. Alternatively, import and reuse `_node_to_memory` or replicate the conversion logic locally.

**Step 3 -- Enrich entities with relationship data**

Certain entity fields are stored as graph relationships, not node properties. Before serialization, the exporter must reconstruct these fields:

- **Character.location_id**: Query `MATCH (c:Character {id: $id})-[:LOCATED_IN]->(l:Location) RETURN l.id`. Use `get_related(client, char_id, "LOCATED_IN", "outgoing")` which returns Location entities -- extract the first one's `id` if present.
- **Location.connected_locations**: Query `MATCH (l:Location {id: $id})-[:CONNECTS_TO]-(other:Location) RETURN other.id`. Use `get_related(client, loc_id, "CONNECTS_TO", "both")` -- collect all returned location IDs into a list.
- **Scene.location_id**: Query `MATCH (s:Scene {id: $id})-[:AT_LOCATION]->(l:Location) RETURN l.id`. Use `get_related(client, scene_id, "AT_LOCATION", "outgoing")`.

After querying, update the entity objects' fields before passing them to `entity_to_frontmatter_dict()`. Since Pydantic models are mutable by default, set `entity.location_id = queried_id` etc.

**Step 4 -- Retrieve chat logs from SQLite**

For each Scene entity, call `campaign.storage.get_scene(scene.id)` to get the SQLite-stored Scene which has the `messages` list populated. The graph-stored Scene does not have messages (they are in EXCLUDED_FIELDS). Format each `ChatMessage` as a line in `chatlog.log`:

```
[{walltime}] ({character_id}) {name}: "{message}"
```

Where `walltime` comes from `ChatMessage.walltime`, `character_id` from `ChatMessage.character_id`, `name` from `ChatMessage.name`, and `message` from `ChatMessage.message`.

**Step 5 -- Build directory tree in temp location**

Create a temporary directory at `campaign.campaign_dir / "markdown" / ".tmp_backup"`. Under it, create the type subdirectories (`characters/`, `locations/`, `items/`, `scenes/`, `events/`).

For each entity:
1. Call `entity_to_frontmatter_dict(entity)` from `migration/serialization.py` to get `(frontmatter_dict, body)`.
2. Determine the subdirectory via `entity_type_to_subdir(type(entity).__name__)`.
3. Generate filename via `sanitize_filename(entity.name) + ".md"`. Handle collisions using `resolve_filename()` which appends `_2`, `_3`, etc.
4. Write the YAML frontmatter + body to the file.
5. Build an entity-ID-to-filepath mapping for memory placement.

For each memory:
1. Determine the parent entity: use `owner_id` if set, otherwise use `target_id`.
2. Look up the parent entity's file stem from the ID-to-filepath mapping.
3. Create or reuse the `.d/` companion directory (`{stem}.d/`).
4. Call `memory_to_frontmatter_dict(memory)` to get `(frontmatter_dict, content_body)`.
5. Generate filename via `sanitize_filename(memory.id) + ".md"`.
6. Write the YAML frontmatter + content body to the file.

For each scene with chat messages:
1. Create or reuse the scene's `.d/` companion directory.
2. Write `chatlog.log` with formatted chat lines.

**Step 6 -- Write status.json**

Create a `BackupStatus` (from `migration/models.py`) with:
- `timestamp`: current time in ISO 8601 format
- `success`: True (set to False on errors)
- `entity_counts`: dict counting entities by type name (e.g., `{"Character": 2, "Location": 3}`)
- `memory_count`: total memories written
- `chatlog_count`: number of scenes with chat logs written
- `errors`: list of any error messages encountered during writing
- `sidestage_version`: read from package metadata or hardcoded

Write as `status.json` in the temp directory root.

**Step 7 -- Atomic swap**

Perform an atomic-ish directory swap to minimize the window where `markdown/` is in an inconsistent state:

1. Let `markdown_dir = campaign.campaign_dir / "markdown"`.
2. Let `tmp_dir = campaign.campaign_dir / "markdown" / ".tmp_backup"` (the just-built tree). Actually, the tmp_dir should be a sibling, not inside markdown/. Use `campaign.campaign_dir / ".tmp_backup"` instead.
3. If `markdown_dir` exists, rename it to `campaign.campaign_dir / ".old_backup"`.
4. Rename `tmp_dir` to `markdown_dir`.
5. Delete `.old_backup` recursively.

If any step fails after step 3, attempt to restore: rename `.old_backup` back to `markdown_dir`.

**Step 8 -- Return result**

Return a `MigrationBackupResult` with:
- `phase`: `"complete"` on success, `"failed"` on error
- `total_entities`, `total_memories`: counts from the query
- `written_entities`, `written_memories`, `written_chatlogs`: counts of files actually written
- `errors`: any error messages

### Internal helper functions

The module should define several helpers to keep `export_campaign()` readable:

```python
async def _query_all_memories(client: GraphClient) -> list[Memory]:
    """Query all Memory nodes from FalkorDB."""
    ...

async def _enrich_entity_relationships(client: GraphClient, entity: Entity) -> Entity:
    """Populate relationship-derived fields (location_id, connected_locations) on entity."""
    ...

def _format_chatlog(messages: list[ChatMessage]) -> str:
    """Format chat messages into chatlog.log content."""
    ...

def _write_entity_file(base_dir: Path, entity: Entity, used_filenames: dict[str, set[str]]) -> tuple[str, Path]:
    """Write a single entity markdown file, returning (entity_id, file_path)."""
    ...

def _write_memory_file(entity_dir_map: dict[str, Path], memory: Memory) -> bool:
    """Write a single memory markdown file into the appropriate .d/ directory."""
    ...

def _write_chatlog_file(entity_dir_map: dict[str, Path], scene_id: str, messages: list[ChatMessage]) -> bool:
    """Write chatlog.log into the scene's .d/ directory."""
    ...

def _atomic_swap(tmp_dir: Path, target_dir: Path) -> None:
    """Atomically swap tmp_dir into target_dir position, preserving old as fallback."""
    ...
```

### YAML serialization for frontmatter

When writing files, use `yaml.dump()` with `sort_keys=False` to preserve the deterministic field ordering from `entity_to_frontmatter_dict()`. The file format is:

```
---
name: Eldric the Bold
id: char_eldric
type: Character
inventory:
- item_flame_tongue
location_id: loc_tavern
unseen: false
---

A brave warrior who frequents the Rusty Tavern...
```

### Memory placement logic

Memory placement follows these rules:
- If `memory.owner_id` is set and maps to a known entity, place in the owner's `.d/` directory
- If `memory.owner_id` is None (or maps to an unknown entity), place in the target entity's `.d/` directory (using `memory.target_id`)
- If neither owner nor target maps to a known entity, log a warning and skip the memory (add to errors list)

### Filename collision handling

The `used_filenames` dict tracks filenames per subdirectory. When `sanitize_filename()` produces a name already in use, call `resolve_filename()` which appends `_2`, then `_3`, etc., until a unique name is found. This is provided by `migration/serialization.py` (section-02).

### Error handling

The exporter should be fault-tolerant for individual entity/memory write failures:
- Wrap each entity write in try/except, log the error, continue
- Wrap each memory write in try/except, log the error, continue
- Accumulate errors in a list
- Still write status.json even if some writes failed (status.json reflects partial success)
- The atomic swap only executes if at least some entities were written successfully
- If the swap itself fails, preserve the old directory and report the error

### Imports needed

```python
from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from sidestage.graph.entities import list_entities
from sidestage.graph.relationships import get_related
from sidestage.memory.models import Memory
from sidestage.migration.models import BackupStatus, MigrationBackupResult
from sidestage.migration.serialization import (
    entity_to_frontmatter_dict,
    entity_type_to_subdir,
    memory_to_frontmatter_dict,
    resolve_filename,
    sanitize_filename,
)
from sidestage.schemas import Character, ChatMessage, Entity, Location, Scene

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.graph.client import GraphClient
```

### Relationship to existing code

- **`campaign.export_entities()`** in `campaign.py`: The old export function writes flat entity files to `campaign_dir/entities/`. The new exporter writes a structured `markdown/` tree. The old function remains for backward compatibility.
- **`entity_to_markdown()` in `entities.py`**: The old serialization function. The new exporter uses `entity_to_frontmatter_dict()` from `migration/serialization.py` instead, which produces the canonical frontmatter format.
- **`list_entities()` from `graph/entities.py`**: Reused directly to query all entities.
- **`get_related()` from `graph/relationships.py`**: Reused to query LOCATED_IN, CONNECTS_TO, AT_LOCATION relationships. Note: `get_related` validates rel_type against `VALID_REL_TYPES` which includes all needed types.
- **`campaign.storage.get_scene()`**: Returns a Scene with `messages` populated from SQLite. The graph-stored Scene excludes messages (per EXCLUDED_FIELDS).

### Edge cases to handle

1. **Empty campaign**: No entities, no memories. Should produce the directory structure with empty subdirectories and a status.json showing zero counts.
2. **Scenes without chat logs**: No `.d/` directory created unless the scene also has memories.
3. **Memories referencing deleted entities**: Log a warning, skip the memory file, add to errors.
4. **Very long entity names**: `sanitize_filename()` handles truncation (from section-02).
5. **No graph client**: If `campaign.graph_client` is None, return a failed result immediately with an appropriate error message.
6. **First backup (no existing `markdown/` dir)**: Skip the rename-old step in atomic swap, just rename tmp to markdown.