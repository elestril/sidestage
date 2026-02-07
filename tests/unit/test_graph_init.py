"""Tests for graph package __init__.py public API."""
import pytest


def test_graph_exports_client():
    """graph package exports GraphClient and GraphConfig."""
    from sidestage.graph import GraphClient, GraphConfig
    assert GraphClient is not None
    assert GraphConfig is not None


def test_graph_exports_connect_close():
    """graph package exports connect and close."""
    from sidestage.graph import connect, close
    assert callable(connect)
    assert callable(close)


def test_graph_exports_entity_crud():
    """graph package exports entity CRUD functions."""
    from sidestage.graph import (
        create_entity,
        get_entity,
        update_entity,
        delete_entity,
        list_entities,
        find_entities,
    )
    assert callable(create_entity)
    assert callable(get_entity)
    assert callable(update_entity)
    assert callable(delete_entity)
    assert callable(list_entities)
    assert callable(find_entities)


def test_graph_exports_relationship_functions():
    """graph package exports relationship functions."""
    from sidestage.graph import link, unlink, get_related, get_relationships
    assert callable(link)
    assert callable(unlink)
    assert callable(get_related)
    assert callable(get_relationships)


def test_graph_exports_query_functions():
    """graph package exports query functions."""
    from sidestage.graph import (
        characters_at_location,
        connected_locations,
        scene_events,
        entity_graph,
    )
    assert callable(characters_at_location)
    assert callable(connected_locations)
    assert callable(scene_events)
    assert callable(entity_graph)


def test_graph_exports_error_types():
    """graph package exports all error types."""
    from sidestage.graph import (
        GraphError,
        GraphConnectionError,
        EntityNotFoundError,
        DuplicateEntityError,
        SchemaError,
        QueryError,
    )
    assert issubclass(GraphConnectionError, GraphError)
    assert issubclass(EntityNotFoundError, GraphError)
    assert issubclass(DuplicateEntityError, GraphError)
    assert issubclass(SchemaError, GraphError)
    assert issubclass(QueryError, GraphError)


def test_graph_all_matches_exports():
    """__all__ lists all public names."""
    import sidestage.graph as graph_mod
    for name in graph_mod.__all__:
        assert hasattr(graph_mod, name), f"{name} listed in __all__ but not importable"
