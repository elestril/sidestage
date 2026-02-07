Now I have all the context I need. Let me generate the section content.

# Section 02: Schema Migration (v2)

## Overview

This section extends the FalkorDB schema system to support Memory nodes. It adds a v2 migration that creates a vector index on `Memory.embedding` (conditional on `vector_dimension` being provided) and range indexes on `Memory.owner_id`, `Memory.target_id`, `Memory.memory_type`, and `Memory.visibility` for fast lookups. The `CURRENT_VERSION` constant bumps from 1 to 2, and `initialize_schema()` gains an optional `vector_dimension` parameter. The `GraphConfig` dataclass gains a `vector_dimension` field.

**Depends on:** section-01-models-and-health (for `GraphConfig.vector_dimension` field addition -- though this section also specifies that change since it is the primary consumer)

**Files modified:**
- `/home/harald/src/sidestage/src/sidestage/graph/schema.py`
- `/home/harald/src/sidestage/src/sidestage/graph/client.py`

**Files created:**
- `/home/harald/src/sidestage/tests/unit/test_schema_v2.py`

---

## Tests (Write First)

All tests go in `/home/harald/src/sidestage/tests/unit/test_schema_v2.py`. They use the same mock-based pattern as the existing tests in `/home/harald/src/sidestage/tests/unit/test_graph_schema.py`.

The existing test file `test_graph_schema.py` uses a `_make_client()` helper that creates a `MagicMock` with a mock `graph.query()` returning `AsyncMock` results. The v2 tests follow the same pattern.

```python
# /home/harald/src/sidestage/tests/unit/test_schema_v2.py

"""Tests for schema v2 migration: Memory indexes and vector index."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.schema import (
    CURRENT_VERSION,
    initialize_schema,
)
from sidestage.graph.errors import SchemaError


def _make_client(query_side_effects):
    """Create a mock GraphClient with a sequence of query results.

    Each entry in query_side_effects is either a MagicMock with
    .result_set or an Exception to raise.
    """
    client = MagicMock()
    mock_graph = MagicMock()
    mock_graph.query = AsyncMock(side_effect=query_side_effects)
    client.graph = mock_graph
    return client


def _ok():
    """Return a MagicMock representing a successful empty query result."""
    result = MagicMock()
    result.result_set = []
    return result


def _version_result(version):
    """Return a MagicMock representing a SchemaVersion query result."""
    result = MagicMock()
    result.result_set = [[version]]
    return result


# --- CURRENT_VERSION ---

def test_current_version_is_2():
    """CURRENT_VERSION should be 2 after the v2 migration is added."""
    assert CURRENT_VERSION == 2


# --- initialize_schema with vector_dimension ---

@pytest.mark.anyio
async def test_initialize_schema_with_vector_dimension_creates_vector_index():
    """When vector_dimension is provided and migrating from v1 to v2,
    the migration should create a vector index on Memory.embedding."""
    # Query sequence: version check returns 1 (at v1),
    # then v2 migration queries (range indexes + vector index),
    # then version set
    effects = [_version_result(1)] + [_ok()] * 10  # generous allowance
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=384)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    vector_queries = [q for q in queries if "VECTOR" in q.upper()]
    assert len(vector_queries) >= 1, "Expected at least one VECTOR INDEX creation query"
    # Verify dimension is referenced (either via param or literal)
    vector_q = vector_queries[0]
    # The query should reference the dimension somehow
    all_params = []
    for c in client.graph.query.call_args_list:
        if c.kwargs.get("params"):
            all_params.append(c.kwargs["params"])
    # Either the dimension appears in the query text or in parameters
    dim_in_query = "384" in vector_q
    dim_in_params = any(
        v == 384 for p in all_params for v in (p.values() if isinstance(p, dict) else [])
    )
    assert dim_in_query or dim_in_params, \
        "Vector dimension 384 should appear in the query or its parameters"


@pytest.mark.anyio
async def test_initialize_schema_without_vector_dimension_skips_vector_index():
    """When vector_dimension is None (no embed config), the v2 migration
    should NOT create a vector index but should still create range indexes."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=None)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    vector_queries = [q for q in queries if "VECTOR" in q.upper()]
    assert len(vector_queries) == 0, "No vector index should be created when vector_dimension is None"


# --- Range indexes ---

@pytest.mark.anyio
async def test_v2_migration_creates_range_indexes():
    """v2 migration should create range indexes on Memory.owner_id,
    Memory.target_id, Memory.memory_type, and Memory.visibility."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=None)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    index_queries = [q for q in queries if "CREATE INDEX" in q and "Memory" in q]

    expected_props = {"owner_id", "target_id", "memory_type", "visibility"}
    found_props = set()
    for q in index_queries:
        for prop in expected_props:
            if prop in q:
                found_props.add(prop)

    assert found_props == expected_props, \
        f"Expected range indexes on {expected_props}, found on {found_props}"


# --- Dimension stored on SchemaVersion ---

@pytest.mark.anyio
async def test_v2_migration_stores_dimension_on_schema_version():
    """After v2 migration with a vector_dimension, the dimension should be
    stored as a property on the SchemaVersion node."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=768)

    # The last query should be the MERGE to set SchemaVersion
    queries = [c.args[0] for c in client.graph.query.call_args_list]
    merge_calls = [
        c for c in client.graph.query.call_args_list
        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
    ]
    assert len(merge_calls) >= 1
    last_merge = merge_calls[-1]
    params = last_merge.kwargs.get("params", {})
    # The version set call should include vector_dimension or it should
    # be set in a separate query during migration
    all_query_params = [
        c.kwargs.get("params", {}) or {}
        for c in client.graph.query.call_args_list
    ]
    dim_stored = any(
        p.get("vector_dimension") == 768 or p.get("dim") == 768
        for p in all_query_params
        if isinstance(p, dict)
    )
    # Also check if dimension is set inline in any SchemaVersion query
    schema_queries = [c.args[0] for c in client.graph.query.call_args_list
                      if "SchemaVersion" in c.args[0]]
    dim_in_query = any("768" in q or "vector_dimension" in q or "dim" in q
                       for q in schema_queries)
    assert dim_stored or dim_in_query, \
        "Dimension should be stored on SchemaVersion node"


# --- Version bump ---

@pytest.mark.anyio
async def test_schema_version_bumps_from_1_to_2():
    """When graph is at version 1, initialize_schema should run v2 migration
    and set version to 2."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client)

    # Find the MERGE SchemaVersion call and verify version=2
    merge_calls = [
        c for c in client.graph.query.call_args_list
        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
    ]
    assert len(merge_calls) >= 1
    params = merge_calls[-1].kwargs.get("params", {})
    assert params.get("version") == 2


# --- No-op when already at v2 ---

@pytest.mark.anyio
async def test_initialize_schema_noop_when_already_at_v2():
    """When graph is already at version 2, initialize_schema should be a no-op
    (only the version check query is executed)."""
    effects = [_version_result(2)]
    client = _make_client(effects)

    await initialize_schema(client)

    assert client.graph.query.await_count == 1, \
        "Only the version check query should run"


# --- Fresh graph runs both v1 and v2 ---

@pytest.mark.anyio
async def test_fresh_graph_runs_v1_and_v2_migrations():
    """A fresh graph (no SchemaVersion) should run both v1 and v2 migrations."""
    effects = [_ok()] * 20  # generous: v1 indexes/constraints + v2 indexes + version set
    client = _make_client(effects)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]

    # v1 artifacts: Entity indexes and constraints
    assert any("CREATE INDEX" in q and "Entity" in q for q in queries), \
        "v1 migration should create Entity indexes"
    assert any("CREATE CONSTRAINT" in q for q in queries), \
        "v1 migration should create Entity constraints"

    # v2 artifacts: Memory range indexes
    assert any("CREATE INDEX" in q and "Memory" in q for q in queries), \
        "v2 migration should create Memory indexes"
```

---

## Implementation Details

### 1. Extend `GraphConfig` with `vector_dimension`

**File:** `/home/harald/src/sidestage/src/sidestage/graph/client.py`

Add an optional `vector_dimension` field to the `GraphConfig` dataclass. This field is set at campaign startup after making a test embedding call and is consumed by the schema migration to create a vector index of the correct size.

```python
@dataclass
class GraphConfig:
    """FalkorDB connection configuration."""
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None
    vector_dimension: int | None = None  # Set from test embedding call at startup
```

**Note:** Section 01 (models-and-health) also specifies adding this field to `GraphConfig`. If section 01 has already been implemented, this change may already be present. If not, this section adds it. Either way, the field must exist before the schema migration can use it.

Additionally, update the `connect()` function to pass `vector_dimension` through to `initialize_schema()`:

```python
async def connect(config: GraphConfig, campaign_name: str = "default") -> GraphClient:
    # ... existing pool/db/graph creation ...

    client = GraphClient(pool=pool, db=db, graph=graph, graph_name=graph_name)

    from sidestage.graph.schema import initialize_schema
    await initialize_schema(client, vector_dimension=config.vector_dimension)

    return client
```

### 2. Extend `initialize_schema()` with `vector_dimension` parameter

**File:** `/home/harald/src/sidestage/src/sidestage/graph/schema.py`

The function signature changes to accept an optional `vector_dimension`:

```python
async def initialize_schema(client: GraphClient, vector_dimension: int | None = None) -> None:
```

The `vector_dimension` is threaded through to the v2 migration function. The migration registry changes to accommodate migrations that need extra context. One clean approach: pass `vector_dimension` via a closure or store it on the client temporarily. The simplest approach is to have `initialize_schema()` pass it directly to `_migrate_v2()` when calling that specific migration.

### 3. Bump `CURRENT_VERSION` to 2

```python
CURRENT_VERSION = 2
```

### 4. Add the v2 migration function

The `_migrate_v2` function creates:

1. **Range indexes** on Memory properties for fast graph-based lookups:
   - `Memory.owner_id`
   - `Memory.target_id`
   - `Memory.memory_type`
   - `Memory.visibility`

2. **Vector index** on `Memory.embedding` (only if `vector_dimension` is provided):
   ```cypher
   CREATE VECTOR INDEX FOR (n:Memory) ON n.embedding
   OPTIONS {dimension: <dim>, similarityFunction: 'cosine'}
   ```

3. **Stores the dimension** on the SchemaVersion node as `vector_dimension` property, so it can be queried later if needed.

The migration function signature:

```python
async def _migrate_v2(client: GraphClient, vector_dimension: int | None = None) -> None:
    """Memory schema migration: range indexes + optional vector index.

    Creates range indexes on Memory.owner_id, Memory.target_id,
    Memory.memory_type, and Memory.visibility.

    If vector_dimension is provided, also creates a vector index on
    Memory.embedding with cosine similarity.

    Stores vector_dimension on the SchemaVersion node for reference.
    """
```

### 5. Update the MIGRATIONS registry

The current `MIGRATIONS` dict maps version numbers to callables. Since `_migrate_v2` needs the `vector_dimension` parameter, `initialize_schema()` needs to handle this. The cleanest approach is to change how `initialize_schema()` calls migration functions, passing extra context to v2+:

```python
MIGRATIONS: dict[int, Callable] = {
    1: _migrate_v1,
    2: _migrate_v2,
}
```

In `initialize_schema()`, when calling a migration that accepts extra parameters (v2), use `functools.partial` or explicit conditional logic:

```python
for version in range(start_version, CURRENT_VERSION + 1):
    migrate_fn = MIGRATIONS.get(version)
    if migrate_fn is None:
        raise SchemaError(f"Schema migration failed: no migration for version {version}")
    try:
        if version == 2:
            await migrate_fn(client, vector_dimension=vector_dimension)
        else:
            await migrate_fn(client)
    except SchemaError:
        raise
    except Exception as exc:
        raise SchemaError(f"Schema migration failed at version {version}: {exc}") from exc
```

Alternatively, give all migration functions the same signature accepting `**kwargs`, or use `inspect.signature` to detect which parameters the migration accepts. The explicit conditional approach is simplest and most readable for a small number of migrations.

### 6. Update `_set_schema_version` to store vector_dimension

Extend the `_set_schema_version` function (or add a separate call in `_migrate_v2`) to store the vector dimension on the SchemaVersion node:

```python
async def _set_schema_version(client: GraphClient, version: int, **extra_props) -> None:
    """Create or update the :SchemaVersion node.

    Extra properties (like vector_dimension) are stored alongside version.
    """
    updated_at = datetime.now(timezone.utc).isoformat()
    params = {"version": version, "updated_at": updated_at, **extra_props}

    # Build SET clause dynamically for extra props
    set_parts = ["v.version = $version", "v.updated_at = $updated_at"]
    for key in extra_props:
        set_parts.append(f"v.{key} = ${key}")

    set_clause = ", ".join(set_parts)
    await client.graph.query(
        f"MERGE (v:SchemaVersion) SET {set_clause}",
        params=params,
    )
```

Then in `initialize_schema()`, after all migrations complete:

```python
extra = {}
if vector_dimension is not None:
    extra["vector_dimension"] = vector_dimension
await _set_schema_version(client, CURRENT_VERSION, **extra)
```

### 7. Memory Range Indexes

The v2 migration creates these four range indexes:

```python
V2_INDEXES: list[tuple[str, str]] = [
    ("Memory", "owner_id"),
    ("Memory", "target_id"),
    ("Memory", "memory_type"),
    ("Memory", "visibility"),
]
```

Each is created with the same Cypher pattern as v1:
```cypher
CREATE INDEX FOR (n:Memory) ON (n.owner_id)
CREATE INDEX FOR (n:Memory) ON (n.target_id)
CREATE INDEX FOR (n:Memory) ON (n.memory_type)
CREATE INDEX FOR (n:Memory) ON (n.visibility)
```

### 8. Vector Index Creation

The vector index uses FalkorDB's vector index syntax. Note: FalkorDB 4.0+ is required. The Cypher is:

```cypher
CREATE VECTOR INDEX FOR (n:Memory) ON n.embedding
OPTIONS {dimension: <dim>, similarityFunction: 'cosine'}
```

FalkorDB does not support parameterized values in `OPTIONS` for `CREATE VECTOR INDEX`, so the dimension must be interpolated directly into the query string. Since `vector_dimension` is always an `int` from internal code (not user input), this is safe from injection. The implementation should include a validation check:

```python
if not isinstance(vector_dimension, int) or vector_dimension <= 0:
    raise SchemaError(f"Invalid vector_dimension: {vector_dimension}")
```

### 9. Error Handling

All migration queries follow the existing pattern: wrap failures in `SchemaError`. If a range index creation fails, the migration stops and the error propagates. The caller (`connect()`) will see the `SchemaError`.

If the vector index creation fails (e.g., FalkorDB server version doesn't support it), the migration logs a warning but does NOT fail the entire migration. The campaign should still be usable without vector search -- only vector-based similarity queries will be unavailable. This matches the graceful degradation philosophy described in the plan.

---

## Existing Test Updates

The existing tests in `/home/harald/src/sidestage/tests/unit/test_graph_schema.py` need minor updates because `CURRENT_VERSION` changes from 1 to 2, and `initialize_schema` now accepts an optional `vector_dimension` parameter.

Key changes needed in existing tests:

1. **`test_initialize_schema_creates_indexes_on_fresh_graph`**: The number of queries increases because v2 migration adds Memory indexes. Update the `side_effect` list to provide enough `ok_result` entries for both v1 and v2 migrations.

2. **`test_initialize_schema_creates_constraints_on_fresh_graph`**: Same adjustment -- more queries in total.

3. **`test_initialize_schema_creates_schema_version_node`**: The version set query now includes `CURRENT_VERSION == 2`.

4. **`test_initialize_schema_idempotent`**: The "already current" version result needs to return `2` instead of `1`.

5. **`test_initialize_schema_skips_when_version_current`**: `CURRENT_VERSION` is now 2.

6. Various tests with hardcoded query counts: increase the `side_effect` lists to account for the additional v2 migration queries (4 range indexes + optionally 1 vector index + potentially 1 dimension storage query).

The pattern is straightforward: provide more `ok_result` entries in the `side_effect` list and update version expectations from 1 to 2. No structural changes are needed.

---

## Caller Changes (for Context)

This section modifies `connect()` in `client.py` to pass `vector_dimension` through. The actual setting of `GraphConfig.vector_dimension` happens in `Campaign.start_graph()` (covered in later sections -- section-04-embeddings and section-08-scene-integration). The flow is:

1. Campaign startup: if `embed` LLM config exists, make a test embedding call to determine dimension
2. Set `self.config.graph.vector_dimension = detected_dimension`
3. Call `connect(config, campaign_name=self.name)` which passes `vector_dimension` to `initialize_schema()`
4. Schema v2 migration creates the vector index with the correct dimension

If no `embed` config exists, `vector_dimension` remains `None`, and the vector index is skipped. Memories still work via graph-based retrieval -- only vector similarity search is unavailable.