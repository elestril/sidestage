"""FalkorDB connection management with pooling and lifecycle.

Provides a thin async wrapper around falkordb.asyncio.FalkorDB that
handles connection pooling, graph selection, and lifecycle management.
"""

import re
from dataclasses import dataclass

from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError

from sidestage.graph.errors import ConnectionError


@dataclass
class GraphConfig:
    """FalkorDB connection configuration."""

    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None


class GraphClient:
    """Holds live FalkorDB connection state.

    Created by connect(), consumed by all graph operation functions,
    cleaned up by close().
    """

    def __init__(self, pool, db, graph, graph_name: str):
        self.pool = pool
        self.db = db
        self.graph = graph
        self.graph_name = graph_name
        self._closed = False


def sanitize_graph_name(name: str) -> str:
    """Convert a campaign name into a valid graph name.

    Lowercases, replaces spaces with underscores, strips non-alphanumeric
    characters (except underscores). Falls back to 'default' if empty.
    """
    result = name.lower()
    result = result.replace(" ", "_")
    result = result.replace("-", "_")
    result = re.sub(r"[^a-z0-9_]", "", result)
    return result if result else "default"


async def connect(config: GraphConfig, campaign_name: str = "default") -> GraphClient:
    """Create connection pool, select graph, run schema init.

    Raises:
        ConnectionError: If the FalkorDB server is unreachable.
    """
    graph_name = config.graph_name if config.graph_name else sanitize_graph_name(campaign_name)

    try:
        pool = BlockingConnectionPool(
            host=config.host,
            port=config.port,
            password=config.password,
            max_connections=config.max_connections,
            decode_responses=True,
        )
        db = FalkorDB(connection_pool=pool)
        graph = db.select_graph(graph_name)
    except (OSError, RedisConnectionError) as exc:
        raise ConnectionError(
            f"FalkorDB unreachable at {config.host}:{config.port}: {exc}"
        ) from exc

    client = GraphClient(pool=pool, db=db, graph=graph, graph_name=graph_name)

    from sidestage.graph.schema import initialize_schema
    await initialize_schema(client)

    return client


async def close(client: GraphClient) -> None:
    """Drain pool and close all connections.

    Safe to call multiple times.
    """
    if client._closed:
        return
    await client.pool.aclose()
    client._closed = True
