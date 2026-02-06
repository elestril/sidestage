"""Tests for graph schema initialization and versioning."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.schema import (
    CURRENT_VERSION,
    INDEXES,
    CONSTRAINTS,
    get_schema_version,
    initialize_schema,
)
from sidestage.graph.errors import SchemaError


def _make_client(query_results=None):
    """Create a mock GraphClient with a mock graph.query().

    query_results: if provided, a list of result sets to return
    on successive calls to graph.query(). Each result set is a list of rows.
    If None, graph.query() returns an empty result set by default.
    """
    client = MagicMock()
    mock_graph = MagicMock()

    if query_results is not None:
        results = []
        for rs in query_results:
            result_obj = MagicMock()
            result_obj.result_set = rs
            results.append(result_obj)
        mock_graph.query = AsyncMock(side_effect=results)
    else:
        default_result = MagicMock()
        default_result.result_set = []
        mock_graph.query = AsyncMock(return_value=default_result)

    client.graph = mock_graph
    return client


# --- get_schema_version ---


@pytest.mark.anyio
async def test_get_schema_version_returns_none_for_fresh_graph():
    """On a graph with no :SchemaVersion node, get_schema_version should
    return None."""
    client = _make_client(query_results=[[]])  # empty result set
    version = await get_schema_version(client)
    assert version is None


@pytest.mark.anyio
async def test_get_schema_version_returns_version_for_initialized_graph():
    """On a graph with a :SchemaVersion node at version 1,
    get_schema_version should return 1."""
    client = _make_client(query_results=[[[1]]])  # result_set = [[1]]
    version = await get_schema_version(client)
    assert version == 1


# --- initialize_schema: fresh graph ---


@pytest.mark.anyio
async def test_initialize_schema_creates_indexes_on_fresh_graph():
    """On a fresh graph (no SchemaVersion node), initialize_schema should
    create range indexes on: Entity.id, Entity.name, Event.gametime,
    Scene.current_gametime."""
    # First query: get_schema_version returns empty (no SchemaVersion node)
    # Subsequent queries: index/constraint creation + version set (all succeed)
    client = _make_client()
    # get_schema_version returns None (empty result set)
    version_result = MagicMock()
    version_result.result_set = []
    ok_result = MagicMock()
    ok_result.result_set = []
    # Many calls: 1 version check + 4 indexes + 3 constraints + 1 version set
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    index_queries = [q for q in queries if "CREATE INDEX" in q]
    assert len(index_queries) == len(INDEXES)
    for label, prop in INDEXES:
        expected = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        assert expected in index_queries


@pytest.mark.anyio
async def test_initialize_schema_creates_constraints_on_fresh_graph():
    """On a fresh graph, initialize_schema should create:
    - UNIQUE constraint on Entity.id
    - MANDATORY (IS NOT NULL) constraint on Entity.id
    - MANDATORY (IS NOT NULL) constraint on Entity.name"""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    ok_result = MagicMock()
    ok_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    constraint_queries = [q for q in queries if "CREATE CONSTRAINT" in q]
    assert len(constraint_queries) == len(CONSTRAINTS)

    assert any("Entity" in q and "id" in q and "IS UNIQUE" in q for q in constraint_queries)
    assert any("Entity" in q and "id" in q and "IS NOT NULL" in q for q in constraint_queries)
    assert any("Entity" in q and "name" in q and "IS NOT NULL" in q for q in constraint_queries)


@pytest.mark.anyio
async def test_initialize_schema_creates_schema_version_node():
    """After initialization on a fresh graph, a :SchemaVersion node should
    be created with MERGE and set to version 1."""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    ok_result = MagicMock()
    ok_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    merge_queries = [q for q in queries if "MERGE" in q and "SchemaVersion" in q]
    assert len(merge_queries) == 1

    # Check params were passed with version and updated_at
    merge_call = [c for c in client.graph.query.call_args_list if "MERGE" in c.args[0]][0]
    params = merge_call.kwargs.get("params") or (merge_call.args[1] if len(merge_call.args) > 1 else None)
    assert params is not None
    assert params["version"] == CURRENT_VERSION
    assert "updated_at" in params
    # Verify updated_at is a valid ISO 8601 timestamp
    datetime.fromisoformat(params["updated_at"])


# --- initialize_schema: idempotent ---


@pytest.mark.anyio
async def test_initialize_schema_idempotent():
    """Calling initialize_schema twice should not raise errors."""
    client = _make_client()
    version_result_none = MagicMock()
    version_result_none.result_set = []
    version_result_one = MagicMock()
    version_result_one.result_set = [[1]]
    ok_result = MagicMock()
    ok_result.result_set = []

    # First call: fresh graph (9 queries: 1 version + 4 idx + 3 con + 1 set)
    # Second call: version already current (1 query: version check)
    client.graph.query = AsyncMock(
        side_effect=[version_result_none] + [ok_result] * 8 + [version_result_one]
    )

    await initialize_schema(client)
    await initialize_schema(client)
    # No error means success


@pytest.mark.anyio
async def test_initialize_schema_skips_when_version_current():
    """When the graph already has a SchemaVersion node at the expected
    version, initialize_schema should not execute index/constraint
    creation queries."""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = [[CURRENT_VERSION]]
    client.graph.query = AsyncMock(return_value=version_result)

    await initialize_schema(client)

    # Only one query: the version check
    assert client.graph.query.await_count == 1


# --- initialize_schema: migrations ---


@pytest.mark.anyio
async def test_initialize_schema_runs_migrations_when_behind():
    """When the graph's SchemaVersion is behind the expected version,
    initialize_schema should run migration functions."""
    # This test only applies if CURRENT_VERSION > 1. For now with v1,
    # a fresh graph (None) triggers migration. We test that _migrate_v1 runs.
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []  # No version = fresh
    ok_result = MagicMock()
    ok_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    # Verify migration ran: indexes + constraints created
    queries = [c.args[0] for c in client.graph.query.call_args_list]
    assert any("CREATE INDEX" in q for q in queries)
    assert any("CREATE CONSTRAINT" in q for q in queries)


@pytest.mark.anyio
async def test_initialize_schema_updates_version_after_migration():
    """After running migrations, the SchemaVersion node should be
    updated to the new expected version."""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    ok_result = MagicMock()
    ok_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    # Last query should be the MERGE to set version
    queries = [c.args[0] for c in client.graph.query.call_args_list]
    assert "MERGE" in queries[-1]
    assert "SchemaVersion" in queries[-1]


# --- initialize_schema: error handling ---


@pytest.mark.anyio
async def test_initialize_schema_raises_schema_error_on_failure():
    """If a migration step fails (e.g., invalid Cypher), initialize_schema
    should raise SchemaError."""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []

    # Version check succeeds, first index creation fails
    client.graph.query = AsyncMock(
        side_effect=[version_result, Exception("Cypher syntax error")]
    )

    with pytest.raises(SchemaError, match="Failed to create index"):
        await initialize_schema(client)


# --- index/constraint ordering ---


@pytest.mark.anyio
async def test_indexes_created_before_constraints():
    """Unique constraints require a range index on the same property.
    Verify that all CREATE INDEX queries are executed before any
    CREATE CONSTRAINT queries."""
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    ok_result = MagicMock()
    ok_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    # Find positions of index and constraint queries
    index_positions = [i for i, q in enumerate(queries) if "CREATE INDEX" in q]
    constraint_positions = [i for i, q in enumerate(queries) if "CREATE CONSTRAINT" in q]

    assert len(index_positions) > 0
    assert len(constraint_positions) > 0
    assert max(index_positions) < min(constraint_positions), \
        "All indexes must be created before any constraints"
