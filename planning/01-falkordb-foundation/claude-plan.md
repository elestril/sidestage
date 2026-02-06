# Implementation Plan: FalkorDB Foundation

## 1. Project Context

Sidestage is a multi-agent RPG assistant built with Python 3.12+, FastAPI, and an async event-driven architecture. It currently stores entity data (characters, locations, items, scenes, events) in SQLite as JSON blobs via a `Storage` class in `storage.py`. This flat key-value approach has no relationship traversal, no semantic queries, and no graph capabilities.

This plan establishes FalkorDB as the graph database backend, replacing SQLite for entity storage while keeping SQLite for chat logs and campaign configuration. FalkorDB is a Redis-compatible graph database that supports Cypher queries, async Python operations via `falkordb.asyncio`, and multi-label nodes.

### Why FalkorDB?

- **Native graph relationships** enable queries like "which characters are in location X?" without linear scans
- **Multi-label nodes** map naturally to Sidestage's entity hierarchy (Entity → Character, Location, etc.)
- **Redis-compatible** protocol means minimal infrastructure overhead
- **Native async Python support** fits the existing async-focused codebase
- **Cypher query language** provides expressive graph traversals

### What This Plan Covers

- FalkorDB connection management with configurable per-campaign graphs
- Graph schema design with multi-label entity nodes and typed relationships
- Schema auto-initialization with version tracking
- Graph-native async API for entity CRUD and relationship operations
- Integration points with existing Campaign, SceneLogic, and WorldTools
- Error handling with fail-fast semantics

### What This Plan Does NOT Cover

- Vector embeddings or memory nodes (split 02)
- Data migration from markdown/SQLite (split 03)
- Event bus auto-sync listeners
- Full-text search

---

## 2. Module Structure

All FalkorDB code lives in a new `src/sidestage/graph/` package:

```
src/sidestage/graph/
├── __init__.py           # Public API re-exports
├── client.py             # Connection management, pooling, lifecycle
├── schema.py             # Schema initialization, versioning, index/constraint management
├── entities.py           # Entity CRUD: create, get, update, delete, list, query
├── relationships.py      # Relationship CRUD: link, unlink, get_related, traverse
├── queries.py            # Higher-level graph queries and traversals
└── errors.py             # Custom exception hierarchy
```

### Why This Structure?

- **Separation of concerns:** Connection management is distinct from query logic
- **Testability:** Each module can be tested independently with mocked dependencies
- **Extensibility:** Split 02 can add `memory.py` without touching existing modules
- **Discoverability:** A developer looking for "how to create an entity" goes to `entities.py`

---

## 3. Connection Management (`client.py`)

### FalkorDB Client Wrapper

The client module provides a thin async wrapper around `falkordb.asyncio.FalkorDB` that handles connection pooling, graph selection, and lifecycle management.

```python
class GraphClient:
    """Async FalkorDB client with connection pooling and graph selection."""

    pool: BlockingConnectionPool
    db: FalkorDB
    graph: Graph  # The selected graph for this campaign
    graph_name: str
```

### Connection Configuration

Connection parameters come from the campaign's configuration. The client supports two deployment modes:

1. **Shared instance** (default): One FalkorDB server, each campaign gets its own named graph via `db.select_graph(campaign_name)`. Graph names are sanitized from campaign names.

2. **Dedicated instance**: Campaign config specifies a separate host/port for its FalkorDB.

Configuration fields:
- `host` (default: `localhost`)
- `port` (default: `6379`)
- `password` (optional)
- `max_connections` (default: `16`)
- `graph_name` (default: derived from campaign name)

### Lifecycle

The client follows an explicit open/close lifecycle:

```python
async def connect(config: GraphConfig) -> GraphClient:
    """Create connection pool, select graph, run schema init."""

async def close(client: GraphClient) -> None:
    """Drain pool and close all connections."""
```

On `connect`, after establishing the connection pool, the client calls schema initialization (see section 4) to ensure indexes and constraints are up to date.

### Connection Pool

Uses `redis.asyncio.BlockingConnectionPool` with:
- `max_connections=16` (configurable)
- `timeout=None` (block until connection available)
- `decode_responses=True` (auto-decode Redis responses)

The pool is shared across all graph operations for the campaign lifetime. It is created once on campaign start and closed on campaign shutdown.

---

## 4. Schema Design & Initialization (`schema.py`)

### Node Labels

Every entity node carries the `:Entity` base label plus its specific type label:

| Sidestage Type | Node Labels | Stored Properties |
|---|---|---|
| Character | `:Entity:Character` | id, name, body, unseen, location_id, inventory (array) |
| Location | `:Entity:Location` | id, name, body |
| Item | `:Entity:Item` | id, name, body |
| Scene | `:Entity:Scene` | id, name, body, current_gametime, location_id |
| Event | `:Entity:Event` | id, name, body, scene_id, gametime, walltime |
| ChatMessage | `:Entity:Event:ChatMessage` | id, name, body, character_id, actor_id, message |

The `:Entity` base label enables queries across all entity types (e.g., "find entity by id regardless of type"). Specific labels enable type-filtered queries.

**Property notes:**
- `inventory` on Character stays as an array property (list of item IDs). This is simpler for now and avoids complex edge management for a feature that may evolve in split 02.
- `connected_locations` on Location is NOT stored as a property. Instead, it becomes `CONNECTS_TO` edges (see section 5).
- `messages` on Scene is NOT stored in the graph. Chat messages stay in SQLite.

### Relationship Types

| Relationship | Source → Target | Purpose |
|---|---|---|
| `LOCATED_IN` | Character → Location | Character's current location |
| `CONNECTS_TO` | Location → Location | Passable connection between locations |
| `AT_LOCATION` | Scene → Location | Scene's setting |
| `HAS_EVENT` | Scene → Event | Events within a scene |
| `INVOLVES` | Event → Character | Characters referenced in events |
| `PARTICIPATES_IN` | Character → Scene | Characters present in a scene |

`CONNECTS_TO` is directional in the graph but semantically bidirectional - a query for "locations connected to X" should traverse both directions. The query layer handles this.

### Indexes

Created on schema initialization for query performance at scale (thousands of entities):

```python
INDEXES = [
    ("Entity", "id"),       # Unique entity lookup (most common query)
    ("Entity", "name"),     # Name-based search
    ("Event", "gametime"),  # Temporal ordering and range queries
    ("Scene", "current_gametime"),  # Scene time queries
]
```

### Constraints

```python
CONSTRAINTS = [
    ("Entity", "id", "unique"),      # No duplicate entity IDs
    ("Entity", "id", "mandatory"),   # All entities must have an ID
    ("Entity", "name", "mandatory"), # All entities must have a name
]
```

Note: Unique constraints require a range index on the same property. The initialization routine creates indexes before constraints.

### Schema Versioning

A special `:SchemaVersion` node stores the current schema version:

```python
class SchemaVersion:
    version: int
    updated_at: str  # ISO timestamp
```

On startup, the initialization routine:
1. Checks for a `:SchemaVersion` node
2. If absent, creates one at version 1 and runs full schema setup (indexes + constraints)
3. If present, compares stored version to expected version
4. If mismatch, runs migration steps for each version increment
5. Updates the version node after successful migration

Migration steps are defined as a registry mapping version numbers to migration functions. For v1, the only migration is "create all indexes and constraints from scratch."

The initialization is idempotent - creating an index that already exists is a no-op in FalkorDB.

---

## 5. Entity Operations (`entities.py`)

### Graph-Native API

The entity module provides a graph-native async API. This is NOT a mirror of the current `Storage` class - it provides richer capabilities suited to a graph database.

```python
async def create_entity(client: GraphClient, entity: Entity) -> Entity:
    """Create a node with appropriate labels and properties.

    Determines labels from entity type (Character → :Entity:Character).
    Serializes Pydantic model fields to node properties.
    If the entity type implies relationships (e.g., Character with location_id),
    those are created separately via the relationships module.
    """

async def get_entity(client: GraphClient, entity_id: str) -> Entity | None:
    """Retrieve entity by ID. Returns None if not found.

    Queries the :Entity label with id property.
    Reconstructs the appropriate Pydantic model based on node labels.
    """

async def update_entity(client: GraphClient, entity_id: str, updates: dict) -> Entity:
    """Update specific properties on an entity node.

    Uses Cypher SET for property updates.
    Does not touch relationships - use relationships module for that.
    """

async def delete_entity(client: GraphClient, entity_id: str) -> None:
    """Delete entity node and all its relationships.

    Uses DETACH DELETE to remove node and connected edges.
    """

async def list_entities(client: GraphClient, entity_type: str | None = None) -> list[Entity]:
    """List entities, optionally filtered by type.

    If entity_type is provided, queries the specific label (e.g., :Character).
    Otherwise queries all :Entity nodes.
    """

async def find_entities(client: GraphClient, **filters) -> list[Entity]:
    """Query entities by property filters.

    Supports equality filters on any indexed property.
    Example: find_entities(client, name="Alice", unseen=False)
    """
```

### Entity Serialization

Entities are Pydantic models in `schemas.py`. The graph module needs to:

1. **Serialize to graph:** Convert a Pydantic model to a dict of node properties, determining labels from the model's class (Character → `:Entity:Character`).
2. **Deserialize from graph:** Given a node's labels and properties, reconstruct the correct Pydantic model.

A label-to-model registry maps FalkorDB labels to Pydantic classes:

```python
LABEL_TO_MODEL = {
    "Character": Character,
    "Location": Location,
    "Item": Item,
    "Scene": Scene,
    "Event": Event,
    "ChatMessage": ChatMessage,
}
```

The most specific label (e.g., "ChatMessage" over "Event") determines which model to instantiate. Labels are checked in specificity order.

### Property Handling

Not all Pydantic fields map directly to graph properties:
- **Stored as properties:** Scalar fields (str, int, bool, Optional[str])
- **Stored as properties (arrays):** `inventory` on Character (list of strings)
- **NOT stored as properties:** `connected_locations` on Location (becomes edges), `messages` on Scene (stays in SQLite)
- **NOT stored:** Fields that are relationship-derived (e.g., `location_id` is stored as a property AND as a `LOCATED_IN` edge for query flexibility)

A field exclusion list per entity type defines which fields to skip during serialization.

---

## 6. Relationship Operations (`relationships.py`)

```python
async def link(client: GraphClient, source_id: str, rel_type: str, target_id: str,
               properties: dict | None = None) -> None:
    """Create a relationship between two entities.

    Matches source and target by :Entity id, creates typed edge.
    Optional properties dict for edge metadata.
    """

async def unlink(client: GraphClient, source_id: str, rel_type: str, target_id: str) -> None:
    """Remove a relationship between two entities."""

async def get_related(client: GraphClient, entity_id: str, rel_type: str,
                      direction: str = "outgoing") -> list[Entity]:
    """Get entities related via a specific relationship type.

    direction: "outgoing", "incoming", or "both"
    For CONNECTS_TO, always use "both" (semantically bidirectional).
    """

async def get_relationships(client: GraphClient, entity_id: str) -> list[dict]:
    """Get all relationships for an entity.

    Returns list of {rel_type, direction, target_id, target_name, properties}.
    Useful for entity detail views.
    """
```

### Relationship Lifecycle

When entities are created or updated, relationships may need to change:

- **Character creation with `location_id`:** After creating the Character node, create a `LOCATED_IN` edge to the specified Location node.
- **Character `location_id` update:** Delete old `LOCATED_IN` edge, create new one. Best effort - if either step fails, log the inconsistency.
- **Location deletion:** `DETACH DELETE` removes all edges (CONNECTS_TO, LOCATED_IN targets, etc.)
- **Scene creation with `location_id`:** Create `AT_LOCATION` edge.

These compound operations are coordinated at the API level (in `entities.py` or a higher-level orchestration function), not inside `relationships.py` which stays focused on single-edge operations.

---

## 7. Graph Queries (`queries.py`)

Higher-level queries that combine entity and relationship operations:

```python
async def characters_at_location(client: GraphClient, location_id: str) -> list[Character]:
    """All characters currently at a location (via LOCATED_IN)."""

async def connected_locations(client: GraphClient, location_id: str) -> list[Location]:
    """All locations connected to a given location (CONNECTS_TO, both directions)."""

async def scene_events(client: GraphClient, scene_id: str,
                       since_gametime: int | None = None) -> list[Event]:
    """Events in a scene, optionally filtered by gametime (for temporal queries)."""

async def entity_graph(client: GraphClient, entity_id: str, depth: int = 1) -> dict:
    """Get an entity and its neighborhood to a given depth.

    Returns the entity plus all directly (or transitively) related entities.
    Useful for building context for AI agents.
    """
```

These functions use single Cypher queries (not multiple round-trips) for efficiency. They return fully deserialized Pydantic models.

---

## 8. Error Handling (`errors.py`)

### Exception Hierarchy

```python
class GraphError(Exception):
    """Base exception for all graph operations."""

class ConnectionError(GraphError):
    """FalkorDB server unreachable or connection pool exhausted."""

class EntityNotFoundError(GraphError):
    """Entity with given ID does not exist."""

class DuplicateEntityError(GraphError):
    """Entity with given ID already exists (unique constraint violation)."""

class SchemaError(GraphError):
    """Schema initialization or migration failed."""

class QueryError(GraphError):
    """Cypher query execution failed."""
```

### Fail-Fast Policy

All operations raise immediately on error. There is no retry logic, no graceful degradation, no fallback to SQLite. If FalkorDB is down, the campaign cannot operate.

Connection errors surface clear messages: "FalkorDB unreachable at {host}:{port}" rather than raw Redis exceptions.

### Logging

All multi-step operations (e.g., character relocation = delete old edge + create new edge) log each step. If an intermediate step fails, the error is logged with enough context to understand the inconsistency, then re-raised.

---

## 9. Integration with Existing Code

### Campaign (`campaign.py`)

Campaign currently creates a `Storage` instance and delegates entity operations to it. The integration changes:

1. Campaign creates a `GraphClient` in addition to (or replacing parts of) `Storage`
2. Entity CRUD calls route to `graph.entities` instead of `storage`
3. Scene creation uses `graph.entities.create_entity` + `graph.relationships.link`
4. Campaign shutdown calls `graph.client.close`

The `Storage` class retains responsibility for chat logs and campaign configuration. Entity-related methods on Storage become deprecated/removed.

### SceneLogic (`scene.py`)

SceneLogic currently stores messages in-memory and persists via the bus insert hook. Changes:

1. Scene entity creation/updates use graph module
2. Event persistence uses `graph.entities.create_entity` for Event nodes
3. Character participation tracking uses `graph.relationships.link` for `PARTICIPATES_IN` edges

### WorldTools (`tools.py`)

WorldTools provides entity query functions for AI agents. Changes:

1. Entity lookup queries use `graph.entities.get_entity` / `graph.entities.find_entities`
2. Location queries use `graph.queries.characters_at_location`
3. Richer context via `graph.queries.entity_graph`

### Configuration

New FalkorDB configuration section in campaign config:

```python
class GraphConfig:
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None  # Default: derived from campaign name
```

Added to the campaign's configuration schema. If `graph_name` is not specified, it's derived by sanitizing the campaign name (lowercase, replace spaces with underscores, strip special characters).

---

## 10. Dependencies

### New Dependencies

Add to `pyproject.toml`:
- `falkordb>=1.4.0` - FalkorDB Python client (includes async support)

The `falkordb` package depends on `redis[hiredis]` which provides `redis.asyncio.BlockingConnectionPool`. No additional Redis package is needed.

### FalkorDB Server

The FalkorDB server must be running separately. For local development:
- Docker: `docker run -p 6379:6379 falkordb/falkordb`
- The plan does not include Docker Compose or infrastructure setup; that's an operational concern

---

## 11. Implementation Order

The recommended implementation sequence, where each step builds on the previous:

1. **errors.py** - Exception hierarchy (no dependencies, needed by everything)
2. **client.py** - Connection management (depends on errors.py)
3. **schema.py** - Schema initialization and versioning (depends on client.py)
4. **entities.py** - Entity CRUD operations (depends on client.py, schema.py, errors.py)
5. **relationships.py** - Relationship operations (depends on client.py, entities.py)
6. **queries.py** - Higher-level graph queries (depends on entities.py, relationships.py)
7. **__init__.py** - Public API re-exports
8. **Integration** - Update campaign.py, scene.py, tools.py to use graph module

Each step should be accompanied by tests before moving to the next.

---

## 12. Key Design Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Node modeling | Multi-label (:Entity:Character) | Query flexibility at multiple abstraction levels |
| Location connections | CONNECTS_TO edges | Natural graph relationship, enables traversal |
| Character inventory | Array property | Simpler for now, can evolve to edges in split 02 |
| Transactions | Single-query atomic, best effort for multi-step | FalkorDB Python client has no multi-query transactions |
| API style | Graph-native (not Storage mirror) | Richer capabilities justify consumer updates |
| Error handling | Fail fast, no fallback | Campaign depends on graph DB being available |
| Schema init | Auto with version tracking | Seamless startup, supports future migrations |
| Event bus | Explicit calls (no bus listener) | Simpler, more predictable, follows current pattern |
| Storage coexistence | FalkorDB replaces SQLite for entities | Single source of truth, SQLite kept for logs/config |
