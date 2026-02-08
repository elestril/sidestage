# `sidestage.graph.client`

FalkorDB connection management with pooling and lifecycle.

Provides a thin async wrapper around falkordb.asyncio.FalkorDB that
handles connection pooling, graph selection, and lifecycle management.

## Classes

### `GraphClient`

Holds live FalkorDB connection state.

Created by connect(), consumed by all graph operation functions,
cleaned up by close().

#### `__init__(pool: BlockingConnectionPool, db: FalkorDB, graph: Any, graph_name: str)`

### `GraphConfig`

FalkorDB connection configuration.

#### `__init__(host: str = 'localhost', port: int = 6379, password: str | None = None, max_connections: int = 16, graph_name: str | None = None, vector_dimension: int | None = None) -> None`

## Functions

### `close(client: GraphClient) -> None` *async*

Drain pool and close all connections.

Safe to call multiple times.

### `connect(config: GraphConfig, campaign_name: str = 'default') -> GraphClient` *async*

Create connection pool, select graph, run schema init.

Raises:
    ConnectionError: If the FalkorDB server is unreachable.

### `sanitize_graph_name(name: str) -> str`

Convert a campaign name into a valid graph name.

Lowercases, replaces spaces with underscores, strips non-alphanumeric
characters (except underscores). Falls back to 'default' if empty.
