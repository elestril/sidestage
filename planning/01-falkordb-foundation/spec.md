# Spec: FalkorDB Foundation

## Overview
Establish FalkorDB as the graph database backend for Sidestage, implementing the entity graph model and core database operations. This split provides the foundational API that the Memory System and Migration/Sync splits will build upon.

## Context & Requirements

### From Project Requirements (planning/requirements.md)
- **Section 2.3:** FalkorDB for entities, relationships, and memories (planned)
- **Section 3.1:** Universal entity model shared across Characters, Locations, Items, Scenes, and Events
- **Section 4.1:** Event-driven architecture with message bus
- **Section 4.2:** Entity data models with inheritance hierarchy

### Existing Architecture Context
- Current storage: Markdown files with YAML frontmatter + SQLite for logs
- Campaign data location: `~/.sidestage/<campaign_name>/`
- Entity types: Character (extends Entity), Location (extends Entity), Scene (extends Entity), Event (Entity)
- Event system: ChatMessage, JoinEvent, LeaveEvent dispatched via message bus
- Tech stack: Python 3.12+, async-focused, Poetry

### Design Principles
- **No parallel tracks:** This is the foundation that splits 02 and 03 depend on
- **Minimal surface area:** Focus on graph operations, defer memory/vector logic to split 02
- **Schema stability:** Graph schema decisions here affect downstream splits
- **Integration point:** Must integrate cleanly with existing Actor system and event bus

## Key Decisions to Explore in Deep-Plan

### 1. Entity Node Modeling
- **Question:** How do we map Sidestage's universal entity model to FalkorDB nodes?
  - Single node type "Entity" with type property?
  - Separate node types per entity kind (Character, Location, Item, Scene, Event)?
  - Mixed approach with base entity nodes + specialized types?
- **Impact:** Affects query patterns, schema extensibility, and performance
- **Design considerations:**
  - Character has location_id, inventory properties
  - Scene has current_gametime, location_id, characters list, events list
  - Event has origin, gametime, walltime, event_type

### 2. Relationship Types & Cardinality
- **Question:** What relationship types should the graph support?
  - `LOCATED_IN` (Character → Location, Item → Location)
  - `CONTAINS` (Location → Item, Character → Item)
  - `OCCURRED_IN` (Event → Scene, Event → Character origin)
  - `PARTICIPATED_IN` (Character → Scene)
  - Others needed?
- **Impact:** Query expressiveness, inference capabilities, relationship traversal efficiency
- **Design considerations:**
  - Relationships should enable gameplay questions: "Which characters are in location X?"
  - Should support memory queries: "What happened to character Y?" (via Event relationships)

### 3. Property Storage & Indexing
- **Question:** What properties live on nodes vs relationships?
  - Core metadata (id, name, type, body/description)?
  - Timestamps (created_at, updated_at)?
  - Mutable vs immutable properties?
- **Question:** What fields should be indexed for performance?
  - Entity id (unique), name (search), type
  - Event gametime (ordering, range queries)
  - Others?
- **Impact:** Query performance, schema flexibility, data consistency

### 4. Transaction Boundaries & Consistency
- **Question:** How do we ensure data consistency across entity operations?
  - Atomic transactions for single entity updates?
  - Multi-step transactions for complex operations (e.g., character leaves location)?
  - Conflict handling strategy?
- **Question:** How to handle concurrent updates from multiple clients (WebSocket sync)?
- **Impact:** Data integrity, update propagation, error handling

### 5. Schema Evolution & Migrations
- **Question:** How do we manage schema changes after initial deployment?
  - Migration script approach (similar to SQL)?
  - Versioned schema with compatibility layer?
  - Elastic schema (property validation at app level)?
- **Impact:** Upgradability, backward compatibility with existing campaigns

## Scope & Deliverables

### In Scope
- FalkorDB connection management (pool, lifecycle, configuration)
- Entity node type definition and creation
- Relationship type definition and linking
- Basic CRUD operations for entities (create, read, update, delete)
- Query interface for entity retrieval by id, name, type
- Schema initialization (node types, relationship types, indexes)
- Transaction management and error handling
- Unit tests for database operations

### Out of Scope
- Embedding/vector properties (deferred to split 02)
- Memory node creation or querying (deferred to split 02)
- Data migration from markdown files (deferred to split 03)
- Bidirectional sync with markdown (deferred to split 03)
- Performance optimization beyond basic indexing
- Full-text search (can add later if needed)

## API Surface (Preliminary)

### Database Initialization
```python
async def init_falkordb(campaign_path: str) -> FalkorDBClient
async def close_falkordb(client: FalkorDBClient) -> None
```

### Entity Operations
```python
async def create_entity(client, entity: EntityData) -> Entity
async def get_entity(client, entity_id: str) -> Entity | None
async def update_entity(client, entity_id: str, updates: dict) -> Entity
async def delete_entity(client, entity_id: str) -> None
async def list_entities_by_type(client, entity_type: str) -> list[Entity]
```

### Relationship Operations
```python
async def link_entities(client, source_id: str, rel_type: str, target_id: str) -> Relationship
async def unlink_entities(client, source_id: str, rel_type: str, target_id: str) -> None
async def get_related(client, entity_id: str, rel_type: str, direction: str) -> list[Entity]
```

### Transaction Management
```python
async def transaction(client) -> Transaction  # context manager
async with transaction(client) as tx:
    # ... operations ...
    # auto-commits on success, rolls back on exception
```

## Integration Points

### Upstream Dependencies
- None (foundation layer)

### Downstream Dependencies
- Split 02 (Memory & Embedding): Needs entity node access, transaction API
- Split 03 (Migration & Sync): Needs full CRUD + entity listing for data import

### Event Bus Integration
- Listen for entity-related events (ChatMessage, JoinEvent, LeaveEvent)
- Trigger updates to location/character relationships
- Publish confirmation events after successful graph updates

### Existing System Integration
- Actor system (Track 5): Reads/writes character nodes for agent state
- Scene management: Scene nodes, character participation relationships
- Entity browser (Track 2): Queries for filtering/search (initially read-only)

## Testing Strategy
- Unit tests for connection management
- Unit tests for entity CRUD operations
- Integration tests with mock FalkorDB (or test instance)
- Schema validation tests
- Transaction rollback/recovery tests

## Success Criteria
1. FalkorDB connection established and configurable per campaign
2. All entity types (Character, Location, Item, Scene, Event) can be created, read, updated, deleted
3. Relationships can be created/deleted between entities
4. Queries can retrieve entities by id, name, type
5. Related entities can be retrieved via relationship traversal
6. Transactions provide ACID guarantees
7. Schema is stable and documented
8. Tests provide >80% code coverage
9. No breaking changes to existing Actor system integration
