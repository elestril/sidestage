"""Entity CRUD operations and serialization logic for FalkorDB graph nodes.

Provides async functions for creating, retrieving, updating, deleting,
listing, and querying entity nodes. Maps between Pydantic entity models
and FalkorDB graph node properties.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TYPE_CHECKING

from sidestage.graph.errors import DuplicateEntityError, EntityNotFoundError, QueryError
from sidestage.models import (
    EntityModel,
    CharacterModel,
    ChatMessageModel,
    EventModel,
    FastForwardEventModel,
    ItemModel,
    JoinEventModel,
    LeaveEventModel,
    LocationModel,
    SceneModel,
)

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

# --- Label/Model Registries ---

# Ordered most-specific first so deserialization picks the right model.
LABEL_TO_MODEL: dict[str, type[EntityModel]] = {
    "ChatMessage": ChatMessageModel,
    "JoinEvent": JoinEventModel,
    "LeaveEvent": LeaveEventModel,
    "FastForwardEvent": FastForwardEventModel,
    "Character": CharacterModel,
    "Location": LocationModel,
    "Item": ItemModel,
    "Scene": SceneModel,
    "Event": EventModel,
}

MODEL_TO_LABELS: dict[type[EntityModel], list[str]] = {
    CharacterModel: ["Entity", "Character"],
    LocationModel: ["Entity", "Location"],
    ItemModel: ["Entity", "Item"],
    SceneModel: ["Entity", "Scene"],
    EventModel: ["Entity", "Event"],
    ChatMessageModel: ["Entity", "Event", "ChatMessage"],
    JoinEventModel: ["Entity", "Event", "JoinEvent"],
    LeaveEventModel: ["Entity", "Event", "LeaveEvent"],
    FastForwardEventModel: ["Entity", "Event", "FastForwardEvent"],
}

# Fields that should NOT be stored as graph node properties.
EXCLUDED_FIELDS: dict[type[EntityModel], set[str]] = {
    LocationModel: {"connected_locations"},
    SceneModel: {"messages"},
    ChatMessageModel: {"widget"},
}

# Valid property key pattern for Cypher safety.
_VALID_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$", re.IGNORECASE)

# All known Entity field names (union across all model types).
_ALL_ENTITY_FIELDS: set[str] = set()
for _model_cls in MODEL_TO_LABELS:
    _ALL_ENTITY_FIELDS.update(_model_cls.model_fields.keys())


def _validate_property_keys(keys: dict[str, Any] | set[str]) -> None:
    """Validate that property keys are known Entity field names.

    Raises QueryError if any key is not a recognized field name.
    """
    key_set = keys if isinstance(keys, set) else set(keys)
    invalid = key_set - _ALL_ENTITY_FIELDS
    if invalid:
        raise QueryError(f"Unknown property keys: {invalid}")
    for k in key_set:
        if not _VALID_KEY_RE.match(k):
            raise QueryError(f"Invalid property key format: {k!r}")


# --- Serialization Helpers ---


def entity_to_labels(entity: EntityModel) -> list[str]:
    """Return the FalkorDB labels for an entity instance."""
    return MODEL_TO_LABELS.get(type(entity), ["Entity"])


def entity_to_properties(entity: EntityModel) -> dict[str, Any]:
    """Convert a Pydantic entity to a dict of graph node properties.

    Excludes fields listed in EXCLUDED_FIELDS for the entity type,
    and omits None values.
    """
    excluded = EXCLUDED_FIELDS.get(type(entity), set())
    props = {}
    for key, value in entity.model_dump().items():
        if key in excluded:
            continue
        if value is None:
            continue
        props[key] = value
    return props


def node_to_entity(labels: list[str], properties: dict[str, Any]) -> EntityModel:
    """Reconstruct a Pydantic entity from graph node labels and properties.

    Iterates LABEL_TO_MODEL in specificity order (most-specific first)
    and picks the first matching label.

    Raises QueryError if no matching label is found.
    """
    label_set = set(labels)
    for label, model_cls in LABEL_TO_MODEL.items():
        if label in label_set:
            return model_cls(**properties)
    raise QueryError(f"Cannot deserialize node with labels {labels}: no matching model")


# --- CRUD Functions ---


async def create_entity(client: GraphClient, entity: EntityModel) -> EntityModel:
    """Create a new entity node in the graph.

    Raises DuplicateEntityError on unique constraint violation.
    Raises QueryError on other failures.
    """
    labels = entity_to_labels(entity)
    props = entity_to_properties(entity)

    label_str = ":".join(labels)
    prop_assignments = ", ".join(f"{k}: ${k}" for k in props)
    cypher = f"CREATE (n:{label_str} {{{prop_assignments}}}) RETURN n"

    logger.info("Creating %s entity id=%s", labels[-1], entity.id)
    logger.debug("Cypher: %s", cypher)

    try:
        await client.graph.query(cypher, params=props)
    except Exception as exc:
        exc_msg = str(exc).lower()
        if "unique" in exc_msg or "already exists" in exc_msg or "constraint" in exc_msg:
            raise DuplicateEntityError(
                f"Entity with id '{entity.id}' already exists: {exc}"
            ) from exc
        raise QueryError(f"Failed to create entity '{entity.id}': {exc}") from exc

    return entity


async def get_entity(client: GraphClient, entity_id: str) -> EntityModel | None:
    """Retrieve an entity by ID, or None if not found."""
    cypher = "MATCH (n:Entity {id: $id}) RETURN n"

    logger.debug("Getting entity id=%s", entity_id)

    try:
        result = await client.graph.query(cypher, params={"id": entity_id})
    except Exception as exc:
        raise QueryError(f"Failed to get entity '{entity_id}': {exc}") from exc

    if not result.result_set:
        return None

    node = result.result_set[0][0]
    return node_to_entity(node.labels, node.properties)


async def update_entity(
    client: GraphClient, entity_id: str, updates: dict[str, Any]
) -> EntityModel:
    """Update specified properties on an entity node.

    Raises EntityNotFoundError if the entity does not exist.
    Raises QueryError if update keys are invalid.
    Returns the updated entity.
    """
    if not updates:
        raise QueryError("No updates provided")

    _validate_property_keys(updates)

    set_clauses = ", ".join(f"n.{k} = ${k}" for k in updates)
    cypher = f"MATCH (n:Entity {{id: $id}}) SET {set_clauses} RETURN n"
    params = {"id": entity_id, **updates}

    logger.info("Updating entity id=%s fields=%s", entity_id, list(updates.keys()))
    logger.debug("Cypher: %s", cypher)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to update entity '{entity_id}': {exc}") from exc

    if not result.result_set:
        raise EntityNotFoundError(f"Entity with id '{entity_id}' not found")

    node = result.result_set[0][0]
    return node_to_entity(node.labels, node.properties)


async def delete_entity(client: GraphClient, entity_id: str) -> None:
    """Delete an entity and all its relationships.

    Succeeds silently if the entity does not exist.
    """
    cypher = "MATCH (n:Entity {id: $id}) DETACH DELETE n"

    logger.info("Deleting entity id=%s", entity_id)

    try:
        await client.graph.query(cypher, params={"id": entity_id})
    except Exception as exc:
        raise QueryError(f"Failed to delete entity '{entity_id}': {exc}") from exc


async def list_entities(
    client: GraphClient, entity_type: str | None = None
) -> list[EntityModel]:
    """List all entities, optionally filtered by type label.

    The entity_type string is validated against known labels.
    """
    if entity_type is not None:
        if entity_type not in LABEL_TO_MODEL:
            raise QueryError(f"Unknown entity type: {entity_type}")
        cypher = f"MATCH (n:{entity_type}) RETURN n"
    else:
        cypher = "MATCH (n:Entity) RETURN n"

    logger.debug("Listing entities type=%s", entity_type)

    try:
        result = await client.graph.query(cypher)
    except Exception as exc:
        raise QueryError(f"Failed to list entities: {exc}") from exc

    return [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]


async def find_entities(client: GraphClient, **filters: Any) -> list[EntityModel]:
    """Find entities matching all given property filters."""
    if not filters:
        return await list_entities(client)

    _validate_property_keys(filters)

    conditions = " AND ".join(f"n.{k} = ${k}" for k in filters)
    cypher = f"MATCH (n:Entity) WHERE {conditions} RETURN n"

    logger.debug("Finding entities filters=%s", filters)

    try:
        result = await client.graph.query(cypher, params=filters)
    except Exception as exc:
        raise QueryError(f"Failed to find entities: {exc}") from exc

    return [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
