# `sidestage.graph.schema`

Schema initialization and versioning for FalkorDB graph.

## Functions

### `get_schema_version(client: GraphClient) -> int | None` *async*

Query the graph for a :SchemaVersion node and return its version.

Returns None if no SchemaVersion node exists (fresh graph).

### `initialize_schema(client: GraphClient, vector_dimension: int | None = None) -> None` *async*

Initialize or migrate the graph schema.

1. Calls get_schema_version to check current state
2. If None (fresh graph): runs all migrations from v1 to CURRENT_VERSION
3. If version < CURRENT_VERSION: runs migrations for each version step
4. If version == CURRENT_VERSION: no-op (already up to date)
5. Creates or updates the :SchemaVersion node

Raises SchemaError if any migration step fails.
