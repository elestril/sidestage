# Synthesized Spec: Campaign Migration and Backup

## Overview

Implement campaign import (markdown -> FalkorDB) and backup (FalkorDB -> markdown) commands as API endpoints with temporary UI buttons. FalkorDB is the primary source of truth; a `markdown/` directory tree serves as a portable backup/exchange format containing entities, memories, and chat logs. No real-time bidirectional sync is needed.

## Key Decisions (from Interview + Revisions)

1. **FalkorDB-primary**: The graph database is the sole runtime source of truth. The existing dual-path logic in WorldTools already supports this.
2. **No real-time file watching**: No watchfiles/watchdog needed. Import and backup are explicit, user-triggered operations.
3. **Entities AND Memories**: Both `:Entity` and `:Memory` graph nodes are included in import/export.
4. **Chat logs exported**: Scene chat logs are saved alongside scene markdown files as `.log` files.
5. **Import = full replacement**: Drop the entire FalkorDB graph and reimport from markdown. No merge/upsert logic needed (versioning/merging deferred to later).
6. **Hierarchical directory structure**: `markdown/` directory with subdirectories per entity type, `.d/` companion directories for memories and chat logs.
7. **Relationships from frontmatter**: Infer graph relationships from YAML fields (location_id, connected_locations, inventory, etc.) with referential integrity validation.
8. **New unified implementation**: Don't extend existing import_entities/export_entities. Build fresh, purpose-built import/export with validation, progress tracking, and error reporting.
9. **API endpoints + UI buttons**: Expose as FastAPI endpoints. Add temporary UI buttons in the web frontend.
10. **Validate-then-ask**: On import, run validation first, report all issues (broken references, missing fields, parse errors), then let user decide to proceed or abort.
11. **Status tracking**: `markdown/status.json` records export metadata (timestamp, success state) for future consistency checking.

## Directory Structure

```
~/.sidestage/<campaign_name>/markdown/
├── status.json                              # Export metadata
├── characters/
│   ├── JohnDoe.md                           # Character entity
│   ├── JohnDoe.d/
│   │   ├── TavernBrawlMemory.md             # Memory about JohnDoe
│   │   └── MeetingTheKingMemory.md          # Another memory
│   ├── Alice.md
│   └── Alice.d/
│       └── ...
├── locations/
│   ├── Tavern.md
│   ├── Tavern.d/
│   │   └── ...                              # Memories about the Tavern
│   └── Castle.md
├── items/
│   ├── MagicSword.md
│   └── ...
├── scenes/
│   ├── TavernBrawl.md                       # Scene entity
│   ├── TavernBrawl.d/
│   │   ├── chatlog.log                      # Chat log for this scene
│   │   └── BrawlStartedMemory.md            # Memories about this scene
│   └── ...
└── events/
    └── ...                                  # Event entities
```

**Naming conventions:**
- Entity files: `{entity_name}.md` (derived from entity `name` field, sanitized for filesystem)
- Memory files: `{memory_content_summary}.md` inside the parent entity's `.d/` directory
- Chat logs: `chatlog.log` inside the scene's `.d/` directory
- Subdirectory names: lowercase plural of entity type (`characters/`, `locations/`, `items/`, `scenes/`, `events/`)

## Scope

### In Scope

1. **Import Campaign API** (`POST /v1/campaign/import`)
   - Read all `.md` files from campaign `markdown/` directory tree
   - Parse entities from type subdirectories
   - Parse memories from `.d/` companion directories
   - Parse chat logs from scene `.d/` directories
   - Validate referential integrity
   - If user confirms: drop existing FalkorDB graph entirely, recreate schema/indexes, insert all entities + memories as graph nodes, create relationships
   - Progress tracking

2. **Backup Campaign API** (`POST /v1/campaign/backup`)
   - Read all Entity and Memory nodes from FalkorDB graph
   - Read chat logs from SQLite (scene messages)
   - Write hierarchical directory structure under `markdown/`
   - Write `status.json` with export metadata
   - Atomic write pattern (temp directory, then swap)
   - Progress tracking

3. **Validation Engine**
   - Parse validation: YAML syntax, required fields, type coercion
   - Referential integrity: entity references resolve, memory owner/target IDs resolve
   - Type checking: entity type matches expected schema
   - Report format: structured list of warnings and errors

4. **UI Integration**
   - Temporary "Import Campaign" and "Backup Campaign" buttons in the web frontend
   - Show progress and validation results
   - Confirmation dialog before destructive import

5. **Relationship Reconstruction**
   - Character.location_id -> LOCATED_IN relationship
   - Location.connected_locations -> CONNECTS_TO relationships (deduplicated)
   - Scene.location_id -> AT_LOCATION relationship
   - Scene events -> HAS_EVENT relationships
   - Memory.owner_id -> HAS_MEMORY relationship
   - Memory.target_id -> ABOUT relationship

6. **Status Tracking**
   - `markdown/status.json` with: timestamp, success/failure, entity counts, memory counts, errors

### Out of Scope

- Real-time bidirectional sync (no file watcher)
- Conflict resolution / merge logic
- Incremental/differential import
- CLI subcommands (API-only for now)
- Access control / authentication on endpoints

## Existing Architecture Context

### Entity Storage (Current)
- Markdown files in `~/.sidestage/<campaign>/entities/` with YAML frontmatter (old format)
- `entity_to_markdown()` and `markdown_to_entity()` in `entities.py`
- Pydantic models in `schemas.py`: Character, Location, Item, Scene, Event, ChatMessage
- Import/export functions in `campaign.py` (will NOT be reused; new implementation)

### Memory System (Already Built)
- Memory models: `memory/models.py` - Memory with id, content, memory_type, visibility, embedding, owner_id, target_id
- Memory CRUD: `memory/store.py` - upsert_memory, get_memories_for_context, search_similar
- Memory labels: `:Memory:SceneMemory`, `:Memory:CharacterMemory`, `:Memory:WorldFact`
- Memory relationships: `HAS_MEMORY` (owner -> memory), `ABOUT` (memory -> target)

### FalkorDB Integration (Already Built)
- Client: `graph/client.py` - `GraphConfig`, `connect()`, `close()`
- Schema: `graph/schema.py` - versioned schema with indexes and constraints
- Entity CRUD: `graph/entities.py` - `create_entity()`, `get_entity()`, `update_entity()`, `delete_entity()`, `list_entities()`
- Relationships: `graph/relationships.py` - `link()`, `unlink()`, `get_related()`, `get_relationships()`
- Valid relationship types: LOCATED_IN, CONNECTS_TO, AT_LOCATION, HAS_EVENT, INVOLVES, PARTICIPATES_IN

### Chat Log Storage
- Chat messages stored in SQLite via `storage.py` (as part of Scene.messages JSON)
- Messages are ChatMessage objects with character_id, message, gametime, walltime

### WebSocket / Event Infrastructure
- `SyncManager` in `sync.py` broadcasts `entities_updated` messages

### Web Frontend
- Vanilla JS SPA served from FastAPI static files
- No build steps, no frameworks

## Success Criteria

1. Import reads all markdown entities AND memories, creates corresponding FalkorDB nodes + relationships
2. Backup exports all FalkorDB entities AND memories to valid markdown files
3. Backup exports scene chat logs as `.log` files
4. Round-trip fidelity: import -> backup -> import produces identical graph state
5. Validation catches broken references, parse errors, and type mismatches before import
6. Connected WebSocket clients are notified of changes after import/backup
7. UI provides import/backup buttons with progress feedback
8. `status.json` is written on every backup with accurate metadata
9. Import of 1000 entities + memories completes in reasonable time (<10 seconds)
10. No data corruption when import/backup is interrupted (atomic write pattern)

## Dependencies

- Split 01 (FalkorDB Foundation): Entity CRUD, schema, relationships - **already built**
- Split 02 (Memory & Embedding): Memory system - **already built** and now included in this split's scope
