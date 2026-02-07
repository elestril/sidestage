diff --git a/planning/02-memory-and-embedding/implementation/deep_implement_config.json b/planning/02-memory-and-embedding/implementation/deep_implement_config.json
index 16905a5..6d6c005 100644
--- a/planning/02-memory-and-embedding/implementation/deep_implement_config.json
+++ b/planning/02-memory-and-embedding/implementation/deep_implement_config.json
@@ -16,7 +16,12 @@
     "section-07-agent-integration",
     "section-08-scene-integration"
   ],
-  "sections_state": {},
+  "sections_state": {
+    "section-01-models-and-health": {
+      "status": "complete",
+      "commit_hash": "e8e63d9"
+    }
+  },
   "pre_commit": {
     "present": false,
     "type": "none",
diff --git a/src/sidestage/graph/client.py b/src/sidestage/graph/client.py
index e782b46..123fc43 100644
--- a/src/sidestage/graph/client.py
+++ b/src/sidestage/graph/client.py
@@ -80,7 +80,7 @@ async def connect(config: GraphConfig, campaign_name: str = "default") -> GraphC
     client = GraphClient(pool=pool, db=db, graph=graph, graph_name=graph_name)
 
     from sidestage.graph.schema import initialize_schema
-    await initialize_schema(client)
+    await initialize_schema(client, vector_dimension=config.vector_dimension)
 
     return client
 
diff --git a/src/sidestage/graph/schema.py b/src/sidestage/graph/schema.py
index de9fea6..3ea4559 100644
--- a/src/sidestage/graph/schema.py
+++ b/src/sidestage/graph/schema.py
@@ -14,7 +14,7 @@ if TYPE_CHECKING:
 
 logger = logging.getLogger(__name__)
 
-CURRENT_VERSION = 1
+CURRENT_VERSION = 2
 
 INDEXES: list[tuple[str, str]] = [
     ("Entity", "id"),
@@ -29,6 +29,13 @@ CONSTRAINTS: list[tuple[str, str, str]] = [
     ("Entity", "name", "mandatory"),
 ]
 
+V2_INDEXES: list[tuple[str, str]] = [
+    ("Memory", "owner_id"),
+    ("Memory", "target_id"),
+    ("Memory", "memory_type"),
+    ("Memory", "visibility"),
+]
+
 
 async def get_schema_version(client: GraphClient) -> int | None:
     """Query the graph for a :SchemaVersion node and return its version.
@@ -41,7 +48,7 @@ async def get_schema_version(client: GraphClient) -> int | None:
     return result.result_set[0][0]
 
 
-async def initialize_schema(client: GraphClient) -> None:
+async def initialize_schema(client: GraphClient, vector_dimension: int | None = None) -> None:
     """Initialize or migrate the graph schema.
 
     1. Calls get_schema_version to check current state
@@ -72,13 +79,19 @@ async def initialize_schema(client: GraphClient) -> None:
         if migrate_fn is None:
             raise SchemaError(f"Schema migration failed: no migration for version {version}")
         try:
-            await migrate_fn(client)
+            if version == 2:
+                await migrate_fn(client, vector_dimension=vector_dimension)
+            else:
+                await migrate_fn(client)
         except SchemaError:
             raise
         except Exception as exc:
             raise SchemaError(f"Schema migration failed at version {version}: {exc}") from exc
 
-    await _set_schema_version(client, CURRENT_VERSION)
+    extra = {}
+    if vector_dimension is not None:
+        extra["vector_dimension"] = vector_dimension
+    await _set_schema_version(client, CURRENT_VERSION, **extra)
 
 
 async def _migrate_v1(client: GraphClient) -> None:
@@ -113,15 +126,49 @@ async def _migrate_v1(client: GraphClient) -> None:
             ) from exc
 
 
-async def _set_schema_version(client: GraphClient, version: int) -> None:
+async def _migrate_v2(client: GraphClient, vector_dimension: int | None = None) -> None:
+    """Memory schema migration: range indexes + optional vector index."""
+    for label, prop in V2_INDEXES:
+        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
+        logger.info("Creating index on %s.%s", label, prop)
+        try:
+            await client.graph.query(query)
+        except Exception as exc:
+            raise SchemaError(
+                f"Failed to create index on {label}.{prop}: {exc}"
+            ) from exc
+
+    if vector_dimension is not None:
+        if not isinstance(vector_dimension, int) or vector_dimension <= 0:
+            raise SchemaError(f"Invalid vector_dimension: {vector_dimension}")
+        query = (
+            f"CREATE VECTOR INDEX FOR (n:Memory) ON (n.embedding) "
+            f"OPTIONS {{dimension: {vector_dimension}, similarityFunction: 'cosine'}}"
+        )
+        logger.info("Creating vector index with dimension %d", vector_dimension)
+        try:
+            await client.graph.query(query)
+        except Exception as exc:
+            logger.warning("Vector index creation failed (non-fatal): %s", exc)
+
+
+async def _set_schema_version(client: GraphClient, version: int, **extra_props) -> None:
     """Create or update the :SchemaVersion node."""
     updated_at = datetime.now(timezone.utc).isoformat()
+    params = {"version": version, "updated_at": updated_at, **extra_props}
+
+    set_parts = ["v.version = $version", "v.updated_at = $updated_at"]
+    for key in extra_props:
+        set_parts.append(f"v.{key} = ${key}")
+
+    set_clause = ", ".join(set_parts)
     await client.graph.query(
-        "MERGE (v:SchemaVersion) SET v.version = $version, v.updated_at = $updated_at",
-        params={"version": version, "updated_at": updated_at},
+        f"MERGE (v:SchemaVersion) SET {set_clause}",
+        params=params,
     )
 
 
 MIGRATIONS: dict[int, Callable] = {
     1: _migrate_v1,
+    2: _migrate_v2,
 }
diff --git a/tests/unit/test_graph_schema.py b/tests/unit/test_graph_schema.py
index 91aaef1..c200a51 100644
--- a/tests/unit/test_graph_schema.py
+++ b/tests/unit/test_graph_schema.py
@@ -8,6 +8,7 @@ from sidestage.graph.schema import (
     CURRENT_VERSION,
     INDEXES,
     CONSTRAINTS,
+    V2_INDEXES,
     get_schema_version,
     initialize_schema,
 )
@@ -40,23 +41,25 @@ def _make_client(query_results=None):
     return client
 
 
+def _ok():
+    result = MagicMock()
+    result.result_set = []
+    return result
+
+
 # --- get_schema_version ---
 
 
 @pytest.mark.anyio
 async def test_get_schema_version_returns_none_for_fresh_graph():
-    """On a graph with no :SchemaVersion node, get_schema_version should
-    return None."""
-    client = _make_client(query_results=[[]])  # empty result set
+    client = _make_client(query_results=[[]])
     version = await get_schema_version(client)
     assert version is None
 
 
 @pytest.mark.anyio
 async def test_get_schema_version_returns_version_for_initialized_graph():
-    """On a graph with a :SchemaVersion node at version 1,
-    get_schema_version should return 1."""
-    client = _make_client(query_results=[[[1]]])  # result_set = [[1]]
+    client = _make_client(query_results=[[[1]]])
     version = await get_schema_version(client)
     assert version == 1
 
@@ -66,42 +69,29 @@ async def test_get_schema_version_returns_version_for_initialized_graph():
 
 @pytest.mark.anyio
 async def test_initialize_schema_creates_indexes_on_fresh_graph():
-    """On a fresh graph (no SchemaVersion node), initialize_schema should
-    create range indexes on: Entity.id, Entity.name, Event.gametime,
-    Scene.current_gametime."""
-    # First query: get_schema_version returns empty (no SchemaVersion node)
-    # Subsequent queries: index/constraint creation + version set (all succeed)
     client = _make_client()
-    # get_schema_version returns None (empty result set)
     version_result = MagicMock()
     version_result.result_set = []
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    # Many calls: 1 version check + 4 indexes + 3 constraints + 1 version set
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
     queries = [c.args[0] for c in client.graph.query.call_args_list]
-    index_queries = [q for q in queries if "CREATE INDEX" in q]
-    assert len(index_queries) == len(INDEXES)
+    v1_index_queries = [q for q in queries if "CREATE INDEX" in q and any(
+        f"(n:{label})" in q for label, _ in INDEXES
+    )]
+    assert len(v1_index_queries) == len(INDEXES)
     for label, prop in INDEXES:
         expected = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
-        assert expected in index_queries
+        assert expected in v1_index_queries
 
 
 @pytest.mark.anyio
 async def test_initialize_schema_creates_constraints_on_fresh_graph():
-    """On a fresh graph, initialize_schema should create:
-    - UNIQUE constraint on Entity.id
-    - MANDATORY (IS NOT NULL) constraint on Entity.id
-    - MANDATORY (IS NOT NULL) constraint on Entity.name"""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = []
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
@@ -116,14 +106,10 @@ async def test_initialize_schema_creates_constraints_on_fresh_graph():
 
 @pytest.mark.anyio
 async def test_initialize_schema_creates_schema_version_node():
-    """After initialization on a fresh graph, a :SchemaVersion node should
-    be created with MERGE and set to version 1."""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = []
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
@@ -131,13 +117,11 @@ async def test_initialize_schema_creates_schema_version_node():
     merge_queries = [q for q in queries if "MERGE" in q and "SchemaVersion" in q]
     assert len(merge_queries) == 1
 
-    # Check params were passed with version and updated_at
     merge_call = [c for c in client.graph.query.call_args_list if "MERGE" in c.args[0]][0]
     params = merge_call.kwargs.get("params") or (merge_call.args[1] if len(merge_call.args) > 1 else None)
     assert params is not None
     assert params["version"] == CURRENT_VERSION
     assert "updated_at" in params
-    # Verify updated_at is a valid ISO 8601 timestamp
     datetime.fromisoformat(params["updated_at"])
 
 
@@ -146,31 +130,24 @@ async def test_initialize_schema_creates_schema_version_node():
 
 @pytest.mark.anyio
 async def test_initialize_schema_idempotent():
-    """Calling initialize_schema twice should not raise errors."""
     client = _make_client()
     version_result_none = MagicMock()
     version_result_none.result_set = []
-    version_result_one = MagicMock()
-    version_result_one.result_set = [[1]]
-    ok_result = MagicMock()
-    ok_result.result_set = []
+    version_result_current = MagicMock()
+    version_result_current.result_set = [[CURRENT_VERSION]]
 
-    # First call: fresh graph (9 queries: 1 version + 4 idx + 3 con + 1 set)
-    # Second call: version already current (1 query: version check)
+    # First call: 1 version_check + 4 v1_idx + 3 v1_con + 4 v2_idx + 1 version_set = 13
+    # Second call: 1 version_check (returns CURRENT_VERSION -> no-op)
     client.graph.query = AsyncMock(
-        side_effect=[version_result_none] + [ok_result] * 8 + [version_result_one]
+        side_effect=[version_result_none] + [_ok()] * 12 + [version_result_current]
     )
 
     await initialize_schema(client)
     await initialize_schema(client)
-    # No error means success
 
 
 @pytest.mark.anyio
 async def test_initialize_schema_skips_when_version_current():
-    """When the graph already has a SchemaVersion node at the expected
-    version, initialize_schema should not execute index/constraint
-    creation queries."""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = [[CURRENT_VERSION]]
@@ -178,7 +155,6 @@ async def test_initialize_schema_skips_when_version_current():
 
     await initialize_schema(client)
 
-    # Only one query: the version check
     assert client.graph.query.await_count == 1
 
 
@@ -187,20 +163,13 @@ async def test_initialize_schema_skips_when_version_current():
 
 @pytest.mark.anyio
 async def test_initialize_schema_runs_migrations_when_behind():
-    """When the graph's SchemaVersion is behind the expected version,
-    initialize_schema should run migration functions."""
-    # This test only applies if CURRENT_VERSION > 1. For now with v1,
-    # a fresh graph (None) triggers migration. We test that _migrate_v1 runs.
     client = _make_client()
     version_result = MagicMock()
-    version_result.result_set = []  # No version = fresh
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    version_result.result_set = []
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
-    # Verify migration ran: indexes + constraints created
     queries = [c.args[0] for c in client.graph.query.call_args_list]
     assert any("CREATE INDEX" in q for q in queries)
     assert any("CREATE CONSTRAINT" in q for q in queries)
@@ -208,18 +177,13 @@ async def test_initialize_schema_runs_migrations_when_behind():
 
 @pytest.mark.anyio
 async def test_initialize_schema_updates_version_after_migration():
-    """After running migrations, the SchemaVersion node should be
-    updated to the new expected version."""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = []
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
-    # Last query should be the MERGE to set version
     queries = [c.args[0] for c in client.graph.query.call_args_list]
     assert "MERGE" in queries[-1]
     assert "SchemaVersion" in queries[-1]
@@ -230,13 +194,10 @@ async def test_initialize_schema_updates_version_after_migration():
 
 @pytest.mark.anyio
 async def test_initialize_schema_raises_schema_error_on_failure():
-    """If a migration step fails (e.g., invalid Cypher), initialize_schema
-    should raise SchemaError."""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = []
 
-    # Version check succeeds, first index creation fails
     client.graph.query = AsyncMock(
         side_effect=[version_result, Exception("Cypher syntax error")]
     )
@@ -250,24 +211,20 @@ async def test_initialize_schema_raises_schema_error_on_failure():
 
 @pytest.mark.anyio
 async def test_indexes_created_before_constraints():
-    """Unique constraints require a range index on the same property.
-    Verify that all CREATE INDEX queries are executed before any
-    CREATE CONSTRAINT queries."""
     client = _make_client()
     version_result = MagicMock()
     version_result.result_set = []
-    ok_result = MagicMock()
-    ok_result.result_set = []
-    client.graph.query = AsyncMock(side_effect=[version_result] + [ok_result] * 8)
+    client.graph.query = AsyncMock(side_effect=[version_result] + [_ok()] * 20)
 
     await initialize_schema(client)
 
     queries = [c.args[0] for c in client.graph.query.call_args_list]
-    # Find positions of index and constraint queries
-    index_positions = [i for i, q in enumerate(queries) if "CREATE INDEX" in q]
+    v1_index_positions = [i for i, q in enumerate(queries) if "CREATE INDEX" in q and any(
+        f"(n:{label})" in q for label, _ in INDEXES
+    )]
     constraint_positions = [i for i, q in enumerate(queries) if "CREATE CONSTRAINT" in q]
 
-    assert len(index_positions) > 0
+    assert len(v1_index_positions) > 0
     assert len(constraint_positions) > 0
-    assert max(index_positions) < min(constraint_positions), \
-        "All indexes must be created before any constraints"
+    assert max(v1_index_positions) < min(constraint_positions), \
+        "All v1 indexes must be created before any constraints"
diff --git a/tests/unit/test_schema_v2.py b/tests/unit/test_schema_v2.py
new file mode 100644
index 0000000..5c45d8f
--- /dev/null
+++ b/tests/unit/test_schema_v2.py
@@ -0,0 +1,175 @@
+"""Tests for schema v2 migration: Memory indexes and vector index."""
+
+import pytest
+from unittest.mock import AsyncMock, MagicMock
+
+from sidestage.graph.schema import (
+    CURRENT_VERSION,
+    initialize_schema,
+)
+from sidestage.graph.errors import SchemaError
+
+
+def _make_client(query_side_effects):
+    """Create a mock GraphClient with a sequence of query results."""
+    client = MagicMock()
+    mock_graph = MagicMock()
+    mock_graph.query = AsyncMock(side_effect=query_side_effects)
+    client.graph = mock_graph
+    return client
+
+
+def _ok():
+    """Return a MagicMock representing a successful empty query result."""
+    result = MagicMock()
+    result.result_set = []
+    return result
+
+
+def _version_result(version):
+    """Return a MagicMock representing a SchemaVersion query result."""
+    result = MagicMock()
+    result.result_set = [[version]]
+    return result
+
+
+# --- CURRENT_VERSION ---
+
+def test_current_version_is_2():
+    assert CURRENT_VERSION == 2
+
+
+# --- initialize_schema with vector_dimension ---
+
+@pytest.mark.anyio
+async def test_initialize_schema_with_vector_dimension_creates_vector_index():
+    """When vector_dimension is provided and migrating from v1 to v2,
+    the migration should create a vector index on Memory.embedding."""
+    effects = [_version_result(1)] + [_ok()] * 10
+    client = _make_client(effects)
+
+    await initialize_schema(client, vector_dimension=384)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    vector_queries = [q for q in queries if "VECTOR" in q.upper()]
+    assert len(vector_queries) >= 1, "Expected at least one VECTOR INDEX creation query"
+    vector_q = vector_queries[0]
+    assert "384" in vector_q, "Vector dimension 384 should appear in the query"
+
+
+@pytest.mark.anyio
+async def test_initialize_schema_without_vector_dimension_skips_vector_index():
+    """When vector_dimension is None, the v2 migration should NOT create
+    a vector index but should still create range indexes."""
+    effects = [_version_result(1)] + [_ok()] * 10
+    client = _make_client(effects)
+
+    await initialize_schema(client, vector_dimension=None)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    vector_queries = [q for q in queries if "VECTOR" in q.upper()]
+    assert len(vector_queries) == 0, "No vector index should be created when vector_dimension is None"
+
+
+# --- Range indexes ---
+
+@pytest.mark.anyio
+async def test_v2_migration_creates_range_indexes():
+    """v2 migration should create range indexes on Memory.owner_id,
+    Memory.target_id, Memory.memory_type, and Memory.visibility."""
+    effects = [_version_result(1)] + [_ok()] * 10
+    client = _make_client(effects)
+
+    await initialize_schema(client, vector_dimension=None)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+    index_queries = [q for q in queries if "CREATE INDEX" in q and "Memory" in q]
+
+    expected_props = {"owner_id", "target_id", "memory_type", "visibility"}
+    found_props = set()
+    for q in index_queries:
+        for prop in expected_props:
+            if prop in q:
+                found_props.add(prop)
+
+    assert found_props == expected_props, \
+        f"Expected range indexes on {expected_props}, found on {found_props}"
+
+
+# --- Dimension stored on SchemaVersion ---
+
+@pytest.mark.anyio
+async def test_v2_migration_stores_dimension_on_schema_version():
+    """After v2 migration with a vector_dimension, the dimension should be
+    stored as a property on the SchemaVersion node."""
+    effects = [_version_result(1)] + [_ok()] * 10
+    client = _make_client(effects)
+
+    await initialize_schema(client, vector_dimension=768)
+
+    merge_calls = [
+        c for c in client.graph.query.call_args_list
+        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
+    ]
+    assert len(merge_calls) >= 1
+    last_merge = merge_calls[-1]
+    params = last_merge.kwargs.get("params", {})
+    assert params.get("vector_dimension") == 768, \
+        "vector_dimension should be stored in SchemaVersion params"
+
+
+# --- Version bump ---
+
+@pytest.mark.anyio
+async def test_schema_version_bumps_from_1_to_2():
+    """When graph is at version 1, initialize_schema should run v2 migration
+    and set version to 2."""
+    effects = [_version_result(1)] + [_ok()] * 10
+    client = _make_client(effects)
+
+    await initialize_schema(client)
+
+    merge_calls = [
+        c for c in client.graph.query.call_args_list
+        if "MERGE" in c.args[0] and "SchemaVersion" in c.args[0]
+    ]
+    assert len(merge_calls) >= 1
+    params = merge_calls[-1].kwargs.get("params", {})
+    assert params.get("version") == 2
+
+
+# --- No-op when already at v2 ---
+
+@pytest.mark.anyio
+async def test_initialize_schema_noop_when_already_at_v2():
+    """When graph is already at version 2, initialize_schema should be a no-op."""
+    effects = [_version_result(2)]
+    client = _make_client(effects)
+
+    await initialize_schema(client)
+
+    assert client.graph.query.await_count == 1, \
+        "Only the version check query should run"
+
+
+# --- Fresh graph runs both v1 and v2 ---
+
+@pytest.mark.anyio
+async def test_fresh_graph_runs_v1_and_v2_migrations():
+    """A fresh graph (no SchemaVersion) should run both v1 and v2 migrations."""
+    effects = [_ok()] * 20
+    client = _make_client(effects)
+
+    await initialize_schema(client)
+
+    queries = [c.args[0] for c in client.graph.query.call_args_list]
+
+    # v1 artifacts: Entity indexes and constraints
+    assert any("CREATE INDEX" in q and "Entity" in q for q in queries), \
+        "v1 migration should create Entity indexes"
+    assert any("CREATE CONSTRAINT" in q for q in queries), \
+        "v1 migration should create Entity constraints"
+
+    # v2 artifacts: Memory range indexes
+    assert any("CREATE INDEX" in q and "Memory" in q for q in queries), \
+        "v2 migration should create Memory indexes"
