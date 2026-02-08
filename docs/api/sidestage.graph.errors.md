# `sidestage.graph.errors`

Custom exception hierarchy for graph operations.

## Classes

### `ConnectionError(GraphError)`

FalkorDB server unreachable or connection pool exhausted.

#### `__init__(args, kwargs)`

### `DuplicateEntityError(GraphError)`

Entity with given ID already exists.

#### `__init__(args, kwargs)`

### `EntityNotFoundError(GraphError)`

Entity with given ID does not exist.

#### `__init__(args, kwargs)`

### `GraphError(Exception)`

Base exception for all graph operations.

#### `__init__(args, kwargs)`

### `QueryError(GraphError)`

Cypher query execution failed.

#### `__init__(args, kwargs)`

### `SchemaError(GraphError)`

Schema initialization or migration failed.

#### `__init__(args, kwargs)`
