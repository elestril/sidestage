diff --git a/poetry.lock b/poetry.lock
index 8a7bb57..62c0614 100644
--- a/poetry.lock
+++ b/poetry.lock
@@ -208,6 +208,7 @@ files = [
 
 [package.dependencies]
 idna = ">=2.8"
+trio = {version = ">=0.32.0", optional = true, markers = "python_version >= \"3.10\" and extra == \"trio\""}
 typing_extensions = {version = ">=4.5", markers = "python_version < \"3.13\""}
 
 [package.extras]
@@ -244,7 +245,6 @@ description = "Foreign Function Interface for Python calling C code."
 optional = false
 python-versions = ">=3.9"
 groups = ["main", "dev"]
-markers = "platform_python_implementation != \"PyPy\""
 files = [
     {file = "cffi-2.0.0-cp310-cp310-macosx_10_13_x86_64.whl", hash = "sha256:0cf2d91ecc3fcc0625c2c530fe004f82c110405f101548512cce44322fa8ac44"},
     {file = "cffi-2.0.0-cp310-cp310-macosx_11_0_arm64.whl", hash = "sha256:f73b96c41e3b2adedc34a7356e64c8eb96e03a3782b535e043a986276ce12a49"},
@@ -331,6 +331,7 @@ files = [
     {file = "cffi-2.0.0-cp39-cp39-win_amd64.whl", hash = "sha256:b882b3df248017dba09d6b16defe9b5c407fe32fc7c65a9c69798e6175601be9"},
     {file = "cffi-2.0.0.tar.gz", hash = "sha256:44d1b5909021139fe36001ae048dbdde8214afa20200eda0f64c068cac5d5529"},
 ]
+markers = {main = "platform_python_implementation != \"PyPy\"", dev = "(platform_python_implementation != \"PyPy\" or os_name == \"nt\") and (platform_python_implementation != \"PyPy\" or implementation_name != \"pypy\")"}
 
 [package.dependencies]
 pycparser = {version = "*", markers = "implementation_name != \"PyPy\""}
@@ -570,6 +571,22 @@ files = [
     {file = "distro-1.9.0.tar.gz", hash = "sha256:2fa77c6fd8940f116ee1d6b94a2f90b13b5ea8d019b98bc8bafdcabcdd9bdbed"},
 ]
 
+[[package]]
+name = "falkordb"
+version = "1.4.0"
+description = "Python client for interacting with FalkorDB database"
+optional = false
+python-versions = "<4.0,>=3.10"
+groups = ["main"]
+files = [
+    {file = "falkordb-1.4.0-py3-none-any.whl", hash = "sha256:3ede67ebf096013e93f46f3365e9c4a68a5bc3e0116eec88d22540422d335601"},
+    {file = "falkordb-1.4.0.tar.gz", hash = "sha256:89b6bd02f0e0ce214852cc07c0be3fa44bb3a08daf39d343f790c7a92b50636f"},
+]
+
+[package.dependencies]
+python-dateutil = ">=2.9.0,<3.0.0"
+redis = ">=7.1.0,<8.0.0"
+
 [[package]]
 name = "fastapi"
 version = "0.128.0"
@@ -2114,6 +2131,21 @@ files = [
 opentelemetry-api = "1.39.1"
 typing-extensions = ">=4.5.0"
 
+[[package]]
+name = "outcome"
+version = "1.3.0.post0"
+description = "Capture the outcome of Python function calls."
+optional = false
+python-versions = ">=3.7"
+groups = ["dev"]
+files = [
+    {file = "outcome-1.3.0.post0-py2.py3-none-any.whl", hash = "sha256:e771c5ce06d1415e356078d3bdd68523f284b4ce5419828922b6871e65eda82b"},
+    {file = "outcome-1.3.0.post0.tar.gz", hash = "sha256:9dcf02e65f2971b80047b377468e72a268e15c0af3cf1238e6ff14f7f91143b8"},
+]
+
+[package.dependencies]
+attrs = ">=19.2.0"
+
 [[package]]
 name = "packaging"
 version = "26.0"
@@ -2347,11 +2379,11 @@ description = "C parser in Python"
 optional = false
 python-versions = ">=3.10"
 groups = ["main", "dev"]
-markers = "platform_python_implementation != \"PyPy\" and implementation_name != \"PyPy\""
 files = [
     {file = "pycparser-3.0-py3-none-any.whl", hash = "sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992"},
     {file = "pycparser-3.0.tar.gz", hash = "sha256:600f49d217304a5902ac3c37e1281c9fe94e4d0489de643a9504c5cdfdfc6b29"},
 ]
+markers = {main = "platform_python_implementation != \"PyPy\" and implementation_name != \"PyPy\"", dev = "(platform_python_implementation != \"PyPy\" or os_name == \"nt\") and (platform_python_implementation != \"PyPy\" or implementation_name != \"pypy\" and implementation_name != \"PyPy\") and implementation_name != \"PyPy\""}
 
 [[package]]
 name = "pydantic"
@@ -2627,6 +2659,22 @@ pygments = ">=2.7.2"
 [package.extras]
 dev = ["argcomplete", "attrs (>=19.2)", "hypothesis (>=3.56)", "mock", "requests", "setuptools", "xmlschema"]
 
+[[package]]
+name = "pytest-anyio"
+version = "0.0.0"
+description = "The pytest anyio plugin is built into anyio. You don't need this package."
+optional = false
+python-versions = "*"
+groups = ["dev"]
+files = [
+    {file = "pytest-anyio-0.0.0.tar.gz", hash = "sha256:b41234e9e9ad7ea1dbfefcc1d6891b23d5ef7c9f07ccf804c13a9cc338571fd3"},
+    {file = "pytest_anyio-0.0.0-py2.py3-none-any.whl", hash = "sha256:dc8b5c4741cb16ff90be37fddd585ca943ed12bbeb563de7ace6cd94441d8746"},
+]
+
+[package.dependencies]
+anyio = "*"
+pytest = "*"
+
 [[package]]
 name = "pytest-timeout"
 version = "2.4.0"
@@ -2642,6 +2690,21 @@ files = [
 [package.dependencies]
 pytest = ">=7.0.0"
 
+[[package]]
+name = "python-dateutil"
+version = "2.9.0.post0"
+description = "Extensions to the standard Python datetime module"
+optional = false
+python-versions = "!=3.0.*,!=3.1.*,!=3.2.*,>=2.7"
+groups = ["main"]
+files = [
+    {file = "python-dateutil-2.9.0.post0.tar.gz", hash = "sha256:37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3"},
+    {file = "python_dateutil-2.9.0.post0-py2.py3-none-any.whl", hash = "sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427"},
+]
+
+[package.dependencies]
+six = ">=1.5"
+
 [[package]]
 name = "python-dotenv"
 version = "1.2.1"
@@ -2783,6 +2846,24 @@ files = [
     {file = "pyyaml-6.0.3.tar.gz", hash = "sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"},
 ]
 
+[[package]]
+name = "redis"
+version = "7.1.0"
+description = "Python client for Redis database and key-value store"
+optional = false
+python-versions = ">=3.10"
+groups = ["main"]
+files = [
+    {file = "redis-7.1.0-py3-none-any.whl", hash = "sha256:23c52b208f92b56103e17c5d06bdc1a6c2c0b3106583985a76a18f83b265de2b"},
+    {file = "redis-7.1.0.tar.gz", hash = "sha256:b1cc3cfa5a2cb9c2ab3ba700864fb0ad75617b41f01352ce5779dabf6d5f9c3c"},
+]
+
+[package.extras]
+circuit-breaker = ["pybreaker (>=1.4.0)"]
+hiredis = ["hiredis (>=3.2.0)"]
+jwt = ["pyjwt (>=2.9.0)"]
+ocsp = ["cryptography (>=36.0.1)", "pyopenssl (>=20.0.1)", "requests (>=2.31.0)"]
+
 [[package]]
 name = "referencing"
 version = "0.37.0"
@@ -3115,6 +3196,18 @@ files = [
     {file = "shellingham-1.5.4.tar.gz", hash = "sha256:8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de"},
 ]
 
+[[package]]
+name = "six"
+version = "1.17.0"
+description = "Python 2 and 3 compatibility utilities"
+optional = false
+python-versions = "!=3.0.*,!=3.1.*,!=3.2.*,>=2.7"
+groups = ["main"]
+files = [
+    {file = "six-1.17.0-py2.py3-none-any.whl", hash = "sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"},
+    {file = "six-1.17.0.tar.gz", hash = "sha256:ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81"},
+]
+
 [[package]]
 name = "smmap"
 version = "5.0.2"
@@ -3133,12 +3226,24 @@ version = "1.3.1"
 description = "Sniff out which async library your code is running under"
 optional = false
 python-versions = ">=3.7"
-groups = ["main"]
+groups = ["main", "dev"]
 files = [
     {file = "sniffio-1.3.1-py3-none-any.whl", hash = "sha256:2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2"},
     {file = "sniffio-1.3.1.tar.gz", hash = "sha256:f4324edc670a0f49750a81b895f35c3adb843cca46f0530f79fc1babb23789dc"},
 ]
 
+[[package]]
+name = "sortedcontainers"
+version = "2.4.0"
+description = "Sorted Containers -- Sorted List, Sorted Dict, Sorted Set"
+optional = false
+python-versions = "*"
+groups = ["dev"]
+files = [
+    {file = "sortedcontainers-2.4.0-py2.py3-none-any.whl", hash = "sha256:a163dcaede0f1c021485e957a39245190e74249897e2ae4b2aa38595db237ee0"},
+    {file = "sortedcontainers-2.4.0.tar.gz", hash = "sha256:25caa5a06cc30b6b83d11423433f65d1f9d76c4c6a0c90e3379eaa43b9bfdb88"},
+]
+
 [[package]]
 name = "sqlalchemy"
 version = "2.0.46"
@@ -3416,6 +3521,26 @@ notebook = ["ipywidgets (>=6)"]
 slack = ["slack-sdk"]
 telegram = ["requests"]
 
+[[package]]
+name = "trio"
+version = "0.32.0"
+description = "A friendly Python library for async concurrency and I/O"
+optional = false
+python-versions = ">=3.10"
+groups = ["dev"]
+files = [
+    {file = "trio-0.32.0-py3-none-any.whl", hash = "sha256:4ab65984ef8370b79a76659ec87aa3a30c5c7c83ff250b4de88c29a8ab6123c5"},
+    {file = "trio-0.32.0.tar.gz", hash = "sha256:150f29ec923bcd51231e1d4c71c7006e65247d68759dd1c19af4ea815a25806b"},
+]
+
+[package.dependencies]
+attrs = ">=23.2.0"
+cffi = {version = ">=1.14", markers = "os_name == \"nt\" and implementation_name != \"pypy\""}
+idna = "*"
+outcome = "*"
+sniffio = ">=1.3.0"
+sortedcontainers = "*"
+
 [[package]]
 name = "typer-slim"
 version = "0.21.1"
@@ -3957,4 +4082,4 @@ type = ["pytest-mypy"]
 [metadata]
 lock-version = "2.1"
 python-versions = ">=3.12,<3.15"
-content-hash = "8604fd1238bb6733970e9156e6113cc8b3e6aa3306bb318b690972d93648db51"
+content-hash = "adb8acb50f627e0d657d9e6403eb830f3c8e75e11bf4ecbec01a90b49ce593f8"
diff --git a/pyproject.toml b/pyproject.toml
index d6f890e..08817fb 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -20,6 +20,7 @@ dependencies = [
     "sqlalchemy (>=2.0.46,<3.0.0)",
     "litellm (>=1.81.6,<2.0.0)",
     "httpx (>=0.28.1,<0.29.0)",
+    "falkordb (>=1.4.0,<2.0.0)",
 ]
 
 [project.scripts]
@@ -39,6 +40,8 @@ dev = [
     "httpx (>=0.28.1,<0.29.0)",
     "mcp-server-git (>=2026.1.14,<2027.0.0)",
     "pytest-timeout (>=2.4.0,<3.0.0)",
+    "anyio[trio] (>=4.9.0,<5.0.0)",
+    "pytest-anyio (>=0.0.0)",
 ]
 
 [tool.pytest.ini_options]
diff --git a/src/sidestage/graph/__init__.py b/src/sidestage/graph/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/src/sidestage/graph/client.py b/src/sidestage/graph/client.py
new file mode 100644
index 0000000..face0e9
--- /dev/null
+++ b/src/sidestage/graph/client.py
@@ -0,0 +1,87 @@
+"""FalkorDB connection management with pooling and lifecycle.
+
+Provides a thin async wrapper around falkordb.asyncio.FalkorDB that
+handles connection pooling, graph selection, and lifecycle management.
+"""
+
+import re
+from dataclasses import dataclass, field
+
+from falkordb.asyncio import FalkorDB
+from redis.asyncio import BlockingConnectionPool
+
+from sidestage.graph.errors import ConnectionError
+
+
+@dataclass
+class GraphConfig:
+    """FalkorDB connection configuration."""
+
+    host: str = "localhost"
+    port: int = 6379
+    password: str | None = None
+    max_connections: int = 16
+    graph_name: str | None = None
+
+
+class GraphClient:
+    """Holds live FalkorDB connection state.
+
+    Created by connect(), consumed by all graph operation functions,
+    cleaned up by close().
+    """
+
+    def __init__(self, pool, db, graph, graph_name: str):
+        self.pool = pool
+        self.db = db
+        self.graph = graph
+        self.graph_name = graph_name
+
+
+def sanitize_graph_name(name: str) -> str:
+    """Convert a campaign name into a valid graph name.
+
+    Lowercases, replaces spaces with underscores, strips non-alphanumeric
+    characters (except underscores). Falls back to 'default' if empty.
+    """
+    result = name.lower()
+    result = result.replace(" ", "_")
+    result = re.sub(r"[^a-z0-9_]", "", result)
+    return result if result else "default"
+
+
+async def connect(config: GraphConfig, campaign_name: str = "default") -> GraphClient:
+    """Create connection pool, select graph, run schema init.
+
+    Raises:
+        ConnectionError: If the FalkorDB server is unreachable.
+    """
+    graph_name = config.graph_name if config.graph_name else sanitize_graph_name(campaign_name)
+
+    try:
+        pool = BlockingConnectionPool(
+            host=config.host,
+            port=config.port,
+            password=config.password,
+            max_connections=config.max_connections,
+            decode_responses=True,
+        )
+        db = FalkorDB(connection_pool=pool)
+        graph = db.select_graph(graph_name)
+    except (OSError, Exception) as exc:
+        raise ConnectionError(
+            f"FalkorDB unreachable at {config.host}:{config.port}: {exc}"
+        ) from exc
+
+    # Placeholder for schema initialization (wired in section-02)
+    # await initialize_schema(client)
+
+    return GraphClient(pool=pool, db=db, graph=graph, graph_name=graph_name)
+
+
+async def close(client: GraphClient) -> None:
+    """Drain pool and close all connections.
+
+    Safe to call multiple times.
+    """
+    await client.pool.aclose()
diff --git a/src/sidestage/graph/errors.py b/src/sidestage/graph/errors.py
new file mode 100644
index 0000000..ba2b420
--- /dev/null
+++ b/src/sidestage/graph/errors.py
@@ -0,0 +1,25 @@
+"""Custom exception hierarchy for graph operations."""
+
+
+class GraphError(Exception):
+    """Base exception for all graph operations."""
+
+
+class ConnectionError(GraphError):
+    """FalkorDB server unreachable or connection pool exhausted."""
+
+
+class EntityNotFoundError(GraphError):
+    """Entity with given ID does not exist."""
+
+
+class DuplicateEntityError(GraphError):
+    """Entity with given ID already exists."""
+
+
+class SchemaError(GraphError):
+    """Schema initialization or migration failed."""
+
+
+class QueryError(GraphError):
+    """Cypher query execution failed."""
diff --git a/tests/unit/test_graph_client.py b/tests/unit/test_graph_client.py
new file mode 100644
index 0000000..85ed652
--- /dev/null
+++ b/tests/unit/test_graph_client.py
@@ -0,0 +1,185 @@
+"""Tests for FalkorDB connection management.
+
+Validates:
+- GraphConfig default values and custom overrides
+- connect() creates pool, selects graph, triggers schema init
+- connect() derives and sanitizes graph_name from campaign name
+- connect() raises ConnectionError when server is unreachable
+- close() drains the connection pool
+"""
+
+import pytest
+from unittest.mock import AsyncMock, MagicMock, patch
+from sidestage.graph.client import GraphClient, GraphConfig, connect, close, sanitize_graph_name
+from sidestage.graph.errors import ConnectionError
+
+
+# --- GraphConfig defaults ---
+
+
+def test_graph_config_defaults():
+    """GraphConfig has sensible defaults: localhost, 6379, no password, 16 connections, no graph_name."""
+    config = GraphConfig()
+    assert config.host == "localhost"
+    assert config.port == 6379
+    assert config.password is None
+    assert config.max_connections == 16
+    assert config.graph_name is None
+
+
+def test_graph_config_custom_values():
+    """GraphConfig accepts custom host, port, password, max_connections, graph_name."""
+    config = GraphConfig(
+        host="db.example.com",
+        port=6380,
+        password="secret",
+        max_connections=32,
+        graph_name="my_graph",
+    )
+    assert config.host == "db.example.com"
+    assert config.port == 6380
+    assert config.password == "secret"
+    assert config.max_connections == 32
+    assert config.graph_name == "my_graph"
+
+
+# --- sanitize_graph_name ---
+
+
+def test_sanitize_lowercases():
+    """Graph name is lowercased."""
+    assert sanitize_graph_name("MyGraph") == "mygraph"
+
+
+def test_sanitize_spaces_to_underscores():
+    """Spaces become underscores."""
+    assert sanitize_graph_name("My Campaign") == "my_campaign"
+
+
+def test_sanitize_strips_special_chars():
+    """Special characters are stripped."""
+    assert sanitize_graph_name("My Campaign! v2") == "my_campaign_v2"
+
+
+def test_sanitize_empty_becomes_default():
+    """Empty result falls back to 'default'."""
+    assert sanitize_graph_name("!!!") == "default"
+
+
+# --- connect() ---
+
+
+@pytest.mark.anyio
+async def test_connect_creates_connection_pool():
+    """connect() creates a BlockingConnectionPool with the configured max_connections."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
+         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
+        mock_pool = MagicMock()
+        mock_pool_cls.return_value = mock_pool
+        mock_db = MagicMock()
+        mock_db.select_graph.return_value = MagicMock()
+        mock_db_cls.return_value = mock_db
+
+        config = GraphConfig(max_connections=8, graph_name="test")
+        client = await connect(config)
+
+        mock_pool_cls.assert_called_once()
+        call_kwargs = mock_pool_cls.call_args[1]
+        assert call_kwargs["max_connections"] == 8
+        assert call_kwargs["decode_responses"] is True
+
+
+@pytest.mark.anyio
+async def test_connect_selects_graph_with_configured_name():
+    """connect() calls db.select_graph() with the graph_name from config."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
+         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
+        mock_pool_cls.return_value = MagicMock()
+        mock_db = MagicMock()
+        mock_graph = MagicMock()
+        mock_db.select_graph.return_value = mock_graph
+        mock_db_cls.return_value = mock_db
+
+        config = GraphConfig(graph_name="my_campaign")
+        client = await connect(config)
+
+        mock_db.select_graph.assert_called_once_with("my_campaign")
+        assert client.graph is mock_graph
+
+
+@pytest.mark.anyio
+async def test_connect_derives_graph_name_from_campaign_name():
+    """When graph_name is None, connect() derives it from campaign_name parameter."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
+         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
+        mock_pool_cls.return_value = MagicMock()
+        mock_db = MagicMock()
+        mock_db.select_graph.return_value = MagicMock()
+        mock_db_cls.return_value = mock_db
+
+        config = GraphConfig()  # graph_name is None
+        client = await connect(config, campaign_name="The Lost Mine")
+
+        mock_db.select_graph.assert_called_once_with("the_lost_mine")
+        assert client.graph_name == "the_lost_mine"
+
+
+@pytest.mark.anyio
+async def test_connect_sanitizes_campaign_name_for_graph_name():
+    """Derived graph_name is lowercased, spaces become underscores, special chars stripped."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
+         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
+        mock_pool_cls.return_value = MagicMock()
+        mock_db = MagicMock()
+        mock_db.select_graph.return_value = MagicMock()
+        mock_db_cls.return_value = mock_db
+
+        config = GraphConfig()
+        client = await connect(config, campaign_name="My Campaign! v2")
+
+        mock_db.select_graph.assert_called_once_with("my_campaign_v2")
+
+
+@pytest.mark.anyio
+async def test_connect_with_custom_host_port_password():
+    """connect() passes host, port, password to the connection pool."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
+         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
+        mock_pool_cls.return_value = MagicMock()
+        mock_db = MagicMock()
+        mock_db.select_graph.return_value = MagicMock()
+        mock_db_cls.return_value = mock_db
+
+        config = GraphConfig(host="db.example.com", port=6380, password="secret", graph_name="test")
+        await connect(config)
+
+        call_kwargs = mock_pool_cls.call_args[1]
+        assert call_kwargs["host"] == "db.example.com"
+        assert call_kwargs["port"] == 6380
+        assert call_kwargs["password"] == "secret"
+
+
+@pytest.mark.anyio
+async def test_connect_raises_connection_error_on_unreachable_host():
+    """connect() raises ConnectionError with a clear message when FalkorDB is unreachable."""
+    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls:
+        mock_pool_cls.side_effect = OSError("Connection refused")
+
+        config = GraphConfig(host="bad-host", port=9999, graph_name="test")
+        with pytest.raises(ConnectionError, match="bad-host:9999"):
+            await connect(config)
+
+
+# --- close() ---
+
+
+@pytest.mark.anyio
+async def test_close_closes_connection_pool():
+    """close() calls aclose() on the connection pool to drain all connections."""
+    mock_pool = AsyncMock()
+    client = GraphClient.__new__(GraphClient)
+    client.pool = mock_pool
+
+    await close(client)
+
+    mock_pool.aclose.assert_awaited_once()
diff --git a/tests/unit/test_graph_errors.py b/tests/unit/test_graph_errors.py
new file mode 100644
index 0000000..ee1e8e7
--- /dev/null
+++ b/tests/unit/test_graph_errors.py
@@ -0,0 +1,82 @@
+"""Tests for the graph error hierarchy.
+
+Validates that:
+- GraphError is the base for all graph exceptions
+- Each specific error is a proper subclass of GraphError
+- All error types carry a message string
+- Catching GraphError catches all specific subtypes
+"""
+
+import pytest
+from sidestage.graph.errors import (
+    GraphError,
+    ConnectionError,
+    EntityNotFoundError,
+    DuplicateEntityError,
+    SchemaError,
+    QueryError,
+)
+
+
+def test_graph_error_is_base_exception():
+    """GraphError inherits from Exception."""
+    assert issubclass(GraphError, Exception)
+
+
+def test_connection_error_is_subclass_of_graph_error():
+    """ConnectionError is a GraphError."""
+    assert issubclass(ConnectionError, GraphError)
+
+
+def test_entity_not_found_error_is_subclass_of_graph_error():
+    """EntityNotFoundError is a GraphError."""
+    assert issubclass(EntityNotFoundError, GraphError)
+
+
+def test_duplicate_entity_error_is_subclass_of_graph_error():
+    """DuplicateEntityError is a GraphError."""
+    assert issubclass(DuplicateEntityError, GraphError)
+
+
+def test_schema_error_is_subclass_of_graph_error():
+    """SchemaError is a GraphError."""
+    assert issubclass(SchemaError, GraphError)
+
+
+def test_query_error_is_subclass_of_graph_error():
+    """QueryError is a GraphError."""
+    assert issubclass(QueryError, GraphError)
+
+
+def test_all_errors_carry_message():
+    """Every error type can be instantiated with a descriptive message string."""
+    error_classes = [
+        GraphError,
+        ConnectionError,
+        EntityNotFoundError,
+        DuplicateEntityError,
+        SchemaError,
+        QueryError,
+    ]
+    for cls in error_classes:
+        msg = f"Test message for {cls.__name__}"
+        err = cls(msg)
+        assert str(err) == msg
+
+
+def test_catching_graph_error_catches_subtypes():
+    """A try/except on GraphError catches any specific subtype."""
+    with pytest.raises(GraphError):
+        raise EntityNotFoundError("missing entity")
+
+    with pytest.raises(GraphError):
+        raise ConnectionError("server down")
+
+    with pytest.raises(GraphError):
+        raise DuplicateEntityError("duplicate")
+
+    with pytest.raises(GraphError):
+        raise SchemaError("bad schema")
+
+    with pytest.raises(GraphError):
+        raise QueryError("bad query")
