# Implementation Plan: Campaign Import & Backup

## 1. Context and Goals

Sidestage is an AI Co-Author platform for tabletop RPGs. It stores game entities (Characters, Locations, Items, Scenes, Events) and Memory nodes in FalkorDB, with chat logs in SQLite. The existing codebase already has full FalkorDB CRUD (`graph/entities.py`, `graph/relationships.py`), memory operations (`memory/store.py`), and markdown serialization (`entities.py`).

This plan implements two explicit, user-triggered operations:
- **Import Campaign**: Read a `markdown/` directory tree from disk, validate it, drop the existing FalkorDB graph, and recreate it from the files.
- **Backup Campaign**: Read all entities and memories from FalkorDB (plus chat logs from SQLite) and write them to a structured `markdown/` directory tree.

FalkorDB is the runtime source of truth. The `markdown/` directory is a portable backup/exchange format. There is no real-time bidirectional sync — import and backup are explicit commands.

### What This Does NOT Include
- Real-time file watching or bidirectional sync
- Merge/upsert logic (import is always a full replacement)
- CLI subcommands (API endpoints only)
- Access control or authentication

## 2. Canonical Data Representation

### The Problem

Currently, entity data has multiple representations that can drift:
- **Pydantic models** (`schemas.py`): `Character`, `Location`, etc. — the in-memory representation
- **JSON (API)**: `model_dump()` + `type` field — used by frontend via `/v1/entities` and `/v1/entities/{id}`
- **YAML frontmatter + markdown body** (`entities.py`): `entity_to_markdown()` / `markdown_to_entity()` — used for disk storage
- **FalkorDB node properties** (`graph/entities.py`): subset of fields, some excluded (`messages`, `widget`, `connected_locations`)

The frontend TypeScript types (`types.ts`) and the Python Pydantic models should describe the same shape, but they can diverge silently.

### The Solution: Single Canonical Frontmatter Format

Define a canonical YAML frontmatter representation for both entities and memories. This is **the same data** the frontend receives as JSON — just serialized as YAML+markdown instead of JSON:

**Entity canonical fields** (in frontmatter):
- All fields from the Pydantic model's `model_dump()` output
- Plus a `type` discriminator field (e.g., `type: Character`)
- The `body` field is the markdown body (below the frontmatter), not in the YAML

**Memory canonical fields** (in frontmatter):
- All fields from `Memory.model_dump()`, excluding `embedding` (regenerated, not stored on disk)
- The `content` field is the markdown body (below the frontmatter), not in the YAML

### Unifying Serialization

Introduce a shared serialization layer in the new `migration/` module that both the API and disk I/O use:

```python
def entity_to_frontmatter_dict(entity: Entity) -> tuple[dict, str]:
    """Convert entity to (frontmatter_dict, body_markdown).

    The frontmatter_dict is the canonical representation — identical
    to what the API returns via model_dump() + type field.
    """

def frontmatter_dict_to_entity(data: dict, body: str) -> Entity:
    """Reconstruct entity from frontmatter dict + body.

    Inverse of entity_to_frontmatter_dict. Also used by the API
    endpoint that accepts JSON updates.
    """

def memory_to_frontmatter_dict(memory: Memory) -> tuple[dict, str]:
    """Convert memory to (frontmatter_dict, body_content).

    Excludes embedding field. Content becomes the markdown body.
    """

def frontmatter_dict_to_memory(data: dict, body: str) -> Memory:
    """Reconstruct memory from frontmatter dict + body."""
```

**Key constraint:** The frontmatter dict for an entity MUST be identical to what `model_dump()` produces (plus `type`), minus the `body` field. This means:
- `GET /v1/entities` returns `[entity_to_frontmatter_dict(e)[0] | {"body": e.body}]` (or equivalently, `model_dump() + type`)
- `POST /v1/entities/{id}` accepts the same dict shape
- Disk files use YAML serialization of the same dict, with `body` as the markdown section

This ensures **one canonical shape** for entity data, used everywhere: frontend JSON, disk YAML, and API.

### Existing Code Changes

The existing `entity_to_markdown()` and `markdown_to_entity()` in `entities.py` already approximate this pattern. The new unified functions should:
1. Replace usage of the old functions in the new migration module
2. Ensure field ordering is deterministic (name, id, type first, then alphabetical)
3. Handle all entity subtypes (ChatMessage, JoinEvent, etc.) and Memory models
4. The old functions remain for backward compatibility but the new migration module uses the new unified functions

The frontend TypeScript `Entity` interface in `types.ts` should be kept in sync — when a field is added to the Pydantic model, it should be added to the TS interface too. This is an ongoing maintenance discipline, not something automated in this plan.

## 3. Directory Structure

The backup/import format uses a hierarchical directory tree under `~/.sidestage/<campaign_name>/markdown/`:

```
markdown/
├── status.json                              # Export metadata
├── characters/
│   ├── JohnDoe.md                           # Character entity
│   ├── JohnDoe.d/
│   │   ├── TavernBrawlMemory.md             # Memory about JohnDoe
│   │   └── MeetingTheKingMemory.md
│   ├── Alice.md
│   └── Alice.d/
│       └── ...
├── locations/
│   ├── Tavern.md
│   ├── Tavern.d/
│   │   └── HauntedHistoryFact.md            # Memory about the Tavern
│   └── Castle.md
├── items/
│   ├── MagicSword.md
│   └── ...
├── scenes/
│   ├── TavernBrawl.md                       # Scene entity
│   ├── TavernBrawl.d/
│   │   ├── chatlog.log                      # Chat log for this scene
│   │   └── BrawlStartedMemory.md            # Memory about this scene
│   └── ...
└── events/
    └── ...
```

### Naming Conventions

- **Entity files**: `{sanitized_name}.md` — derived from entity `name` field, sanitized for filesystem (non-alphanumeric except `-`/`_` replaced with `_`, collapse multiples)
- **Type subdirectories**: lowercase plural: `characters/`, `locations/`, `items/`, `scenes/`, `events/`
- **Companion directories**: `{sanitized_name}.d/` — same stem as entity file, `.d` suffix. Created only when entity has memories or chat logs.
- **Memory files**: `{sanitized_memory_id}.md` inside parent entity's `.d/` directory
- **Chat logs**: `chatlog.log` inside scene's `.d/` directory

### Entity-to-Directory Mapping

| Entity Type | Subdirectory |
|---|---|
| Character | `characters/` |
| Location | `locations/` |
| Item | `items/` |
| Scene | `scenes/` |
| Event, ChatMessage, JoinEvent, LeaveEvent | `events/` |

### status.json

```python
class BackupStatus(BaseModel):
    timestamp: str              # ISO 8601
    success: bool
    entity_counts: dict[str, int]   # {"Character": 5, "Location": 3, ...}
    memory_count: int
    chatlog_count: int
    errors: list[str]
    sidestage_version: str
```

## 4. Architecture Overview

### New Module: `src/sidestage/migration/`

```
src/sidestage/migration/
├── __init__.py
├── serialization.py  # Canonical frontmatter serialization (shared by API + disk)
├── parser.py         # Parse markdown directory tree -> models
├── validator.py      # Referential integrity and schema validation
├── importer.py       # Import orchestration
├── exporter.py       # Backup orchestration
└── models.py         # Validation reports, progress, status models
```

The existing `import_entities()`/`export_entities()` in `campaign.py` and the old `/v1/entities/import`, `/v1/entities/export` routes are deprecated but left in place.

### Integration Points

- **FastAPI endpoints** in `orchestrator.py`: `POST /v1/campaign/import`, `POST /v1/campaign/backup`
- **Serialization layer**: `migration/serialization.py` provides canonical frontmatter functions used by both exporter AND API entity get/set endpoints (eventually)
- **Web frontend**: Two buttons for import/backup
- **WebSocket**: Broadcast `entities_updated` after operations
- **FalkorDB**: `graph/` module for entity + relationship CRUD
- **Memory**: `memory/store.py` for memory CRUD
- **SQLite**: `storage.py` for chat log retrieval/restoration
- **Concurrency guard**: During import, set `campaign.health` to `DEGRADED` with reason `"Importing campaign data"`. Other graph endpoints check `campaign.health.is_accepting_chat` — DEGRADED still allows reads but signals reduced functionality. Embedding generation is blocked (`is_embedding_available` returns `False` when not HEALTHY).

## 5. Data Models (models.py)

All API-facing models use Pydantic `BaseModel`, prefixed with `Migration`.

### Validation

```python
class MigrationValidationIssue(BaseModel):
    entity_id: str | None
    file_path: str
    severity: str          # "error" or "warning"
    message: str

class MigrationValidationReport(BaseModel):
    valid: bool
    entities_found: int
    memories_found: int
    entity_counts: dict[str, int]
    errors: list[MigrationValidationIssue]
    warnings: list[MigrationValidationIssue]
```

### Results

```python
class MigrationImportResult(BaseModel):
    phase: str             # "complete" or "failed"
    total_entities: int
    total_memories: int
    processed_entities: int
    processed_memories: int
    errors: list[str]

class MigrationBackupResult(BaseModel):
    phase: str             # "complete" or "failed"
    total_entities: int
    total_memories: int
    written_entities: int
    written_memories: int
    written_chatlogs: int
    errors: list[str]
```

### API Models

```python
class MigrationImportRequest(BaseModel):
    action: str = "validate"
    force: bool = False

class MigrationImportResponse(BaseModel):
    action: str
    validation: MigrationValidationReport | None = None
    result: MigrationImportResult | None = None
```

## 6. Import Campaign

### 6.1 API Endpoint

`POST /v1/campaign/import` with two phases:

**Phase 1 — Validate:** `{"action": "validate"}`
**Phase 2 — Execute:** `{"action": "execute", "force": false|true}`

### 6.2 Parsing (parser.py)

Reads the entire `markdown/` directory tree.

**Process:**
1. Iterate type subdirectories (`characters/`, `locations/`, `items/`, `scenes/`, `events/`)
2. For each `.md` file in a type subdirectory: parse via `frontmatter_dict_to_entity()` using the canonical serialization
3. For each `.d/` companion directory: parse `.md` files as memories via `frontmatter_dict_to_memory()`, parse `chatlog.log` if present
4. Associate memories with parent entity via `.d/` naming
5. If `type` field missing in frontmatter: infer from subdirectory name, log warning

**Output:** `ParseResult` with entities, memories, chatlogs, errors.

**Memory frontmatter format:**
```markdown
---
id: "mem_abc123"
memory_type: "scene"
visibility: "common"
owner_id: "char_john"
target_id: "scene_tavern_brawl"
gametime: 3600
created_at: 1706000000.0
updated_at: 1706000000.0
access_count: 0
---

John witnessed a fierce brawl break out in the tavern...
```

**Chat log format (`chatlog.log`):**
```
[2026-01-15T14:30:00Z] (char_john) John: "I challenge you to a duel!"
[2026-01-15T14:30:05Z] (char_alice) Alice: "You'll regret that."
```

**Edge cases:**
- `.d/` without parent `.md`: warning (orphaned memories)
- `chatlog.log` in non-scene `.d/`: warning (ignored)
- `Scene.messages` in frontmatter: ignored (messages come from chatlog.log)
- Duplicate entity IDs: warning, last-wins

### 6.3 Validation (validator.py)

**Entity checks:** ID uniqueness, Character.location_id references, Character.inventory references, Location.connected_locations references, Scene.location_id references, Event.scene_id references, required fields (id, name).

**Memory checks:** owner_id references existing entity (or null), target_id references existing entity, valid memory_type, required fields (id, content, memory_type, target_id).

**General:** Always include data-loss warning.

### 6.4 Graph Import (importer.py)

**Concurrency guard:** Set `campaign.health` to `DEGRADED` with reason `"Importing campaign data"`. The existing `CampaignHealth` class (in `health.py`) already provides `is_accepting_chat` (True when DEGRADED — allows reads) and `is_embedding_available` (False when DEGRADED — blocks embedding generation during import). No new flags or states needed.

**Process:**
1. Set `await campaign.health.set_status(HealthStatus.DEGRADED, "Importing campaign data")`
2. Drop graph via `await graph.delete()`, re-select via `db.select_graph(graph_name)`
3. Recreate schema via `initialize_schema()` (pass `vector_dimension` from embedding config or `None`)
4. Insert entities via `create_entity()` for each
5. Create relationships: `LOCATED_IN`, `CONNECTS_TO` (deduplicated), `AT_LOCATION`, `HAS_EVENT`
6. Insert memories via `upsert_memory()`, create `HAS_MEMORY` + `ABOUT` relationships. Skip embedding generation.
7. Restore chat logs via `storage.update_scene()`
8. Verify counts
9. Restore health: `await campaign.health.set_status(HealthStatus.HEALTHY, "")`, clear active scenes, broadcast `entities_updated`

## 7. Backup Campaign

### 7.1 API Endpoint

`POST /v1/campaign/backup` — returns `MigrationBackupResult`.

### 7.2 Export Process (exporter.py)

**Process:**
1. Query all entities from FalkorDB
2. Query all memories from FalkorDB
3. Retrieve chat logs from SQLite for all scenes
4. Build directory tree in temp location (`markdown/.tmp_backup/`):
   - Entity files via `entity_to_frontmatter_dict()` -> YAML + markdown
   - Memory files in `.d/` dirs via `memory_to_frontmatter_dict()` -> YAML + markdown
   - Chat logs as `chatlog.log` in scene `.d/` dirs
5. Write `status.json`
6. Atomic swap: old `markdown/` -> `markdown/.old_backup/`, temp -> `markdown/`, delete `.old_backup/`
7. Broadcast `entities_updated`

**Serialization:** Uses the canonical `entity_to_frontmatter_dict()` and `memory_to_frontmatter_dict()` from `migration/serialization.py`.

**Relationship reconstruction for frontmatter:** Query `LOCATED_IN` for `location_id`, `CONNECTS_TO` for `connected_locations`, `AT_LOCATION` for scene location. Inventory is a node property, no query needed.

**Memory placement:** If `owner_id` set, place in owner's `.d/`. If null, place in target's `.d/`.

**Filename collisions:** Append `_2`, `_3` etc.

## 8. Web Frontend Integration

### 8.1 UI Buttons

"Import Campaign" and "Backup Campaign" buttons in campaign settings area.

### 8.2 Import Flow (UI)

Validate -> show results (counts, warnings, data-loss warning) -> confirm -> execute.

### 8.3 Backup Flow (UI)

Click -> show completion with counts.

## 9. FastAPI Route Integration

```python
@app.post("/v1/campaign/import")
async def import_campaign(request: MigrationImportRequest) -> MigrationImportResponse:
    """Import entities and memories from markdown directory into FalkorDB."""

@app.post("/v1/campaign/backup")
async def backup_campaign() -> MigrationBackupResult:
    """Backup all entities, memories, and chat logs to markdown directory."""
```

Check `campaign.health.status` — if DEGRADED (import in progress), return 409 Conflict for import/backup requests. Other read endpoints remain available (DEGRADED allows chat reads).

## 10. Error Recovery

### Import Failures
- Parse failure: reported in validation. User decides.
- Graph drop failure: restore health to HEALTHY, abort. Old graph intact.
- Partial insertion: restore health to HEALTHY, return error with counts. Retry is idempotent.

### Backup Failures
- Query/write failure: abort. Old files untouched (temp dir pattern).
- `status.json` written last. If backup fails, it reflects previous state.

### Concurrency
- Import/backup requests return 409 when `campaign.health.status == DEGRADED`. Embedding generation blocked (`is_embedding_available` returns False). Chat reads remain available. Active scenes cleared after import. Frontend refreshes via WebSocket.

## 11. Integration with Existing Code

### What We Reuse
- `graph/client.py`, `graph/schema.py` (`initialize_schema()`), `graph/entities.py` (`create_entity()`, `list_entities()`), `graph/relationships.py` (`link()`, `get_related()`)
- `memory/store.py` (`upsert_memory()`), `memory/models.py` (`Memory`)
- `schemas.py` (all Pydantic models)
- `entities.py` (`entity_to_markdown()` as reference — new canonical functions supersede it)
- `storage.py` (chat log retrieval/restoration)
- `sync.py` (`SyncManager.broadcast()`)

### What We Don't Touch
- `campaign.py`: old import/export deprecated, not removed
- `bus.py`, `tools.py`: not involved

### What We Add
- `migration/` module: serialization, parser, validator, importer, exporter, models
- API routes in `orchestrator.py`
- UI buttons in frontend
- Test campaign data in `data/test_campaign/`

## 12. Test Campaign and Testing Strategy

### Canonical Test Campaign (`data/test_campaign/markdown/`)

A representative test campaign checked into git, containing markdown files in the canonical directory structure. This serves as both documentation of the expected format and test fixtures.

```
data/test_campaign/markdown/
├── characters/
│   ├── Eldric_the_Bold.md
│   ├── Eldric_the_Bold.d/
│   │   ├── mem_tavern_brawl.md              # Scene memory (private)
│   │   └── mem_knows_alice.md               # Character memory
│   ├── Alice_the_Merchant.md
│   └── Alice_the_Merchant.d/
│       └── mem_trade_secret.md              # World fact
├── locations/
│   ├── The_Rusty_Tavern.md
│   ├── The_Rusty_Tavern.d/
│   │   └── mem_haunted_history.md           # World fact about location
│   ├── Castle_Blackmoor.md
│   └── Town_Square.md                       # Location with no memories
├── items/
│   ├── Flame_Tongue_Sword.md
│   └── Healing_Potion.md
├── scenes/
│   ├── Tavern_Brawl.md
│   ├── Tavern_Brawl.d/
│   │   ├── chatlog.log                      # Chat log with multiple speakers
│   │   └── mem_brawl_outcome.md             # Common scene memory
│   └── Castle_Audience.md                   # Scene with no chat/memories
└── events/
    └── Eldric_Joins_Brawl.md                # JoinEvent
```

**Coverage:**
- **Characters**: One with location_id + inventory, one without (optional fields)
- **Locations**: Three with connected_locations forming a triangle (CONNECTS_TO deduplication)
- **Items**: Two (one in inventory, one standalone)
- **Scenes**: One with chat log + memories, one bare
- **Events**: JoinEvent subtype
- **Memories**: All three types (scene, character, world_fact), private and common visibility, on different entity types
- **Relationships**: Characters at locations, items in inventory, connected locations, scene at location, event in scene

### Integration Tests (temp dirs only)

Integration tests copy `data/test_campaign/markdown/` to a `tmp_path` fixture. They never read/write `data/` directly during test execution.

```python
@pytest.fixture
def test_campaign_markdown(tmp_path: Path) -> Path:
    """Copy canonical test campaign to a temp directory for testing."""
    src = Path(__file__).parent.parent.parent / "data" / "test_campaign" / "markdown"
    dst = tmp_path / "markdown"
    shutil.copytree(src, dst)
    return dst
```

**Test cases:**

1. **Full roundtrip (import -> backup -> diff)**:
   - Copy test campaign to temp dir
   - Parse + validate (expect no errors)
   - Import into FalkorDB (requires FalkorDB fixture)
   - Query graph: verify entity counts, relationship counts, memory counts
   - Backup from FalkorDB to a second temp dir
   - Compare: every entity and memory from original appears in backup
   - Re-import the backup: verify identical graph state

2. **Entity fidelity (canonical format = API format)**:
   - Import test campaign
   - Call `list_entities()` via campaign API (returns JSON dicts)
   - For each entity: verify JSON dict matches the frontmatter dict from the original markdown file
   - This validates the canonical format is identical whether accessed via JSON API or disk

3. **Memory fidelity**:
   - Import, query all memories
   - Verify fields: owner_id, target_id, memory_type, visibility, gametime, content
   - Verify HAS_MEMORY and ABOUT relationships

4. **Chat log fidelity**:
   - Import, call `get_scene_messages()` for scenes with chat logs
   - Verify message count, character_ids, content, ordering

5. **Relationship integrity**:
   - Verify LOCATED_IN edges match Character.location_id
   - Verify CONNECTS_TO edges deduplicated
   - Verify AT_LOCATION for scenes

6. **Validation errors**:
   - Copy test files, introduce broken references
   - Verify validator catches with correct messages

7. **Concurrency guard**:
   - Start import, verify `campaign.health.status == DEGRADED` and reason is set
   - Verify import/backup requests return 409 during import
   - Verify health restored to HEALTHY after import completes (or fails)

### Unit Tests

- **Serialization roundtrip**: `entity_to_frontmatter_dict()` -> YAML -> parse -> `frontmatter_dict_to_entity()` for all entity types. Same for memories.
- **Parser**: Type subdirectory iteration, `.d/` companion parsing, chatlog parsing, malformed YAML, missing fields, type inference
- **Validator**: All check types in section 6.3
- **Filename sanitization**: Special chars, collisions
