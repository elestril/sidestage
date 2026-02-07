"""Higher-level graph query functions for common traversal patterns.

Provides specialized, efficient Cypher-based query functions that combine
entity and relationship operations into single graph traversals.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from sidestage.graph.entities import node_to_entity
from sidestage.graph.errors import QueryError
from sidestage.schemas import Character, Entity, Event, Location

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)


async def characters_at_location(client: GraphClient, location_id: str) -> list[Character]:
    """All characters currently at a location (via LOCATED_IN).

    Returns a list of Character models. Returns empty list if no characters
    are at the location or if the location does not exist.
    """
    cypher = (
        "MATCH (c:Character)-[:LOCATED_IN]->(l:Location {id: $location_id}) "
        "RETURN c"
    )

    logger.debug("characters_at_location id=%s", location_id)

    try:
        result = await client.graph.query(cypher, params={"location_id": location_id})
    except Exception as exc:
        raise QueryError(f"Failed to query characters at location '{location_id}': {exc}") from exc

    characters = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
    logger.debug("characters_at_location returned %d characters", len(characters))
    return characters


async def connected_locations(client: GraphClient, location_id: str) -> list[Location]:
    """All locations connected to a given location (CONNECTS_TO, both directions).

    Uses undirected match since CONNECTS_TO is semantically bidirectional.
    Returns a list of Location models. Returns empty list if no connections exist.
    """
    cypher = (
        "MATCH (l:Location {id: $location_id})-[:CONNECTS_TO]-(other:Location) "
        "RETURN other"
    )

    logger.debug("connected_locations id=%s", location_id)

    try:
        result = await client.graph.query(cypher, params={"location_id": location_id})
    except Exception as exc:
        raise QueryError(f"Failed to query connected locations for '{location_id}': {exc}") from exc

    locations = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
    logger.debug("connected_locations returned %d locations", len(locations))
    return locations


async def scene_events(
    client: GraphClient, scene_id: str, since_gametime: int | None = None
) -> list[Event]:
    """Events in a scene, optionally filtered by gametime.

    Returns a list of Event models (may include ChatMessage subtype based
    on node labels). Returns empty list if scene has no events.
    Always ordered by gametime ascending.
    """
    params: dict[str, Any] = {"scene_id": scene_id}

    cypher = "MATCH (s:Scene {id: $scene_id})-[:HAS_EVENT]->(e:Event) "
    if since_gametime is not None:
        cypher += "WHERE e.gametime >= $since_gametime "
        params["since_gametime"] = since_gametime
    cypher += "RETURN e ORDER BY e.gametime ASC"

    logger.debug("scene_events id=%s since=%s", scene_id, since_gametime)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to query events for scene '{scene_id}': {exc}") from exc

    events = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
    logger.debug("scene_events returned %d events", len(events))
    return events


async def entity_graph(client: GraphClient, entity_id: str, depth: int = 1) -> dict:
    """Get an entity and its neighborhood to a given depth.

    Returns a dict with:
        - "entity": the center Entity model (or None if not found)
        - "related": list of Entity models within the given depth
    """
    if not isinstance(depth, int) or depth < 1:
        raise ValueError(f"depth must be a positive integer, got {depth!r}")

    cypher = (
        "MATCH (center:Entity {id: $entity_id}) "
        f"OPTIONAL MATCH path = (center)-[*1..{depth}]-(neighbor:Entity) "
        "RETURN center, collect(DISTINCT neighbor) AS neighbors"
    )

    logger.debug("entity_graph id=%s depth=%d", entity_id, depth)

    try:
        result = await client.graph.query(cypher, params={"entity_id": entity_id})
    except Exception as exc:
        raise QueryError(f"Failed to query entity graph for '{entity_id}': {exc}") from exc

    if not result.result_set:
        return {"entity": None, "related": []}

    row = result.result_set[0]
    center_node = row[0]
    neighbor_nodes = row[1]

    entity = node_to_entity(center_node.labels, center_node.properties)
    related = [node_to_entity(n.labels, n.properties) for n in neighbor_nodes]

    logger.debug("entity_graph returned entity + %d related", len(related))
    return {"entity": entity, "related": related}
