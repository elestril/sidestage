"""Tests for schema v2 migration: Memory indexes and vector index."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.schema import (
    CURRENT_VERSION,
    initialize_schema,
)
from sidestage.graph.errors import SchemaError


def _make_client(query_side_effects):
    """Create a mock GraphClient with a sequence of query results."""
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
    assert CURRENT_VERSION == 2


# --- initialize_schema with vector_dimension ---

@pytest.mark.anyio
async def test_initialize_schema_with_vector_dimension_creates_vector_index():
    """When vector_dimension is provided and migrating from v1 to v2,
    the migration should create a vector index on Memory.embedding."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=384)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    vector_queries = [q for q in queries if "VECTOR" in q.upper()]
    assert len(vector_queries) >= 1, "Expected at least one VECTOR INDEX creation query"
    vector_q = vector_queries[0]
    assert "384" in vector_q, "Vector dimension 384 should appear in the query"


@pytest.mark.anyio
async def test_initialize_schema_without_vector_dimension_skips_vector_index():
    """When vector_dimension is None, the v2 migration should NOT create
    a vector index but should still create range indexes."""
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

    merge_calls = [
        c for c in client.graph.query.call_args_list
        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
    ]
    assert len(merge_calls) >= 1
    last_merge = merge_calls[-1]
    params = last_merge.kwargs.get("params", {})
    assert params.get("vector_dimension") == 768, \
        "vector_dimension should be stored in SchemaVersion params"


# --- Version bump ---

@pytest.mark.anyio
async def test_schema_version_bumps_from_1_to_2():
    """When graph is at version 1, initialize_schema should run v2 migration
    and set version to 2."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client)

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
    """When graph is already at version 2, initialize_schema should be a no-op."""
    effects = [_version_result(2)]
    client = _make_client(effects)

    await initialize_schema(client)

    assert client.graph.query.await_count == 1, \
        "Only the version check query should run"


# --- Fresh graph runs both v1 and v2 ---

@pytest.mark.anyio
async def test_fresh_graph_runs_v1_and_v2_migrations():
    """A fresh graph (no SchemaVersion) should run both v1 and v2 migrations."""
    effects = [_ok()] * 20
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


# --- Invalid vector_dimension ---

@pytest.mark.anyio
async def test_invalid_vector_dimension_zero():
    """vector_dimension=0 should raise SchemaError."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    with pytest.raises(SchemaError, match="Invalid vector_dimension"):
        await initialize_schema(client, vector_dimension=0)


@pytest.mark.anyio
async def test_invalid_vector_dimension_negative():
    """vector_dimension=-1 should raise SchemaError."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    with pytest.raises(SchemaError, match="Invalid vector_dimension"):
        await initialize_schema(client, vector_dimension=-1)


# --- Graceful degradation ---

@pytest.mark.anyio
async def test_vector_index_failure_is_non_fatal():
    """If vector index creation fails, migration should continue (non-fatal)."""
    version_result = _version_result(1)
    ok = _ok()
    # 1 version check + 4 range indexes succeed + vector index fails + version set
    effects = [version_result, ok, ok, ok, ok, Exception("VECTOR not supported"), ok]
    client = _make_client(effects)

    # Should NOT raise
    await initialize_schema(client, vector_dimension=384)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    # Version set should still happen
    assert any("MERGE" in q and "SchemaVersion" in q for q in queries)


# --- Dimension not stored when None ---

@pytest.mark.anyio
async def test_dimension_not_stored_when_none():
    """When vector_dimension is None, SchemaVersion should not have vector_dimension."""
    effects = [_version_result(1)] + [_ok()] * 10
    client = _make_client(effects)

    await initialize_schema(client, vector_dimension=None)

    merge_calls = [
        c for c in client.graph.query.call_args_list
        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
    ]
    assert len(merge_calls) >= 1
    params = merge_calls[-1].kwargs.get("params", {})
    assert "vector_dimension" not in params
