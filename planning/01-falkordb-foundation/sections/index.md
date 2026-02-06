<!-- PROJECT_CONFIG
runtime: python-poetry
test_command: poetry run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-errors-and-client
section-02-schema
section-03-entities
section-04-relationships
section-05-queries
section-06-integration
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-errors-and-client | - | 02, 03, 04, 05, 06 | Yes |
| section-02-schema | 01 | 03, 06 | No |
| section-03-entities | 01, 02 | 04, 05, 06 | No |
| section-04-relationships | 03 | 05, 06 | No |
| section-05-queries | 03, 04 | 06 | No |
| section-06-integration | 01, 02, 03, 04, 05 | - | No |

## Execution Order

1. section-01-errors-and-client (no dependencies)
2. section-02-schema (after 01)
3. section-03-entities (after 01, 02)
4. section-04-relationships (after 03)
5. section-05-queries (after 03, 04)
6. section-06-integration (final, after all)

Note: This is a largely sequential dependency chain. Each section builds on the previous. section-01 is the only section with no dependencies.

## Section Summaries

### section-01-errors-and-client
Custom exception hierarchy (`errors.py`) and FalkorDB connection management (`client.py`). Defines `GraphError` and subclasses, `GraphClient` wrapper with async connection pooling via `redis.asyncio.BlockingConnectionPool`, `GraphConfig` dataclass, and `connect()`/`close()` lifecycle functions. This is the foundation that everything else imports.

**Plan sections covered:** Section 3 (Connection Management), Section 8 (Error Handling)
**TDD sections covered:** Section 3 tests, Section 8 tests

### section-02-schema
Schema initialization and versioning (`schema.py`). Creates indexes on Entity.id, Entity.name, Event.gametime, Scene.current_gametime. Creates unique and mandatory constraints on Entity.id and Entity.name. Implements `SchemaVersion` node tracking with migration registry. Auto-initializes on connection with idempotent creation.

**Plan sections covered:** Section 4 (Schema Design & Initialization)
**TDD sections covered:** Section 4 tests

### section-03-entities
Entity CRUD operations (`entities.py`) with serialization logic. Multi-label node creation (`:Entity:Character`, etc.), entity retrieval by ID, property updates, DETACH DELETE, listing by type, and property-filtered find. Includes label-to-model registry, property serialization/deserialization, and field exclusion lists per entity type.

**Plan sections covered:** Section 5 (Entity Operations)
**TDD sections covered:** Section 5 tests (CRUD + serialization)

### section-04-relationships
Relationship operations (`relationships.py`). Edge creation/deletion between entity nodes, get_related with directional traversal, get_relationships for entity detail views. Handles CONNECTS_TO bidirectional semantics. Compound operations for entity lifecycle (Character location changes, Scene location assignment).

**Plan sections covered:** Section 6 (Relationship Operations)
**TDD sections covered:** Section 6 tests

### section-05-queries
Higher-level graph queries (`queries.py`). Specialized query functions: characters_at_location, connected_locations, scene_events (with gametime filtering), entity_graph (neighborhood to depth N). All use single Cypher queries for efficiency, return deserialized Pydantic models.

**Plan sections covered:** Section 7 (Graph Queries)
**TDD sections covered:** Section 7 tests

### section-06-integration
Integration with existing Sidestage code. Updates Campaign to create/use GraphClient, routes entity CRUD through graph module, updates SceneLogic for scene/event graph operations, updates WorldTools for graph-backed entity queries. Adds `__init__.py` public API re-exports. Adds GraphConfig to campaign configuration schema. Deprecates/removes entity methods from Storage class.

**Plan sections covered:** Section 9 (Integration), Section 10 (Dependencies), Section 11 (Implementation Order)
**TDD sections covered:** Section 9 integration tests
