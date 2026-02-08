# Research Findings: Migration and Synchronization

## Part 1: Codebase Research

### 1.1 Project Structure and Architecture

**Overview:**
- Sidestage is an AI Co-Author platform for Roleplaying Games built on the Agno framework
- Written in Python 3.12+ with FastAPI web server
- Hybrid LLM support: local (llama.cpp) and cloud (Google Gemini)
- Modular architecture with clear separation of concerns

**Main Modules:**
```
/src/sidestage/
├── main.py                 # CLI entry point, Uvicorn server setup
├── orchestrator.py         # Central FastAPI app, route management, WebSocket handling
├── campaign.py            # Campaign management, LLM config, graph initialization
├── storage.py             # SQLite persistence layer
├── entities.py            # Markdown serialization/deserialization
├── schemas.py             # Pydantic models for all entity types
├── models.py              # Re-exports of schemas
├── bus.py                 # SceneMessageBus (event pub/sub system)
├── sync.py                # WebSocket broadcast manager
├── scene.py               # Scene runtime logic and message handling
├── character.py           # AgentActor for NPC autonomy
├── agent.py               # LiteLLMAgent wrapper for LLM calls
├── tools.py               # WorldTools for entity CRUD via agent calls
├── time.py                # Time management utilities
├── health.py              # Campaign health status tracking
├── graph/                 # FalkorDB integration
│   ├── client.py          # Connection management, pooling
│   ├── schema.py          # Schema versioning and migrations
│   ├── entities.py        # Entity CRUD operations
│   ├── relationships.py    # Relationship (edge) operations
│   ├── queries.py         # Complex Cypher queries
│   └── errors.py          # Graph-specific exceptions
└── memory/                # Embedding and memory system
    ├── models.py          # Memory data structures
    ├── store.py           # Memory CRUD and vector search
    ├── embeddings.py      # LiteLLM embedding generation
    ├── tools.py           # Memory tools for agents
    └── context.py         # Context assembly for agents
```

**Directory Structure:**
```
~/.sidestage/{campaign_name}/
├── config.yml             # Campaign config (LLMs, graph settings)
├── sidestage.db          # SQLite database (entities, events, sessions)
├── server.log            # Application logs
└── entities/             # Exported markdown files
```

### 1.2 Entity/Markdown Storage Format

**YAML Frontmatter + Markdown Body Format:**

```markdown
---
id: "char_co_author"
name: "Co-Author"
type: "Character"
unseen: true
location_id: null
inventory: []
---

I am the Sidestage Co-Author, a world-building assistant...
```

**Serialization Functions** (`entities.py`):
- `entity_to_markdown(entity: Entity) -> str`: Converts Pydantic models to markdown with YAML frontmatter
- `markdown_to_entity(content: str, override_id: Optional[str] = None) -> Entity`: Parses markdown back to Pydantic models

**Type Mapping** (in `markdown_to_entity`):
```python
type_map = {
    "Character": Character,
    "Location": Location,
    "Item": Item,
    "Scene": Scene,
    "Event": Event,
    "Entity": Entity
}
```

**Entity Models** (`schemas.py`):

| Entity Type | Fields | Notes |
|---|---|---|
| **Character** | `id`, `name`, `body`, `unseen` (bool), `location_id`, `inventory` (list of item IDs) | NPCs/player characters |
| **Location** | `id`, `name`, `body`, `connected_locations` (list of location IDs) | Spatial graph of the world |
| **Item** | `id`, `name`, `body` | Objects in the world |
| **Scene** | `id`, `name`, `body`, `current_gametime`, `location_id`, `events` (list), `messages` (ChatMessage list) | Conversation context |
| **Event** | `id`, `name`, `body`, `scene_id`, `gametime` (seconds), `walltime` (ISO) | Base class for all events |
| **ChatMessage** (extends Event) | `character_id`, `actor_id`, `message`, `widget` | Dialog and agent responses |

**Import/Export Operations** (`campaign.py`):
- `import_entities()`: Reads `.md` files from `~/.sidestage/{campaign}/entities/`, parses to Pydantic models, stores in SQLite or FalkorDB
- `export_entities()`: Writes all entities as `.md` files to the entities directory

### 1.3 FalkorDB Integration (Already Built)

**Client Setup** (`graph/client.py`):
```python
class GraphConfig:
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None
    vector_dimension: int | None = None

async def connect(config: GraphConfig, campaign_name: str) -> GraphClient
await close(client: GraphClient)
```

**Schema & Versioning** (`graph/schema.py`):
- Current schema version: **2**
- Version 1: Entity indexes and constraints (`Entity.id` unique + mandatory, `Entity.name` mandatory)
- Version 2: Memory system indexes + optional vector index on `Memory.embedding`

**Node Labels (Hierarchical):**
```
:Entity:Character
:Entity:Location
:Entity:Item
:Entity:Scene
:Entity:Event
:Entity:Event:ChatMessage
:Entity:Event:JoinEvent
:Entity:Event:LeaveEvent
:Entity:Event:FastForwardEvent
```

**Relationship Types** (`graph/relationships.py`):
```python
VALID_REL_TYPES = {
    "LOCATED_IN",      # Character/Item -> Location
    "CONNECTS_TO",     # Location -> Location
    "AT_LOCATION",     # Character/Item at Location
    "HAS_EVENT",       # Scene -> Event
    "INVOLVES",        # Event -> Character/Entity
    "PARTICIPATES_IN", # Character -> Scene
}
```

**Entity CRUD** (`graph/entities.py`):
- `create_entity(client, entity)`: Create node with labels and properties
- `get_entity(client, entity_id)`: Retrieve by ID, deserialize to appropriate Pydantic model
- `update_entity(client, entity_id, updates)`: Update specific properties
- `delete_entity(client, entity_id)`: DETACH DELETE with all relationships
- `list_entities(client, entity_type=None)`: Query all entities or filtered by type
- `find_entities(client, **filters)`: Find by property filters

**Relationship Operations** (`graph/relationships.py`):
- `link(client, source_id, rel_type, target_id, properties={})`: Create typed edges
- `unlink(client, source_id, rel_type, target_id)`: Delete edges
- `get_related(client, entity_id, rel_type, direction)`: Traverse relationships
- `get_relationships(client, entity_id)`: List all incoming/outgoing edges

### 1.4 Memory System (Already Built)

**Models** (`memory/models.py`):
```python
class Memory(BaseModel):
    id: str  # UUID
    content: str
    memory_type: MemoryType  # SCENE, CHARACTER, WORLD_FACT
    visibility: str  # common, private
    embedding: list[float] | None
    owner_id: str | None  # Character who owns the memory
    target_id: str        # What the memory is about
    created_at: float
    updated_at: float
    gametime: int | None
    access_count: int
    last_accessed_at: float | None
```

**Memory nodes** use labels (`Memory:SceneMemory`, `Memory:CharacterMemory`, `Memory:WorldFact`) with relationships:
- `HAS_MEMORY`: Owner Character -> Memory
- `ABOUT`: Memory -> Target Entity

**Key Operations:**
- `upsert_memory()`: Create or update with uniqueness key
- `upsert_scene_memory()`, `upsert_common_scene_memory()`, `upsert_character_memory()`, `upsert_world_fact()`
- `get_memories_for_context()`: Fetch all memories for context assembly
- `search_similar()`: Vector search with optional filtering

**Embeddings** (`memory/embeddings.py`):
- `embed_text(config, text)`: Generate embedding via LiteLLM
- `embed_and_update()`: Fire-and-forget background task
- Supports local llama.cpp and Google Gemini

### 1.5 Event Bus & WebSocket Infrastructure

**SceneMessageBus** (`bus.py`):
```python
class SceneMessageBus:
    listeners: List[EventListener]
    insert_hook: Optional[InsertHook]
    queue: asyncio.Queue[Event]

    async def start()       # Start background worker
    async def stop()        # Stop and cleanup
    def subscribe(listener) # Register async listener
    def unsubscribe(listener)
    async def publish(event) # Enqueue for processing
    async def _worker()     # Background: dispatch to all listeners
```

**Event Flow:**
1. Event published to `scene.bus.publish(event)`
2. Optional `insert_hook` runs for persistence/validation
3. Event enqueued to internal asyncio Queue
4. Background worker dispatches to all subscribers concurrently
5. Listeners (UI sync, agent responders, persistence) handle event

**WebSocket Broadcasting** (`sync.py`):
```python
class SyncManager:
    active_connections: List[WebSocket]

    async def connect(websocket)
    def disconnect(websocket)
    async def broadcast(message, exclude=)
    async def handle_message(websocket, data, handler)
```

**Message Types:**
- `chat_message`: Text from user, routed to scene bus
- `entity_content_sync`: Keystroke updates, broadcast to other clients
- `entities_updated`: Broadcast when entities change
- `scene_updated`: Broadcast when scenes change

### 1.6 WorldTools (Entity CRUD via Agents)

The `WorldTools` class (`tools.py`) already has **dual-path logic** checking `self.graph_client is not None`:
- If graph_client available: Uses `graph/entities.py` functions (create_entity, get_entity, etc.)
- Otherwise: Falls back to `self.storage` (SQLite-based Storage)

This means entity CRUD already routes through FalkorDB when available.

### 1.7 Chat Log Storage

**Schema** (`storage.py`):
```sql
CREATE TABLE scenes (id TEXT PRIMARY KEY, data TEXT)  -- JSON-serialized Scene
CREATE TABLE events (id TEXT PRIMARY KEY, data TEXT)  -- JSON-serialized Event
```

**ChatMessage Persistence:**
1. User sends message via `/v1/chat` endpoint
2. SceneLogic publishes to message bus
3. Insert hook appends to `scene.data.messages` list and calls `storage.update_scene()`
4. If graph_client: creates Event node and `HAS_EVENT` relationship
5. Bus dispatches to listeners (persistence, agents, UI broadcast)

### 1.8 Testing Setup

**Framework:** pytest with async support (pytest-anyio)

**Test Structure:**
```
/tests/
├── conftest.py              # Shared fixtures, LLM health check
└── unit/
    ├── test_entities.py     # Markdown round-trip tests
    ├── test_storage.py      # SQLite CRUD tests
    ├── test_models.py       # Schema validation
    ├── test_graph_*.py      # FalkorDB integration tests
    ├── test_memory_*.py     # Memory system tests
    ├── test_campaign.py     # Campaign lifecycle tests
    └── test_agent_loop.py   # Agent interaction tests
```

**Key Fixtures:**
```python
@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(db_path=tmp_path / "world.db")
```

**Test Execution:** `poetry run pytest tests/`

### 1.9 Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ^0.128.0 | Web framework |
| `uvicorn[standard]` | ^0.40.0 | ASGI server |
| `websockets` | ^16.0 | WebSocket support |
| `falkordb` | ^1.4.0 | Graph database client |
| `pyyaml` | ^6.0.3 | YAML parsing |
| `litellm` | ^1.81.6 | LLM provider abstraction |
| `pytest` | ^9.0.2 | Testing (dev) |
| `pytest-anyio` | - | Async test support (dev) |

---

## Part 2: Web Research

### 2.1 FalkorDB Python Client & Bulk Import

**Sync and Async API:**
```python
# Sync
from falkordb import FalkorDB
db = FalkorDB(host='localhost', port=6379)
g = db.select_graph('social')
result = g.query("CREATE (a:Person {name:'Alice'})")

# Async
from falkordb.asyncio import FalkorDB as AsyncFalkorDB
from redis.asyncio import BlockingConnectionPool
pool = BlockingConnectionPool(max_connections=16, timeout=None, decode_responses=True)
db = AsyncFalkorDB(connection_pool=pool)
g = db.select_graph('social')
result = await g.query("CREATE (a:Person {name:'Alice'})")
```

**Bulk Import Strategies (3 tiers, highest to lowest throughput):**

1. **falkordb-bulk-loader** (CSV-based, highest throughput): Dedicated CLI utility using binary `GRAPH.BULK` endpoint. Best for initial migration of large datasets.

2. **GRAPH.BULK Endpoint** (binary protocol, programmatic): Low-level binary protocol. Nodes get sequential 8-byte IDs. Blobs limited to 512 MB.

3. **Cypher UNWIND Batching** (programmatic, moderate throughput): Best for migration from Python objects:
```python
batch = [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}]
g.query("UNWIND $batch AS props CREATE (p:Person) SET p = props", {'batch': batch})
```
Recommended batch sizes: 500-1000 items per UNWIND call.

**Key recommendations:**
- Always use **MERGE** (not CREATE) for idempotent operations during migration
- Create indexes **after** bulk loading for better insertion throughput
- Use parameterized queries to leverage query plan caching
- Use async with `asyncio.gather()` for concurrent batch processing

### 2.2 FalkorDB Transaction Patterns & Limitations

**Individual query atomicity:** Each `GRAPH.QUERY` command executes atomically.

**No explicit multi-statement transaction API:** No documented `BEGIN`/`COMMIT`/`ROLLBACK`. Atomicity is per-query.

**Recommended pattern:**
1. Use single Cypher queries with UNWIND for batch atomicity
2. Use MERGE for idempotent operations (safe retry on failure)
3. Design for eventual consistency if multi-query transactions are needed

**Known Limitations:**
1. **LIMIT doesn't constrain eager operations:** `UNWIND [1,2,3] AS v CREATE (n {v:v}) RETURN n LIMIT 1` creates ALL three nodes but returns only one
2. **Relationship uniqueness in patterns:** Unreferenced relations only verify existence, not iterate
3. **No inequality index scans:** Indexes don't support `<>` filters
4. **Bulk update incremental commits:** Malformed input can leave graphs partially updated

**Performance:** FalkorDB can create 1M+ nodes in <0.5s and 500K relations in ~0.3s.

### 2.3 Bidirectional Sync Architecture Patterns

**Three primary architectural approaches:**

1. **Point-to-Point:** Direct file system ↔ database. Simplest.
2. **Hub-and-Spoke (Event Bus):** Central event bus mediates all changes. Best for multiple backends.
3. **Append-Only Operations Log:** Each system writes ops to its own log. Most robust for conflict resolution.

**Common components:**
- Change detection on both sides
- Normalized change representation
- Conflict detection (comparing versions/timestamps/checksums)
- Conflict resolution (automated or manual)
- **Loop prevention** (critical — prevent sync cycles using change-origin tracking)

### 2.4 Change Detection Approaches

**File-Side:**
| Approach | Mechanism | Latency |
|---|---|---|
| OS-level notifications (inotify/FSEvents) | Kernel events | Near-real-time |
| Polling | Periodic stat() calls | Configurable |
| Checksum/hash comparison | Content hashing | Batch-oriented |

**Recommendation:** OS-level notifications via watchfiles for real-time, with periodic hash reconciliation as safety net.

**Database-Side (FalkorDB):**
Since FalkorDB lacks native CDC, use **application-level events** — wrap all database writes in a function that both executes the query and emits a sync event.

### 2.5 Conflict Resolution Strategies

1. **Last-Write-Wins (LWW):** Simple, deterministic. Used by Cassandra, DynamoDB. Can lose data if both sides update between sync cycles.

2. **Vector Clocks:** Each location maintains vector of logical timestamps. Accurately detects true conflicts. Used by Riak, CouchDB.

3. **Field-Level Merging:** Compare individual fields. Preserves more changes, fewer manual conflicts.

4. **CRDTs:** Data structures always mergeable without conflicts. Mathematically guaranteed convergence. Limited data types.

5. **Manual/Queue-Based:** Flag conflicts and queue for resolution. Best for critical data.

**Recommendation:** Start with LWW for simplicity. Upgrade to field-level merging if needed.

### 2.6 Python File Watching Libraries

**watchfiles (Recommended for async-first projects):**
- Rust backend (notify crate), native async support
- Built-in debouncing (configurable, default 1600ms)
- Custom filter classes

```python
from watchfiles import awatch, Change

async def watch_vault(path: str):
    async for changes in awatch(path):
        for change_type, file_path in changes:
            if change_type == Change.added:
                await handle_file_added(file_path)
            elif change_type == Change.modified:
                await handle_file_modified(file_path)
            elif change_type == Change.deleted:
                await handle_file_deleted(file_path)
```

**Custom filter:**
```python
from watchfiles import DefaultFilter, Change

class MarkdownFilter(DefaultFilter):
    allowed_extensions = '.md', '.markdown'
    def __call__(self, change: Change, path: str) -> bool:
        return super().__call__(change, path) and path.endswith(self.allowed_extensions)
```

**watchdog:** More mature (10+ years), thread-based, requires bridge for async.

**Comparison:**
| Feature | watchfiles | watchdog |
|---|---|---|
| Backend | Rust (notify) | Python (OS-native) |
| Async support | Native (awatch) | Via thread bridge |
| Debouncing | Built-in | Manual |
| Performance | Higher (Rust) | Good |

### 2.7 Real-World Implementations

**CouchDB Replication Model (gold standard for bidirectional doc sync):**
- Push + Pull = Full Sync
- Revision tree per document (like Git)
- Deterministic winner selection across replicas
- All conflicting versions preserved
- Application-level conflict resolution

**Obsidian:** Files ARE the single source of truth. No dual storage. Sync delegated to file-sync providers.

### 2.8 Recommended Architecture for File ↔ FalkorDB Sync

```
+-------------------+     +------------------+     +-------------------+
|   File System     |     |   Sync Engine    |     |    FalkorDB       |
|   (Markdown)      |     |  (Orchestrator)  |     |   (Graph DB)      |
+-------------------+     +------------------+     +-------------------+
        |                         |                         |
        |  watchfiles.awatch()    |                         |
        |------------------------>|                         |
        |                         |  g.query(MERGE ...)     |
        |                         |------------------------>|
        |                         |                         |
        |                         |  Application-level      |
        |                         |  change events          |
        |                         |<------------------------|
        |  Write files            |                         |
        |<------------------------|                         |
```

**Key design decisions:**

1. **Loop prevention (critical):** Tag every sync operation with origin. Track "recently synced" paths with short TTL to suppress echo events.

2. **Conflict resolution:** File-wins-by-default with timestamp comparison. Log all conflicts for audit.

3. **Incremental sync:** Track last-sync timestamps per entity. Only process modified entities.

4. **Full reconciliation:** Periodically (e.g., on startup), hash-based comparison to catch missed changes.

### 2.9 Sources

- [FalkorDB Python Client (GitHub)](https://github.com/FalkorDB/falkordb-py)
- [FalkorDB Bulk Loader](https://github.com/FalkorDB/falkordb-bulk-loader)
- [FalkorDB Design Documentation](https://docs.falkordb.com/design/)
- [FalkorDB Known Limitations](https://docs.falkordb.com/cypher/known-limitations.html)
- [watchfiles Documentation](https://watchfiles.helpmanual.io/)
- [watchfiles API - filters](https://watchfiles.helpmanual.io/api/filters/)
- [CouchDB Conflict Model](https://docs.couchdb.org/en/stable/replication/conflicts.html)
- [Local, First, Forever (Tonsky)](https://tonsky.me/blog/crdt-filesync/)
- [Obsidian Data Storage](https://help.obsidian.md/data-storage)
