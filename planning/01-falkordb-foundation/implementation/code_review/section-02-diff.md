diff --git a/src/sidestage/graph/schema.py b/src/sidestage/graph/schema.py
new file mode 100644
index 0000000..0fcd0b2
--- /dev/null
+++ b/src/sidestage/graph/schema.py
@@ -0,0 +1,108 @@
+"""Schema initialization and versioning for FalkorDB graph."""
+
+from __future__ import annotations
+
+import logging
+from collections.abc import Callable
+from datetime import datetime, timezone
+
+from sidestage.graph.client import GraphClient
+from sidestage.graph.errors import SchemaError
+
+logger = logging.getLogger(__name__)
+
+CURRENT_VERSION = 1
+
+INDEXES: list[tuple[str, str]] = [
+    ("Entity", "id"),
+    ("Entity", "name"),
+    ("Event", "gametime"),
+    ("Scene", "current_gametime"),
+]
+
+CONSTRAINTS: list[tuple[str, str, str]] = [
+    ("Entity", "id", "unique"),
+    ("Entity", "id", "mandatory"),
+    ("Entity", "name", "mandatory"),
+]
+
+
+async def get_schema_version(client: GraphClient) -> int | None:
+    """Query the graph for a :SchemaVersion node and return its version.
+
+    Returns None if no SchemaVersion node exists (fresh graph).
+    """
+    result = await client.graph.query("MATCH (v:SchemaVersion) RETURN v.version AS version")
+    if not result.result_set:
+        return None
+    return result.result_set[0][0]
+
+
+async def initialize_schema(client: GraphClient) -> None:
+    """Initialize or migrate the graph schema.
+
+    1. Calls get_schema_version to check current state
+    2. If None (fresh graph): runs all migrations from v1 to CURRENT_VERSION
+    3. If version < CURRENT_VERSION: runs migrations for each version step
+    4. If version == CURRENT_VERSION: no-op (already up to date)
+    5. Creates or updates the :SchemaVersion node
+
+    Raises SchemaError if any migration step fails.
+    """
+    current = await get_schema_version(client)
+
+    if current == CURRENT_VERSION:
+        logger.info("Schema already at version %d", CURRENT_VERSION)
+        return
+
+    start_version = (current or 0) + 1
+    logger.info("Schema version: %s -> %d", current, CURRENT_VERSION)
+
+    for version in range(start_version, CURRENT_VERSION + 1):
+        migrate_fn = MIGRATIONS.get(version)
+        if migrate_fn is None:
+            raise SchemaError(f"Schema migration failed: no migration for version {version}")
+        try:
+            await migrate_fn(client)
+        except SchemaError:
+            raise
+        except Exception as exc:
+            raise SchemaError(f"Schema migration failed at version {version}: {exc}") from exc
+
+    await _set_schema_version(client, CURRENT_VERSION)
+
+
+async def _migrate_v1(client: GraphClient) -> None:
+    """Bootstrap migration: create all indexes and constraints.
+
+    Indexes MUST be created before unique constraints, because unique
+    constraints require a range index on the same property.
+    """
+    for label, prop in INDEXES:
+        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
+        logger.info("Creating index on %s.%s", label, prop)
+        await client.graph.query(query)
+
+    for label, prop, constraint_type in CONSTRAINTS:
+        if constraint_type == "unique":
+            query = f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS UNIQUE"
+        elif constraint_type == "mandatory":
+            query = f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS NOT NULL"
+        else:
+            raise SchemaError(f"Unknown constraint type: {constraint_type}")
+        logger.info("Creating %s constraint on %s.%s", constraint_type, label, prop)
+        await client.graph.query(query)
+
+
+async def _set_schema_version(client: GraphClient, version: int) -> None:
+    """Create or update the :SchemaVersion node."""
+    updated_at = datetime.now(timezone.utc).isoformat()
+    await client.graph.query(
+        "MERGE (v:SchemaVersion) SET v.version = $version, v.updated_at = $updated_at",
+        params={"version": version, "updated_at": updated_at},
+    )
+
+
+MIGRATIONS: dict[int, Callable] = {
+    1: _migrate_v1,
+}
diff --git a/tests/unit/test_graph_schema.py b/tests/unit/test_graph_schema.py
new file mode 100644
index 0000000..f11ccc1
--- /dev/null
+++ b/tests/unit/test_graph_schema.py
@@ -0,0 +1,269 @@
+"""Tests for graph schema initialization and versioning."""
+
+import pytest
+from unittest.mock import AsyncMock, MagicMock, call
+
+from sidestage.graph.schema import (
+    CURRENT_VERSION,
+    INDEXES,
+    CONSTRAINTS,
+    get_schema_version,
+    initialize_schema,
+)
+from sidestage.graph.errors import SchemaError
+
+
+def _make_client(query_results=None):
+    """Create a mock GraphClient with a mock graph.query().
+
+    query_results: if provided, a list of result sets to return
+    on successive calls to graph.query(). Each result set is a list of rows.
+    If None, graph.query() returns an empty result set by default.
+    """
+    client = MagicMock()
+    mock_graph = MagicMock()
+
+    if query_results is not None:
+        results = []
+        for rs in query_results:
+            result_obj = MagicMock()
+            result_obj.result_set = rs
+            results.append(result_obj)
+        mock_graph.query = AsyncMock(side_effect=results)
+    else:
+        default_result = MagicMock()
+        default_result.result_set = []
+        mock_graph.query = AsyncMock(return_value=default_result)
+
+    client.graph = mock_graph
+    return client
+
+
+# --- get_schema_version ---
+
+
+@pytest.mark.anyio
+async def test_get_schema_version_returns_none_for_fresh_graph():
+    """On a graph with no :SchemaVersion node, get_schema_version should
+    return None."""
+    client = _make_client(query_results=[[]])  # empty result set
+    version = await get_schema_version(client)
+    assert version is None
+
+
+@pytest.mark.anyio
+async def test_get_schema_version_returns_version_for_initialized_graph():
+    """On a graph with a :SchemaVersion node at version 1,
+    get_schema_version should return 1."""
+    client = _make_client(query_results=[[[1]]])  # result_set = [[1]]
+    version = await get_schema_version(client)
+    assert version == 1
+
+
+# --- initialize_schema: fresh graph ---
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_creates_indexes_on_fresh_graph():
+    """On a fresh graph (no SchemaVersion node), initialize_schema should
+    create range indexes on: Entity.id, Entity.name, Event.gametime,
+    Scene.current_gametime."""
+    # First query: get_schema_version returns empty (no SchemaVersion node)
+    # Subsequent queries: index/constraint creation + version set (all succeed)
+    client = _make_client()
+    # get_schema_version returns None (empty result set)
+    version_result = MagicMock()
+    version_result.result_set = []
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    # Many calls: 1 version check + 4 indexes + 3 constraints + 1 version set
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    index_queries = [q for q in queries if "CREATE INDEX" in q]
+    assert len(index_queries) == len(INDEXES)
+    for label, prop in INDEXES:
+        expected = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
+        assert expected in index_queries
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_creates_constraints_on_fresh_graph():
+    """On a fresh graph, initialize_schema should create:
+    - UNIQUE constraint on Entity.id
+    - MANDATORY (IS NOT NULL) constraint on Entity.id
+    - MANDATORY (IS NOT NULL) constraint on Entity.name"""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    constraint_queries = [q for q in queries if "CREATE CONSTRAINT" in q]
+    assert len(constraint_queries) == len(CONSTRAINTS)
+
+    assert any("Entity" in q and "id" in q and "IS UNIQUE" in q for q in constraint_queries)
+    assert any("Entity" in q and "id" in q and "IS NOT NULL" in q for q in constraint_queries)
+    assert any("Entity" in q and "name" in q and "IS NOT NULL" in q for q in constraint_queries)
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_creates_schema_version_node():
+    """After initialization on a fresh graph, a :SchemaVersion node should
+    be created with MERGE and set to version 1."""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    merge_queries = [q for q in queries if "MERGE" in q and "SchemaVersion" in q]
+    assert len(merge_queries) == 1
+
+    # Check params were passed with version
+    merge_call = [c for c in client.graph.query.call_args_list if "MERGE" in c.args[0]][0]
+    params = merge_call.kwargs.get("params") or (merge_call.args[1] if len(merge_call.args) > 1 else None)
+    assert params is not None
+    assert params["version"] == CURRENT_VERSION
+
+
+# --- initialize_schema: idempotent ---
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_idempotent():
+    """Calling initialize_schema twice should not raise errors."""
+    client = _make_client()
+    version_result_none = MagicMock()
+    version_result_none.result_set = []
+    version_result_one = MagicMock()
+    version_result_one.result_set = [[1]]
+    ok_result = MagicMock()
+    ok_result.result_set = []
+
+    # First call: fresh graph (9 queries: 1 version + 4 idx + 3 con + 1 set)
+    # Second call: version already current (1 query: version check)
+    client.graph.query = AsyncMock(
+        side_effect=[version_result_none] + [ok_result] * 8 + [version_result_one]
+    )
+
+    await initialize_schema(client)
+    await initialize_schema(client)
+    # No error means success
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_skips_when_version_current():
+    """When the graph already has a SchemaVersion node at the expected
+    version, initialize_schema should not execute index/constraint
+    creation queries."""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = [[CURRENT_VERSION]]
+    client.graph.query = AsyncMock(return_value=version_result)
+
+    await initialize_schema(client)
+
+    # Only one query: the version check
+    assert client.graph.query.await_count == 1
+
+
+# --- initialize_schema: migrations ---
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_runs_migrations_when_behind():
+    """When the graph's SchemaVersion is behind the expected version,
+    initialize_schema should run migration functions."""
+    # This test only applies if CURRENT_VERSION > 1. For now with v1,
+    # a fresh graph (None) triggers migration. We test that _migrate_v1 runs.
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []  # No version = fresh
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    # Verify migration ran: indexes + constraints created
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    assert any("CREATE INDEX" in q for q in queries)
+    assert any("CREATE CONSTRAINT" in q for q in queries)
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_updates_version_after_migration():
+    """After running migrations, the SchemaVersion node should be
+    updated to the new expected version."""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    # Last query should be the MERGE to set version
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    assert "MERGE" in queries[-1]
+    assert "SchemaVersion" in queries[-1]
+
+
+# --- initialize_schema: error handling ---
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_raises_schema_error_on_failure():
+    """If a migration step fails (e.g., invalid Cypher), initialize_schema
+    should raise SchemaError."""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []
+
+    # Version check succeeds, first index creation fails
+    client.graph.query = AsyncMock(
+        side_effect=[version_result, Exception("Cypher syntax error")]
+    )
+
+    with pytest.raises(SchemaError, match="Schema migration failed"):
+        await initialize_schema(client)
+
+
+# --- index/constraint ordering ---
+
+
+@pytest.mark.anyio
+async def test_indexes_created_before_constraints():
+    """Unique constraints require a range index on the same property.
+    Verify that all CREATE INDEX queries are executed before any
+    CREATE CONSTRAINT queries."""
+    client = _make_client()
+    version_result = MagicMock()
+    version_result.result_set = []
+    ok_result = MagicMock()
+    ok_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+
+    await initialize_schema(client)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    # Find positions of index and constraint queries
+    index_positions = [i for i, q in enumerate(queries) if "CREATE INDEX" in q]
+    constraint_positions = [i for i, q in enumerate(queries) if "CREATE CONSTRAINT" in q]
+
+    assert len(index_positions) > 0
+    assert len(constraint_positions) > 0
+    assert max(index_positions) < min(constraint_positions), \
+        "All indexes must be created before any constraints"
