Now I have all the context needed. Let me generate the section content.

# Section 01: Custom Errors and FalkorDB Client

## Overview

This section implements the foundation layer for the FalkorDB graph database integration. It covers two files that have no dependencies on other graph modules and are required by every subsequent section:

1. **`src/sidestage/graph/errors.py`** -- Custom exception hierarchy for all graph operations
2. **`src/sidestage/graph/client.py`** -- Async FalkorDB connection management with pooling and lifecycle
3. **`src/sidestage/graph/__init__.py`** -- Initial package file (empty for now, populated in section-06)

These modules are the first step in building the `src/sidestage/graph/` package. All subsequent graph modules (schema, entities, relationships, queries) import from these two files.

---

## Background Context

### Project Architecture

Sidestage is a multi-agent RPG assistant using Python 3.12+, FastAPI, and async event-driven architecture. Entity data (characters, locations, items, scenes, events) is currently stored in SQLite as JSON blobs via a `Storage` class in `src/sidestage/storage.py`. This plan introduces FalkorDB as a graph database backend for entity storage.

### FalkorDB Async Client

FalkorDB provides native async support via `falkordb.asyncio`:

```python
from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

pool = BlockingConnectionPool(max_connections=16, timeout=None, decode_responses=True)
db = FalkorDB(connection_pool=pool)
graph = db.select_graph("my_campaign")
result = await graph.query("MATCH (n) RETURN n LIMIT 1")
await pool.aclose()
```

The `falkordb` package depends on `redis[hiredis]`, which provides `redis.asyncio.BlockingConnectionPool`. No additional Redis package is needed.

### Testing Framework

The project uses pytest with `pytest-anyio` for async tests. Async test functions use the `@pytest.mark.anyio` decorator. Mocking uses `unittest.mock` (AsyncMock, MagicMock, patch). Unit test files live in `tests/unit/`.

---

## File Listing

| File | Action |
|------|--------|
| `src/sidestage/graph/__init__.py` | Create (empty) |
| `src/sidestage/graph/errors.py` | Create |
| `src/sidestage/graph/client.py` | Create |
| `tests/unit/test_graph_errors.py` | Create |
| `tests/unit/test_graph_client.py` | Create |
| `pyproject.toml` | Modify (add `falkordb` and `pytest-anyio` dependencies) |

---

## Dependencies

### New Package Dependencies

Add to `pyproject.toml` under `[project] dependencies`:

```
"falkordb (>=1.4.0,<2.0.0)"
```

Add to `pyproject.toml` under `[dependency-groups] dev`:

```
"anyio[trio] (>=4.9.0,<5.0.0)",
"pytest-anyio (>=0.0.0)",
```

Note: `pytest-anyio` may already be transitively available since `tests/unit/test_agent_loop.py` uses `@pytest.mark.anyio`, but it should be explicitly listed.

### Section Dependencies

This section has no dependencies on other sections. It is the foundation that sections 02 through 06 build upon.

---

## Tests FIRST

### Test File: `tests/unit/test_graph_errors.py`

This file validates the exception hierarchy. All exceptions descend from `GraphError`, which itself descends from `Exception`. Each error class must be instantiable with a message string and must be catchable as its parent type.

```python
"""Tests for the graph error hierarchy.

Validates that:
- GraphError is the base for all graph exceptions
- Each specific error is a proper subclass of GraphError
- All error types carry a message string
- Catching GraphError catches all specific subtypes
"""

import pytest
from sidestage.graph.errors import (
    GraphError,
    ConnectionError,
    EntityNotFoundError,
    DuplicateEntityError,
    SchemaError,
    QueryError,
)


def test_graph_error_is_base_exception():
    """GraphError inherits from Exception."""

def test_connection_error_is_subclass_of_graph_error():
    """ConnectionError is a GraphError."""

def test_entity_not_found_error_is_subclass_of_graph_error():
    """EntityNotFoundError is a GraphError."""

def test_duplicate_entity_error_is_subclass_of_graph_error():
    """DuplicateEntityError is a GraphError."""

def test_schema_error_is_subclass_of_graph_error():
    """SchemaError is a GraphError."""

def test_query_error_is_subclass_of_graph_error():
    """QueryError is a GraphError."""

def test_all_errors_carry_message():
    """Every error type can be instantiated with a descriptive message string."""

def test_catching_graph_error_catches_subtypes():
    """A try/except on GraphError catches any specific subtype (e.g., EntityNotFoundError)."""
```

Each test is a simple assertion on `issubclass`, `isinstance`, or `str(err)`. Implementation is straightforward.

### Test File: `tests/unit/test_graph_client.py`

This file validates the `GraphClient` wrapper, `GraphConfig` dataclass, and the `connect()`/`close()` lifecycle functions. Because these tests are unit tests, they mock the FalkorDB and Redis connection pool to avoid requiring a running FalkorDB server.

```python
"""Tests for FalkorDB connection management.

Validates:
- GraphConfig default values and custom overrides
- connect() creates pool, selects graph, triggers schema init
- connect() derives and sanitizes graph_name from campaign name
- connect() raises ConnectionError when server is unreachable
- close() drains the connection pool
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sidestage.graph.client import GraphClient, GraphConfig, connect, close
from sidestage.graph.errors import ConnectionError


# --- GraphConfig defaults ---

def test_graph_config_defaults():
    """GraphConfig has sensible defaults: localhost, 6379, no password, 16 connections, no graph_name."""

def test_graph_config_custom_values():
    """GraphConfig accepts custom host, port, password, max_connections, graph_name."""


# --- connect() ---

@pytest.mark.anyio
async def test_connect_creates_connection_pool():
    """connect() creates a BlockingConnectionPool with the configured max_connections."""

@pytest.mark.anyio
async def test_connect_selects_graph_with_configured_name():
    """connect() calls db.select_graph() with the graph_name from config."""

@pytest.mark.anyio
async def test_connect_derives_graph_name_from_campaign_name():
    """When graph_name is None, connect() derives it from campaign_name parameter."""

@pytest.mark.anyio
async def test_connect_sanitizes_campaign_name_for_graph_name():
    """Derived graph_name is lowercased, spaces become underscores, special chars stripped."""

@pytest.mark.anyio
async def test_connect_calls_schema_initialization():
    """After establishing connection, connect() calls schema initialization."""

@pytest.mark.anyio
async def test_connect_with_custom_host_port_password():
    """connect() passes host, port, password to the connection pool."""

@pytest.mark.anyio
async def test_connect_raises_connection_error_on_unreachable_host():
    """connect() raises ConnectionError with a clear message when FalkorDB is unreachable."""


# --- close() ---

@pytest.mark.anyio
async def test_close_closes_connection_pool():
    """close() calls aclose() on the connection pool to drain all connections."""
```

---

## Implementation Details

### File: `src/sidestage/graph/__init__.py`

Create as an empty file. This establishes the `sidestage.graph` package. Public API re-exports will be added in section-06.

### File: `src/sidestage/graph/errors.py`

Define a custom exception hierarchy with a single base class and five specific subclasses. The design follows fail-fast semantics: all graph operations raise immediately on error with no retry logic, no graceful degradation, and no fallback to SQLite.

```python
"""Custom exception hierarchy for graph operations.

All graph-related errors inherit from GraphError, enabling callers to
catch broad (GraphError) or narrow (EntityNotFoundError) as needed.

Design principles:
- Fail fast: no retries, no fallback
- Clear messages: wrap raw Redis/FalkorDB errors with context
- Catchable hierarchy: isinstance checks work naturally
"""

class GraphError(Exception):
    """Base exception for all graph operations."""

class ConnectionError(GraphError):
    """FalkorDB server unreachable or connection pool exhausted.

    Raised when the connection pool cannot be created or a connection
    cannot be acquired. The message should include host:port details.
    """

class EntityNotFoundError(GraphError):
    """Entity with given ID does not exist.

    Raised by get, update, delete operations when the target entity
    cannot be found in the graph.
    """

class DuplicateEntityError(GraphError):
    """Entity with given ID already exists (unique constraint violation).

    Raised by create operations when the entity ID collides with
    an existing node's ID.
    """

class SchemaError(GraphError):
    """Schema initialization or migration failed.

    Raised during startup if indexes, constraints, or version
    tracking cannot be established.
    """

class QueryError(GraphError):
    """Cypher query execution failed.

    Raised when a Cypher query returns an error from FalkorDB.
    The message should include the query text (or a summary) and
    the underlying error.
    """
```

Note on naming: `ConnectionError` shadows the Python built-in `ConnectionError`. This is intentional for clean API ergonomics within the graph package (callers import `from sidestage.graph.errors import ConnectionError`). If this causes issues, the alternative is `GraphConnectionError`, but the plan specifies `ConnectionError`.

### File: `src/sidestage/graph/client.py`

This module provides a thin async wrapper around `falkordb.asyncio.FalkorDB` that handles connection pooling, graph selection, and lifecycle management.

#### GraphConfig

A Pydantic `BaseModel` (or dataclass) holding connection configuration:

```python
class GraphConfig(BaseModel):
    """FalkorDB connection configuration.

    Attributes:
        host: FalkorDB server hostname (default: localhost)
        port: FalkorDB server port (default: 6379, Redis-compatible)
        password: Optional authentication password
        max_connections: Connection pool size (default: 16)
        graph_name: Explicit graph name. If None, derived from campaign name.
    """
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None
```

#### GraphClient

A container holding the live connection objects. This is not a class with methods; it is a data holder that is passed to all graph operation functions.

```python
class GraphClient:
    """Holds live FalkorDB connection state.

    Created by connect(), consumed by all graph operation functions,
    cleaned up by close().

    Attributes:
        pool: The redis.asyncio BlockingConnectionPool
        db: The FalkorDB async client instance
        graph: The selected Graph object for this campaign
        graph_name: The name of the selected graph
    """
```

The `GraphClient` stores four attributes:
- `pool` -- `redis.asyncio.BlockingConnectionPool` instance
- `db` -- `falkordb.asyncio.FalkorDB` instance
- `graph` -- `falkordb.asyncio.Graph` instance (result of `db.select_graph()`)
- `graph_name` -- `str`, the resolved graph name

#### connect()

```python
async def connect(config: GraphConfig, campaign_name: str = "default") -> GraphClient:
    """Create connection pool, select graph, run schema init.

    1. Resolve graph_name: use config.graph_name if set, otherwise
       derive from campaign_name via sanitize_graph_name().
    2. Create BlockingConnectionPool with host, port, password, max_connections.
       Set decode_responses=True.
    3. Create FalkorDB instance with the pool.
    4. Select the graph via db.select_graph(graph_name).
    5. Call schema initialization (from schema module, section-02).
       For now, this call can be a no-op placeholder that will be
       wired up when section-02 is implemented.
    6. Return a GraphClient instance.

    Raises:
        ConnectionError: If the FalkorDB server is unreachable or the
            pool cannot be created. The message includes host:port.
    """
```

#### sanitize_graph_name()

A helper function that converts a campaign name into a valid graph name:
- Lowercase the string
- Replace spaces with underscores
- Strip any characters that are not alphanumeric or underscores
- If the result is empty, use "default"

Example: `"My Campaign! v2"` becomes `"my_campaign_v2"`.

#### close()

```python
async def close(client: GraphClient) -> None:
    """Drain pool and close all connections.

    Calls await client.pool.aclose() to cleanly shut down.
    Safe to call multiple times.
    """
```

#### Error Wrapping

The `connect()` function wraps any `redis.exceptions.ConnectionError` or `OSError` from the pool/FalkorDB client into `sidestage.graph.errors.ConnectionError` with a message like `"FalkorDB unreachable at {host}:{port}: {original_error}"`.

#### Schema Initialization Hook

The `connect()` function should accept an optional `schema_init` callable (or import it conditionally). For this section, use a placeholder approach:

```python
# Placeholder for schema initialization (wired in section-02)
# After pool and graph are ready:
# await initialize_schema(client)
```

This allows section-01 to be completed and tested independently. Section-02 will wire in the real schema initialization.

---

## Implementation Checklist

1. Create directory `src/sidestage/graph/`
2. Create empty `src/sidestage/graph/__init__.py`
3. Write `tests/unit/test_graph_errors.py` (all tests)
4. Implement `src/sidestage/graph/errors.py` (all exception classes)
5. Run error tests, confirm green
6. Write `tests/unit/test_graph_client.py` (all tests, mocking FalkorDB/Redis)
7. Implement `src/sidestage/graph/client.py` (GraphConfig, GraphClient, connect, close, sanitize_graph_name)
8. Run client tests, confirm green
9. Update `pyproject.toml` to add `falkordb` dependency and `pytest-anyio` dev dependency
10. Run full test suite to confirm no regressions

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ConnectionError naming | Shadows built-in | Clean import ergonomics within graph package; always used qualified |
| GraphClient as data holder | Not a class with methods | Functional API style; client is passed to free functions |
| Schema init as placeholder | No-op in section-01 | Enables independent implementation and testing |
| Fail-fast errors | No retries or fallback | Campaign depends on graph DB being available |
| Pool type | BlockingConnectionPool | Blocks until connection available rather than erroring under load |
| decode_responses | True | Auto-decode Redis responses; avoids bytes everywhere |