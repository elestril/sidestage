# Research Findings: FalkorDB Foundation

## Part 1: Codebase Analysis

### Project Structure & Architecture

Sidestage is a multi-agent RPG assistant built with Python 3.12+, FastAPI, and a clean separation between domain models, business logic, and infrastructure.

```
src/sidestage/
├── main.py             # Entry point, Uvicorn server
├── orchestrator.py     # Central coordinator, FastAPI routes
├── campaign.py         # Campaign container, config management
├── scene.py            # SceneLogic runtime state
├── character.py        # CharacterLogic and AgentActor
├── agent.py            # LiteLLMAgent wrapper
├── bus.py              # SceneMessageBus event system
├── schemas.py          # Pydantic models (Entity, Event types)
├── models.py           # Re-exports from schemas
├── entities.py         # Markdown serialization
├── storage.py          # SQLite storage layer
├── tools.py            # WorldTools for agent tool calls
├── sync.py             # SyncManager for WebSocket
└── time.py             # Gametime model
```

**Key Design Patterns:**
- Runtime vs. Data Separation: schemas (data) are separate from runtime logic classes
- Event-Driven Architecture: async message bus for decoupled communication
- Actor System: Characters controlled by Users or AI Agents
- Campaign-Centric: Each campaign isolated with own database and configuration

### Entity Model (schemas.py)

```python
class Entity(BaseModel):
    name: str
    body: str  # Markdown description
    id: str    # Unique identifier

class Character(Entity):
    unseen: bool = False
    location_id: Optional[str] = None
    inventory: List[str] = []  # Item IDs

class Location(Entity):
    connected_locations: List[str] = []  # Location IDs

class Item(Entity):
    pass

class Scene(Entity):
    current_gametime: Optional[int] = None
    location_id: Optional[str] = None
    events: List[str] = []       # Event IDs
    messages: List[ChatMessage] = []

class Event(Entity):
    scene_id: str
    gametime: int     # Seconds when event occurred
    walltime: str     # ISO timestamp

class ChatMessage(Event):
    character_id: str
    actor_id: Optional[str] = None
    message: str
    widget: Optional[Dict[str, Any]] = None
```

### Event Bus (bus.py)

```python
class SceneMessageBus:
    listeners: List[EventListener]    # Async callbacks
    insert_hook: Optional[InsertHook] # Pre-processing
    queue: asyncio.Queue[Event]
    _worker: background task
```

**Flow:** `publish(event)` → insert_hook (persistence) → queue → background worker → parallel listener dispatch

**Key integration points:**
- `SceneLogic._on_publish_hook`: Persists ChatMessages to scene history
- `AgentActor.on_event`: Filters and responds to messages
- `Orchestrator._on_scene_event`: Broadcasts to WebSocket clients

### Actor System (character.py)

- **AgentActor**: Autonomous "brain" wrapping a `LiteLLMAgent`
- **CharacterLogic**: Runtime wrapper managing AgentActor lifecycle
- Loop prevention: Agents skip messages where `event.actor_id == self.actor_id`

### Current Storage (storage.py)

**SQLite-based, simple key-value with JSON serialization:**
- Entity stored as `model_dump_json()`
- `INSERT OR REPLACE` for upsert semantics
- No relationships, no foreign keys, flat per-type tables
- Separate CRUD methods per entity type

**Limitations:**
- No semantic queries ("who is in this location?")
- No relationship traversal
- Linear scan for relationships
- Scene messages grow unbounded

### Dependencies (pyproject.toml)

**Core:** FastAPI, Uvicorn, websockets, litellm, openai, google-generativeai, pydantic, pyyaml, sqlalchemy, httpx, pyjwt, opentelemetry

**Dev:** pytest, pytest-timeout, pyright, pytest-anyio

### Testing Setup

- **Framework:** pytest with pytest-anyio for async tests
- **Pattern:** `@pytest.mark.anyio` for async functions
- **Fixtures:** `tmp_path` for isolated test databases
- **Mocking:** Heavy use of `unittest.mock` (AsyncMock, MagicMock)
- **Structure:** `tests/unit/`, `tests/integration/`, `tests/meta/`

### Async Patterns

All I/O-bound operations use `async def`. Key patterns:
- `asyncio.create_task()` for background workers
- `asyncio.Queue` for message passing
- `asyncio.wait()` for parallel listener dispatch
- Storage layer is currently synchronous (sqlite3)

### Integration Strategy (Codebase Insights)

- Clean `Storage` class is a facade - easy to add `GraphStorage` backend
- Campaign delegates to Storage, not direct SQL
- Entity-to-Node mapping is straightforward
- Event bus insert_hook can persist to graph
- Async architecture ready for async graph queries

---

## Part 2: FalkorDB Python Async Client Patterns

### Client Library

- **Package:** `falkordb` (falkordb-py) v1.4.0 (Dec 2025)
- **Python:** 3.10-3.14, CPython and PyPy
- **Alternative:** FalkorDBLite v0.7.0 (embedded, Jan 2026)

### Native Async Support

FalkorDB **natively supports async** via `falkordb.asyncio`:

```python
from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

async def main():
    pool = BlockingConnectionPool(
        max_connections=16, timeout=None, decode_responses=True
    )
    db = FalkorDB(connection_pool=pool)
    g = db.select_graph('social')
    result = await g.query('MATCH (n:Person) RETURN n LIMIT 10')
    await pool.aclose()
```

### Connection Pooling

- Use `BlockingConnectionPool` from `redis.asyncio`
- Configure pool size based on concurrency (default: 16)
- Set `decode_responses=True`
- Reuse instances; always close with `await pool.aclose()`

### Transaction Management

- **Each query is atomic** (no explicit BEGIN/COMMIT/ROLLBACK in Python client)
- Use `g.query()` for read-write, `g.ro_query()` for read-only
- Multi-query transactions are NOT natively supported
- For multi-step operations, use application-level coordination

### Query Best Practices

**Always use parameterized queries:**
```python
result = await g.query(
    'CREATE (p:Person {name: $name, age: $age}) RETURN p',
    params={'name': 'Alice', 'age': 30}
)
```

Benefits: execution plan caching, injection prevention, query plan reuse.

### Supported Data Types

**Scalar:** Strings, Booleans, Int64, Float64, Geospatial Points
**Temporal:** Date, Time, DateTime, Duration
**Collections:** Arrays (no null/unserializable)
**Cannot store:** null, Maps, Graph entities

---

## Part 3: FalkorDB Schema Design & Indexing

### Node Labels

- Nodes can have **0 or more labels** (multi-label support)
- Labels narrow search scope, improving performance
- Each label gets its own sparse matrix in FalkorDB

**For entity hierarchies, multi-label is recommended:**
```cypher
CREATE (c:Entity:Character {name: 'Alice', unseen: false})
MATCH (e:Entity) RETURN e        -- All entities
MATCH (c:Character) RETURN c     -- Just characters
```

### Relationship Types

- Each relationship has **exactly one type**
- Convention: UPPERCASE_WITH_UNDERSCORES (most common in docs)
- Multiple types in queries: `MATCH (a)-[r:LOCATED_IN|CONTAINS]->(b)`

### Index Types

1. **Range Index** - Exact match and range queries on single properties
   ```cypher
   CREATE INDEX FOR (e:Entity) ON (e.id)
   CREATE INDEX FOR (e:Entity) ON (e.name)
   ```

2. **Full-Text Index** - Text search with stemming, phonetic, fuzzy
   ```cypher
   CALL db.idx.fulltext.createNodeIndex('Entity', 'name', 'body')
   ```

3. **Vector Index** - Similarity search on embeddings (for split 02)

### Constraints

1. **Mandatory** - Ensure properties exist
   ```cypher
   GRAPH.CONSTRAINT CREATE myGraph MANDATORY NODE Entity PROPERTIES 1 id
   ```

2. **Unique** - Prevent duplicate values (requires range index first)
   ```cypher
   GRAPH.CONSTRAINT CREATE myGraph UNIQUE NODE Entity PROPERTIES 1 id
   ```

### Property Storage

Both nodes and relationships can store properties. Use relationship properties for:
- Transaction metadata (timestamps, amounts)
- Connection strength (weights, scores)
- Edge-specific attributes

### Schema Evolution

- FalkorDB is "schema-lite" - add new node types/relationships without affecting existing data
- Keep migration scripts in version control
- Use constraints for data quality enforcement
- No formal migration framework; application-level management

---

## Key Findings for Implementation

### Entity-to-Node Mapping (Recommended)

Use **multi-label** approach:
```
Entity → :Entity (base label on all nodes)
Character → :Entity:Character {unseen, location_id, inventory}
Location → :Entity:Location {connected_locations}
Item → :Entity:Item
Scene → :Entity:Scene {current_gametime, location_id}
Event → :Entity:Event {scene_id, gametime, walltime}
ChatMessage → :Entity:Event:ChatMessage {character_id, actor_id, message}
```

### Relationship Mapping

```
(:Character)-[:LOCATED_IN]->(:Location)
(:Character)-[:HAS_ITEM]->(:Item)
(:Location)-[:CONNECTS_TO]->(:Location)
(:Scene)-[:AT_LOCATION]->(:Location)
(:Scene)-[:HAS_EVENT]->(:Event)
(:Event)-[:INVOLVES]->(:Character)
(:Character)-[:PARTICIPATES_IN]->(:Scene)
```

### Critical Architecture Decisions

1. **No multi-query transactions** - Each Cypher query is atomic. Complex operations need app-level coordination.
2. **Async-native** - Use `falkordb.asyncio` directly, fits existing codebase async patterns.
3. **Connection pool** - Use `redis.asyncio.BlockingConnectionPool` shared across operations.
4. **Parameterized queries** - Always use `params={}` for execution plan caching.
5. **Multi-label nodes** - Enables querying at multiple abstraction levels.

### Sources

- [FalkorDB Python Client GitHub](https://github.com/FalkorDB/falkordb-py)
- [FalkorDB Official Documentation](https://docs.falkordb.com/)
- [FalkorDB Indexing](https://docs.falkordb.com/cypher/indexing/)
- [FalkorDB Constraints](https://docs.falkordb.com/commands/graph.constraint-create.html)
- [FalkorDB Design](https://docs.falkordb.com/design/)
- [FalkorDB Migration Guide](https://www.falkordb.com/blog/relational-database-to-graph-database/)
