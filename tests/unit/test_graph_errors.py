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
    assert issubclass(GraphError, Exception)


def test_connection_error_is_subclass_of_graph_error():
    """ConnectionError is a GraphError."""
    assert issubclass(ConnectionError, GraphError)


def test_entity_not_found_error_is_subclass_of_graph_error():
    """EntityNotFoundError is a GraphError."""
    assert issubclass(EntityNotFoundError, GraphError)


def test_duplicate_entity_error_is_subclass_of_graph_error():
    """DuplicateEntityError is a GraphError."""
    assert issubclass(DuplicateEntityError, GraphError)


def test_schema_error_is_subclass_of_graph_error():
    """SchemaError is a GraphError."""
    assert issubclass(SchemaError, GraphError)


def test_query_error_is_subclass_of_graph_error():
    """QueryError is a GraphError."""
    assert issubclass(QueryError, GraphError)


def test_all_errors_carry_message():
    """Every error type can be instantiated with a descriptive message string."""
    error_classes = [
        GraphError,
        ConnectionError,
        EntityNotFoundError,
        DuplicateEntityError,
        SchemaError,
        QueryError,
    ]
    for cls in error_classes:
        msg = f"Test message for {cls.__name__}"
        err = cls(msg)
        assert str(err) == msg


def test_catching_graph_error_catches_subtypes():
    """A try/except on GraphError catches any specific subtype."""
    with pytest.raises(GraphError):
        raise EntityNotFoundError("missing entity")

    with pytest.raises(GraphError):
        raise ConnectionError("server down")

    with pytest.raises(GraphError):
        raise DuplicateEntityError("duplicate")

    with pytest.raises(GraphError):
        raise SchemaError("bad schema")

    with pytest.raises(GraphError):
        raise QueryError("bad query")
