Good, `pytest.mark.anyio` is used in the project. Now I have all the context I need. Let me produce the section content.

# Section 02: Schema Design and Initialization (`schema.py`)

## Overview

This section implements schema initialization and version tracking for the FalkorDB graph database. The `schema.py` module lives at `/home/harald/src/sidestage/src/sidestage/graph/schema.py` and is responsible for creating indexes, constraints, and a `SchemaVersion` tracking node on graph startup. It is called automatically by the `connect()` function in `client.py` (from section-01) after a connection pool is established.

## Dependencies

- **section-01-errors-and-client** must be completed first. This section depends on:
  - `GraphClient` from `/home/harald/src/sidestage/src/sidestage/graph/client.py` -- provides `client.graph` (a FalkorDB `Graph` object) used to execute Cypher queries
  - `SchemaError` from `/home/harald/src/sidestage/src/sidestage/graph/errors.py` -- raised when schema initialization or migration fails

## Background

FalkorDB supports Cypher queries for creating indexes and constraints. Key behaviors that inform this implementation:

- Creating an index that already exists is a no-op (idempotent)
- Unique constraints require a range index on the same property to already exist, so indexes must be created before constraints
- FalkorDB supports `CREATE INDEX FOR (n:Label) ON (n.property)` syntax for range indexes
- FalkorDB supports `CREATE CONSTRAINT ON (n:Label) ASSERT n.property IS UNIQUE` and `IS NOT NULL` syntax

### Node Labels

Every entity node in the graph carries the `:Entity` base label plus its specific type label. The full label mapping is:

| Sidestage Type | Node Labels |
|---|---|
| Character | `:Entity:Character` |
| Location | `:Entity:Location` |
| Item | `:Entity:Item` |
| Scene | `:Entity:Scene` |
| Event | `:Entity:Event` |
| ChatMessage | `:Entity:Event:ChatMessage` |

The `:Entity` base label enables cross-type queries (e.g., "find entity by id regardless of type"). This is why the indexes and constraints are primarily on the `:Entity` label.

### Relationship Types

These are documented here for context (relationships are created in later sections, but the schema must be designed with them in mind):

| Relationship | Source -> Target |
|---|---|
| `LOCATED_IN` | Character -> Location |
| `CONNECTS_TO` | Location -> Location |
| `AT_LOCATION` | Scene -> Location |
| `HAS_EVENT` | Scene -> Event |
| `INVOLVES` | Event -> Character |
| `PARTICIPATES_IN` | Character -> Scene |

## Tests First

### File: `/home/harald/src/sidestage/tests/unit/test_graph_schema.py`

All tests use `pytest` with `pytest-anyio` for async support and `unittest.mock` for mocking the `GraphClient`.

```python
"""Tests for graph schema initialization and versioning."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# Test: initialize_schema creates all expected indexes on fresh graph
@pytest.mark.anyio
async def test_initialize_schema_creates_indexes_on_fresh_graph():
    """On a fresh graph (no SchemaVersion node), initialize_schema should
    create range indexes on: Entity.id, Entity.name, Event.gametime,
    Scene.current_gametime. Verify by inspecting the Cypher queries
    passed to client.graph.query()."""


# Test: initialize_schema creates all expected constraints on fresh graph
@pytest.mark.anyio
async def test_initialize_schema_creates_constraints_on_fresh_graph():
    """On a fresh graph, initialize_schema should create:
    - UNIQUE constraint on Entity.id
    - MANDATORY (IS NOT NULL) constraint on Entity.id
    - MANDATORY (IS NOT NULL) constraint on Entity.name
    Verify by inspecting Cypher queries."""


# Test: initialize_schema creates SchemaVersion node at version 1
@pytest.mark.anyio
async def test_initialize_schema_creates_schema_version_node():
    """After initialization on a fresh graph, a :SchemaVersion node should
    exist with version=1 and a valid updated_at ISO timestamp."""


# Test: initialize_schema is idempotent (calling twice doesn't error)
@pytest.mark.anyio
async def test_initialize_schema_idempotent():
    """Calling initialize_schema twice should not raise errors.
    The second call should detect the existing SchemaVersion node
    and skip re-initialization if versions match."""


# Test: initialize_schema detects existing version and skips if current
@pytest.mark.anyio
async def test_initialize_schema_skips_when_version_current():
    """When the graph already has a SchemaVersion node at the expected
    version, initialize_schema should not execute index/constraint
    creation queries."""


# Test: initialize_schema runs migrations when version is behind
@pytest.mark.anyio
async def test_initialize_schema_runs_migrations_when_behind():
    """When the graph's SchemaVersion is behind the expected version,
    initialize_schema should run migration functions for each
    intermediate version step."""


# Test: initialize_schema updates SchemaVersion node after migration
@pytest.mark.anyio
async def test_initialize_schema_updates_version_after_migration():
    """After running migrations, the SchemaVersion node should be
    updated to the new expected version with a fresh updated_at timestamp."""


# Test: initialize_schema raises SchemaError on migration failure
@pytest.mark.anyio
async def test_initialize_schema_raises_schema_error_on_failure():
    """If a migration step fails (e.g., invalid Cypher), initialize_schema
    should raise SchemaError with a descriptive message."""


# Test: get_schema_version returns None for fresh graph (no SchemaVersion node)
@pytest.mark.anyio
async def test_get_schema_version_returns_none_for_fresh_graph():
    """On a graph with no :SchemaVersion node, get_schema_version should
    return None."""


# Test: get_schema_version returns version number for initialized graph
@pytest.mark.anyio
async def test_get_schema_version_returns_version_for_initialized_graph():
    """On a graph with a :SchemaVersion node at version 1,
    get_schema_version should return 1."""


# Test: index creation order (indexes before constraints)
@pytest.mark.anyio
async def test_indexes_created_before_constraints():
    """Unique constraints require a range index on the same property.
    Verify that all CREATE INDEX queries are executed before any
    CREATE CONSTRAINT queries."""
```

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/graph/schema.py`

This module exposes two public functions and several module-level constants.

### Constants

Define the schema specification as module-level data structures:

```python
"""Schema initialization and versioning for FalkorDB graph."""

from __future__ import annotations

CURRENT_VERSION = 1

INDEXES: list[tuple[str, str]] = [
    ("Entity", "id"),
    ("Entity", "name"),
    ("Event", "gametime"),
    ("Scene", "current_gametime"),
]

CONSTRAINTS: list[tuple[str, str, str]] = [
    ("Entity", "id", "unique"),
    ("Entity", "id", "mandatory"),
    ("Entity", "name", "mandatory"),
]
```

Each index tuple is `(label, property)`. Each constraint tuple is `(label, property, constraint_type)` where `constraint_type` is either `"unique"` or `"mandatory"`.

### Migration Registry

Migrations are stored as a dict mapping version numbers to async callables:

```python
MIGRATIONS: dict[int, Callable] = {
    1: _migrate_v1,
}
```

For version 1, the migration function `_migrate_v1` creates all indexes and constraints from scratch. This is the "bootstrap" migration. Future versions will add entries for incremental schema changes.

### Public Functions

#### `get_schema_version`

```python
async def get_schema_version(client: GraphClient) -> int | None:
    """Query the graph for a :SchemaVersion node and return its version.

    Returns None if no SchemaVersion node exists (fresh graph).
    Uses Cypher: MATCH (v:SchemaVersion) RETURN v.version
    """
```

This function queries `client.graph` for a `:SchemaVersion` node. If the result set is empty, it returns `None`. Otherwise it returns the integer `version` property from the node.

#### `initialize_schema`

```python
async def initialize_schema(client: GraphClient) -> None:
    """Initialize or migrate the graph schema.

    1. Calls get_schema_version to check current state
    2. If None (fresh graph): runs all migrations from v1 to CURRENT_VERSION
    3. If version < CURRENT_VERSION: runs migrations for each version step
    4. If version == CURRENT_VERSION: no-op (already up to date)
    5. Creates or updates the :SchemaVersion node with CURRENT_VERSION and
       an ISO timestamp in updated_at

    Raises SchemaError if any migration step fails.
    """
```

### Internal Functions

#### `_migrate_v1`

```python
async def _migrate_v1(client: GraphClient) -> None:
    """Bootstrap migration: create all indexes and constraints.

    Iterates over INDEXES and creates range indexes using:
        CREATE INDEX FOR (n:{label}) ON (n.{property})

    Then iterates over CONSTRAINTS and creates them using:
        For 'unique':    CREATE CONSTRAINT ON (n:{label}) ASSERT n.{property} IS UNIQUE
        For 'mandatory': CREATE CONSTRAINT ON (n:{label}) ASSERT n.{property} IS NOT NULL

    Order matters: indexes MUST be created before unique constraints,
    because unique constraints require a range index on the same property.
    """
```

#### `_set_schema_version`

```python
async def _set_schema_version(client: GraphClient, version: int) -> None:
    """Create or update the :SchemaVersion node.

    Uses MERGE to upsert:
        MERGE (v:SchemaVersion)
        SET v.version = $version, v.updated_at = $updated_at
    
    The updated_at value is the current UTC time in ISO 8601 format.
    """
```

### Cypher Query Patterns

The Cypher queries used by this module:

**Get schema version:**
```cypher
MATCH (v:SchemaVersion) RETURN v.version AS version
```

**Create range index:**
```cypher
CREATE INDEX FOR (n:Entity) ON (n.id)
```

**Create unique constraint:**
```cypher
CREATE CONSTRAINT ON (n:Entity) ASSERT n.id IS UNIQUE
```

**Create mandatory constraint:**
```cypher
CREATE CONSTRAINT ON (n:Entity) ASSERT n.id IS NOT NULL
```

**Upsert schema version:**
```cypher
MERGE (v:SchemaVersion) SET v.version = $version, v.updated_at = $updated_at
```

### Interaction with `client.py`

The `connect()` function in `client.py` (section-01) calls `initialize_schema(client)` after establishing the connection pool and selecting the graph. This ensures the schema is always up to date when a campaign starts. The call sequence is:

1. `connect()` creates the `BlockingConnectionPool`
2. `connect()` creates the `FalkorDB` instance and calls `db.select_graph(graph_name)`
3. `connect()` calls `initialize_schema(client)` -- this is the entry point for this module
4. `connect()` returns the fully initialized `GraphClient`

### Error Handling

- If any index or constraint creation Cypher query fails, catch the exception, wrap it in `SchemaError` with context (which index/constraint failed and why), and re-raise
- If `get_schema_version` fails due to a connection issue, let the underlying connection error propagate (it will be a `ConnectionError` from `errors.py`)
- Log each step of initialization at `INFO` level: "Creating index on Entity.id", "Creating unique constraint on Entity.id", etc.
- Log schema version transitions: "Schema version: None -> 1", "Schema already at version 1"

### FalkorDB Graph Query API

Queries are executed via `client.graph.query(cypher_string)`. The FalkorDB Python client's `Graph.query()` method is an async method (when using `falkordb.asyncio`) that returns a result object. The result object has a `.result_set` attribute containing rows of data. For parameterized queries, use `client.graph.query(cypher_string, params)` where `params` is a dict.

## Implementation Checklist

1. Create `/home/harald/src/sidestage/src/sidestage/graph/schema.py`
2. Define `CURRENT_VERSION`, `INDEXES`, `CONSTRAINTS`, and `MIGRATIONS` constants
3. Implement `get_schema_version(client)` -- query for `:SchemaVersion` node
4. Implement `_set_schema_version(client, version)` -- MERGE upsert of version node
5. Implement `_migrate_v1(client)` -- create all indexes then all constraints
6. Implement `initialize_schema(client)` -- orchestrate version check and migration
7. Create `/home/harald/src/sidestage/tests/unit/test_graph_schema.py` with all test stubs
8. Implement all tests using mocked `GraphClient` (mock `client.graph.query()`)
9. Verify tests pass with `poetry run pytest tests/unit/test_graph_schema.py`