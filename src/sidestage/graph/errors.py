"""Custom exception hierarchy for graph operations."""


class GraphError(Exception):
    """Base exception for all graph operations."""


class ConnectionError(GraphError):
    """FalkorDB server unreachable or connection pool exhausted."""


class EntityNotFoundError(GraphError):
    """Entity with given ID does not exist."""


class DuplicateEntityError(GraphError):
    """Entity with given ID already exists."""


class SchemaError(GraphError):
    """Schema initialization or migration failed."""


class QueryError(GraphError):
    """Cypher query execution failed."""
