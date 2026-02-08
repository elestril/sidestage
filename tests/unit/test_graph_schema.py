"""Tests for graph schema initialization and versioning."""

from typing import Any

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.schema import (
    CURRENT_VERSION,
    INDEXES,
    CONSTRAINTS,
    V2_INDEXES,
    get_schema_version,
    initialize_schema,
)
from sidestage.graph.errors import SchemaError


def _make_client(query_results: list[list[Any]] | None = None) -> MagicMock:
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


def _ok() -> MagicMock:
    result = MagicMock()
    result.result_set = []
    return result


# --- get_schema_version ---


@pytest.mark.anyio
async def test_get_schema_version_returns_none_for_fresh_graph():
    client = _make_client(query_results=[[]])
    version = await get_schema_version(client)
    assert version is None


@pytest.mark.anyio
async def test_get_schema_version_returns_version_for_initialized_graph():
    client = _make_client(query_results=[[[1]]])
    version = await get_schema_version(client)
    assert version == 1


# --- initialize_schema: fresh graph ---


@pytest.mark.anyio
async def test_initialize_schema_creates_indexes_on_fresh_graph():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    v1_index_queries = [q for q in queries if "CREATE INDEX" in q and any(
        f"(n:{label})" in q for label, _ in INDEXES
    )]
    assert len(v1_index_queries) == len(INDEXES)
    for label, prop in INDEXES:
        expected = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        assert expected in v1_index_queries


@pytest.mark.anyio
async def test_initialize_schema_creates_constraints_on_fresh_graph():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    constraint_queries = [q for q in queries if "CREATE CONSTRAINT" in q]
    assert len(constraint_queries) == len(CONSTRAINTS)

    assert any("Entity" in q and "id" in q and "IS UNIQUE" in q for q in constraint_queries)
    assert any("Entity" in q and "id" in q and "IS NOT NULL" in q for q in constraint_queries)
    assert any("Entity" in q and "name" in q and "IS NOT NULL" in q for q in constraint_queries)


@pytest.mark.anyio
async def test_initialize_schema_creates_schema_version_node():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    merge_queries = [q for q in queries if "MERGE" in q and "SchemaVersion" in q]
    assert len(merge_queries) == 1

    merge_call = [c for c in client.graph.query.call_args_list if "MERGE" in c.args[0]][0]
    params = merge_call.kwargs.get("params") or (merge_call.args[1] if len(merge_call.args) > 1 else None)
    assert params is not None
    assert params["version"] == CURRENT_VERSION
    assert "updated_at" in params
    datetime.fromisoformat(params["updated_at"])


# --- initialize_schema: idempotent ---


@pytest.mark.anyio
async def test_initialize_schema_idempotent():
    client = _make_client()
    version_result_none = MagicMock()
    version_result_none.result_set = []
    version_result_current = MagicMock()
    version_result_current.result_set = [[CURRENT_VERSION]]

    # First call uses exactly: 1 version_check + N_v1 + N_v2 + 1 version_set
    # Second call: 1 version_check returning CURRENT_VERSION -> no-op
    n_migration_queries = len(INDEXES) + len(CONSTRAINTS) + len(V2_INDEXES)
    client.graph.query = AsyncMock(
        side_effect=(
            [version_result_none] + [_ok()] * (n_migration_queries + 1)
            + [version_result_current]
        )
    )

    await initialize_schema(client)
    await initialize_schema(client)


@pytest.mark.anyio
async def test_initialize_schema_skips_when_version_current():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = [[CURRENT_VERSION]]
    client.graph.query = AsyncMock(return_value=version_result)

    await initialize_schema(client)

    assert client.graph.query.await_count == 1


# --- initialize_schema: migrations ---


@pytest.mark.anyio
async def test_initialize_schema_runs_migrations_when_behind():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    assert any("CREATE INDEX" in q for q in queries)
    assert any("CREATE CONSTRAINT" in q for q in queries)


@pytest.mark.anyio
async def test_initialize_schema_updates_version_after_migration():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    assert "MERGE" in queries[-1]
    assert "SchemaVersion" in queries[-1]


# --- initialize_schema: error handling ---


@pytest.mark.anyio
async def test_initialize_schema_raises_schema_error_on_failure():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []

    client.graph.query = AsyncMock(
        side_effect=[version_result, Exception("Cypher syntax error")]
    )

    with pytest.raises(SchemaError, match="Failed to create index"):
        await initialize_schema(client)


# --- index/constraint ordering ---


@pytest.mark.anyio
async def test_indexes_created_before_constraints():
    client = _make_client()
    version_result = MagicMock()
    version_result.result_set = []
    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)

    await initialize_schema(client)

    queries = [c.args[0] for c in client.graph.query.call_args_list]
    v1_index_positions = [i for i, q in enumerate(queries) if "CREATE INDEX" in q and any(
        f"(n:{label})" in q for label, _ in INDEXES
    )]
    constraint_positions = [i for i, q in enumerate(queries) if "CREATE CONSTRAINT" in q]

    assert len(v1_index_positions) > 0
    assert len(constraint_positions) > 0
    assert max(v1_index_positions) < min(constraint_positions), \
        "All v1 indexes must be created before any constraints"
