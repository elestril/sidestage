"""Relationship (edge) operations for FalkorDB graph.

Provides async functions for creating, removing, and querying
relationships between entity nodes.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TYPE_CHECKING

from sidestage.graph.entities import node_to_entity
from sidestage.graph.errors import EntityNotFoundError, QueryError
from sidestage.schemas import Entity

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

VALID_REL_TYPES = frozenset({
    "LOCATED_IN",
    "CONNECTS_TO",
    "AT_LOCATION",
    "HAS_EVENT",
    "INVOLVES",
    "PARTICIPATES_IN",
})

VALID_DIRECTIONS = frozenset({"outgoing", "incoming", "both"})

# Safe property key pattern: alphanumeric + underscores, must start with letter/underscore.
_VALID_PROP_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$", re.IGNORECASE)


def _validate_rel_type(rel_type: str) -> None:
    """Validate rel_type against allowed set to prevent Cypher injection."""
    if rel_type not in VALID_REL_TYPES:
        raise ValueError(
            f"Invalid relationship type: {rel_type!r}. "
            f"Must be one of {sorted(VALID_REL_TYPES)}"
        )


def _validate_direction(direction: str) -> None:
    """Validate direction parameter."""
    if direction not in VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction: {direction!r}. "
            f"Must be one of {sorted(VALID_DIRECTIONS)}"
        )


async def link(
    client: GraphClient,
    source_id: str,
    rel_type: str,
    target_id: str,
    properties: dict | None = None,
) -> None:
    """Create a relationship between two entities.

    Matches source and target by :Entity id property, creates a typed edge.
    Optional properties dict for edge metadata (stored on the edge).

    Raises EntityNotFoundError if source or target entity does not exist.
    Raises QueryError if the Cypher query fails.
    """
    _validate_rel_type(rel_type)

    logger.debug("Linking %s -[%s]-> %s", source_id, rel_type, target_id)

    # Check both entities exist
    check_cypher = (
        "OPTIONAL MATCH (s:Entity {id: $source_id}) "
        "OPTIONAL MATCH (t:Entity {id: $target_id}) "
        "RETURN s.id, t.id"
    )
    try:
        result = await client.graph.query(
            check_cypher, params={"source_id": source_id, "target_id": target_id}
        )
    except Exception as exc:
        raise QueryError(f"Failed to check entities for link: {exc}") from exc

    if not result.result_set:
        raise EntityNotFoundError(
            f"Entity '{source_id}' or '{target_id}' not found"
        )

    row = result.result_set[0]
    if row[0] is None:
        raise EntityNotFoundError(f"Source entity '{source_id}' not found")
    if row[1] is None:
        raise EntityNotFoundError(f"Target entity '{target_id}' not found")

    # Create the edge
    if properties:
        for k in properties:
            if not _VALID_PROP_KEY_RE.match(k):
                raise QueryError(f"Invalid property key format: {k!r}")
        # Prefix property params to avoid collision with source_id/target_id
        prop_assignments = ", ".join(f"{k}: $prop_{k}" for k in properties)
        create_cypher = (
            f"MATCH (s:Entity {{id: $source_id}}) "
            f"MATCH (t:Entity {{id: $target_id}}) "
            f"CREATE (s)-[:{rel_type} {{{prop_assignments}}}]->(t)"
        )
        params: dict[str, Any] = {
            "source_id": source_id,
            "target_id": target_id,
            **{f"prop_{k}": v for k, v in properties.items()},
        }
    else:
        create_cypher = (
            f"MATCH (s:Entity {{id: $source_id}}) "
            f"MATCH (t:Entity {{id: $target_id}}) "
            f"CREATE (s)-[:{rel_type}]->(t)"
        )
        params = {"source_id": source_id, "target_id": target_id}

    try:
        await client.graph.query(create_cypher, params=params)
    except Exception as exc:
        raise QueryError(
            f"Failed to create {rel_type} from '{source_id}' to '{target_id}': {exc}"
        ) from exc

    logger.info("Linked %s -[%s]-> %s", source_id, rel_type, target_id)


async def unlink(
    client: GraphClient,
    source_id: str,
    rel_type: str,
    target_id: str,
) -> None:
    """Remove a relationship between two entities.

    Idempotent: does not raise if the edge does not exist.
    """
    _validate_rel_type(rel_type)

    logger.debug("Unlinking %s -[%s]-> %s", source_id, rel_type, target_id)

    cypher = (
        f"MATCH (s:Entity {{id: $source_id}})-[r:{rel_type}]->(t:Entity {{id: $target_id}}) "
        "DELETE r"
    )
    try:
        await client.graph.query(
            cypher, params={"source_id": source_id, "target_id": target_id}
        )
    except Exception as exc:
        raise QueryError(
            f"Failed to unlink {rel_type} from '{source_id}' to '{target_id}': {exc}"
        ) from exc

    logger.info("Unlinked %s -[%s]-> %s", source_id, rel_type, target_id)


async def get_related(
    client: GraphClient,
    entity_id: str,
    rel_type: str,
    direction: str = "outgoing",
) -> list[Entity]:
    """Get entities related via a specific relationship type.

    Args:
        client: The graph client.
        entity_id: ID of the source entity.
        rel_type: The relationship type to traverse.
        direction: "outgoing", "incoming", or "both".

    Returns:
        List of deserialized Entity (or subclass) objects.
    """
    _validate_rel_type(rel_type)
    _validate_direction(direction)

    if direction == "outgoing":
        cypher = f"MATCH (s:Entity {{id: $id}})-[:{rel_type}]->(t) RETURN t"
    elif direction == "incoming":
        cypher = f"MATCH (s:Entity {{id: $id}})<-[:{rel_type}]-(t) RETURN t"
    else:  # both
        cypher = f"MATCH (s:Entity {{id: $id}})-[:{rel_type}]-(t) RETURN t"

    logger.debug("get_related id=%s rel=%s dir=%s", entity_id, rel_type, direction)

    try:
        result = await client.graph.query(cypher, params={"id": entity_id})
    except Exception as exc:
        raise QueryError(
            f"Failed to get related entities for '{entity_id}': {exc}"
        ) from exc

    entities = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
    logger.debug("get_related returned %d entities", len(entities))
    return entities


async def get_relationships(
    client: GraphClient,
    entity_id: str,
) -> list[dict]:
    """Get all relationships for an entity.

    Returns list of dicts, each containing:
        - rel_type: str
        - direction: str ("outgoing" or "incoming")
        - target_id: str
        - target_name: str
        - properties: dict
    """
    logger.debug("get_relationships id=%s", entity_id)

    outgoing_cypher = (
        "MATCH (s:Entity {id: $id})-[r]->(t:Entity) "
        "RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props"
    )
    incoming_cypher = (
        "MATCH (s:Entity {id: $id})<-[r]-(t:Entity) "
        "RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props"
    )

    try:
        outgoing_result = await client.graph.query(outgoing_cypher, params={"id": entity_id})
        incoming_result = await client.graph.query(incoming_cypher, params={"id": entity_id})
    except Exception as exc:
        raise QueryError(
            f"Failed to get relationships for '{entity_id}': {exc}"
        ) from exc

    relationships: list[dict] = []

    for row in outgoing_result.result_set:
        relationships.append({
            "rel_type": row[0],
            "direction": "outgoing",
            "target_id": row[1],
            "target_name": row[2],
            "properties": row[3] if row[3] else {},
        })

    for row in incoming_result.result_set:
        relationships.append({
            "rel_type": row[0],
            "direction": "incoming",
            "target_id": row[1],
            "target_name": row[2],
            "properties": row[3] if row[3] else {},
        })

    logger.debug("get_relationships returned %d relationships", len(relationships))
    return relationships
