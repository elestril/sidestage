# Complete Specification: FalkorDB Foundation

## Overview

Establish FalkorDB as the graph database backend for Sidestage, replacing SQLite for entity storage. This provides the foundational graph API that the Memory System (split 02) and Migration/Sync (split 03) will build upon.

## Architecture Decisions

### Connection Management
- **Configurable per campaign:** Support both shared instance with graph-per-campaign namespacing (`select_graph('campaign_name')`) and separate FalkorDB instances
- Campaign config determines connection strategy
- Use `falkordb.asyncio` with `redis.asyncio.BlockingConnectionPool` for async operations

### Storage Strategy
- **FalkorDB replaces SQLite for all entity data** (characters, locations, items, scenes, events)
- SQLite retained only for chat logs and campaign configuration
- FalkorDB is the single source of truth for entities and their relationships

### Entity-to-Node Modeling (Multi-Label)
Nodes use multi-label approach for flexible querying at different abstraction levels:

| Entity Type | Labels | Properties |
|---|---|---|
| Character | `:Entity:Character` | id, name, body, unseen, location_id |
| Location | `:Entity:Location` | id, name, body |
| Item | `:Entity:Item` | id, name, body |
| Scene | `:Entity:Scene` | id, name, body, current_gametime, location_id |
| Event | `:Entity:Event` | id, name, body, scene_id, gametime, walltime |
| ChatMessage | `:Entity:Event:ChatMessage` | id, name, body, character_id, actor_id, message |

### Relationship Types

| Relationship | Direction | Notes |
|---|---|---|
| `LOCATED_IN` | Character → Location | Character's current location |
| `CONNECTS_TO` | Location → Location | Replaces `connected_locations` array. Bidirectional semantics. |
| `HAS_ITEM` | Character → Item | Inventory as edges (future consideration) |
| `AT_LOCATION` | Scene → Location | Scene's setting |
| `HAS_EVENT` | Scene → Event | Events within a scene |
| `INVOLVES` | Event → Character | Characters involved in events |
| `PARTICIPATES_IN` | Character → Scene | Characters present in scene |

**Note:** `inventory` on Character remains as an array property for now (simpler). `connected_locations` on Location becomes `CONNECTS_TO` edges (natural graph relationship).

### Consistency Model
- **Best effort with logging** for multi-step operations
- Combine multi-step operations into single Cypher queries where possible (e.g., character relocation)
- Log failures for operations that cannot be atomic
- Accept eventual consistency for non-critical relationship updates

### API Design
- **Graph-native API** - New async interface with graph operations (traverse, query_related, etc.)
- Not a mirror of the current Storage class
- Consumers (Campaign, SceneLogic, WorldTools) will be updated to use the new API
- Richer querying capabilities (relationship traversal, filtered queries)

### Error Handling
- **Fail fast with clear errors** - Operations raise immediately when FalkorDB is unreachable
- Campaign cannot function without graph DB
- Clear, descriptive error messages for connection failures, query errors, constraint violations

### Event Bus Integration
- **Explicit calls from Campaign** - Campaign/SceneLogic calls graph storage directly
- No automatic bus listener in this foundation split
- Simpler, more predictable, follows current patterns
- Bus integration may be added in future splits

### Schema Initialization
- **Auto-initialize with version checking**
- On connection, check schema version and create/update indexes and constraints as needed
- Track schema version to support future migrations
- Idempotent initialization (safe to run on every startup)

## Expected Scale
- **Large campaigns:** Thousands of entities and events
- Indexing strategy must support this scale
- Required indexes: entity id (unique), name (search), type-specific fields (gametime for events)

## Graph Schema

### Indexes
```cypher
CREATE INDEX FOR (e:Entity) ON (e.id)      -- Unique lookup
CREATE INDEX FOR (e:Entity) ON (e.name)     -- Name search
CREATE INDEX FOR (ev:Event) ON (ev.gametime) -- Temporal ordering
CREATE INDEX FOR (s:Scene) ON (s.current_gametime)
```

### Constraints
```cypher
GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE Entity PROPERTIES 1 id
GRAPH.CONSTRAINT CREATE <graph> MANDATORY NODE Entity PROPERTIES 2 id name
```

## Module Structure

New module: `src/sidestage/graph/`
```
graph/
├── __init__.py           # Public API exports
├── client.py             # FalkorDB connection management, pooling
├── schema.py             # Schema initialization, versioning, migrations
├── entities.py           # Entity CRUD operations (graph-native)
├── relationships.py      # Relationship operations
├── queries.py            # Graph traversal and query helpers
└── errors.py             # Custom exception types
```

## Integration Points

### Upstream Dependencies
- None (foundation layer)
- Requires running FalkorDB server (Redis-compatible)

### Downstream Consumers
- `Campaign` - Entity lifecycle management
- `SceneLogic` - Scene entity operations, event persistence
- `WorldTools` - Entity queries for agent tool calls
- Split 02 (Memory & Embedding) - Entity node access
- Split 03 (Migration & Sync) - Full CRUD + entity listing

### Existing System Changes
- `storage.py` - Remove entity storage methods (keep chat log/config)
- `campaign.py` - Update to use graph module instead of Storage for entities
- `schemas.py` - Entity models remain as Pydantic schemas (serialization layer)

## Testing Strategy
- Unit tests for connection management (mock FalkorDB)
- Unit tests for entity CRUD operations
- Unit tests for relationship operations
- Unit tests for schema initialization and versioning
- Integration tests with real FalkorDB instance (test containers or local)
- Test framework: pytest with pytest-anyio for async
- Mocking: AsyncMock for FalkorDB client

## Success Criteria
1. FalkorDB connection established and configurable per campaign
2. All entity types can be created, read, updated, deleted via graph operations
3. Relationships can be created/deleted between entities
4. Graph traversal queries work (get related entities, path queries)
5. Schema auto-initializes with version tracking
6. Fail-fast error handling with clear messages
7. Tests provide >80% code coverage
8. No breaking changes to existing Actor system integration

## Out of Scope
- Embedding/vector properties (split 02)
- Memory node creation or querying (split 02)
- Data migration from markdown/SQLite (split 03)
- Bidirectional sync with markdown (split 03)
- Event bus auto-sync listener
- Full-text search
- Performance optimization beyond basic indexing
