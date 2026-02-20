"""FalkorDB graph persistence layer for Sidestage.

Public API re-exports for the graph package. All consumers should import
from ``sidestage.graph`` rather than from submodules directly.
"""

from sidestage.graph.client import GraphClient, GraphConfig, connect, close
from sidestage.graph.entities import (
    create_entity,
    get_entity,
    update_entity,
    delete_entity,
    list_entities,
    find_entities,
)
from sidestage.graph.relationships import link, unlink, get_related, get_relationships
from sidestage.graph.queries import (
    characters_at_location,
    characters_in_scene,
    connected_locations,
    scene_events,
    entity_graph,
)
from sidestage.graph.errors import (
    GraphError,
    ConnectionError as GraphConnectionError,
    EntityNotFoundError,
    DuplicateEntityError,
    SchemaError,
    QueryError,
)

__all__ = [
    # Client
    "GraphClient",
    "GraphConfig",
    "connect",
    "close",
    # Entities
    "create_entity",
    "get_entity",
    "update_entity",
    "delete_entity",
    "list_entities",
    "find_entities",
    # Relationships
    "link",
    "unlink",
    "get_related",
    "get_relationships",
    # Queries
    "characters_at_location",
    "characters_in_scene",
    "connected_locations",
    "scene_events",
    "entity_graph",
    # Errors
    "GraphError",
    "GraphConnectionError",
    "EntityNotFoundError",
    "DuplicateEntityError",
    "SchemaError",
    "QueryError",
]
