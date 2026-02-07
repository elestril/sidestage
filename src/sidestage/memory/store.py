"""Memory CRUD operations and vector search for FalkorDB.

All Cypher for Memory nodes lives here. Does NOT use graph/entities.py
or graph/relationships.py. Memory nodes use :Memory labels, not :Entity.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from sidestage.memory.models import Memory, MemoryType, ContextMemories
from sidestage.graph.errors import QueryError

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

MEMORY_REL_TYPES = frozenset({"HAS_MEMORY", "ABOUT"})

_TYPE_TO_SUBLABEL: dict[MemoryType, str] = {
    MemoryType.SCENE: "SceneMemory",
    MemoryType.CHARACTER: "CharacterMemory",
    MemoryType.WORLD_FACT: "WorldFact",
}


def _node_to_memory(node) -> Memory:
    """Convert a FalkorDB node to a Memory model."""
    props = dict(node.properties)
    # FalkorDB may store embedding as a special vector type; convert if needed
    if "embedding" in props and props["embedding"] is not None:
        props["embedding"] = list(props["embedding"])
    return Memory(**props)


# --- Upsert operations ---


async def upsert_memory(
    client: GraphClient,
    memory_type: MemoryType,
    visibility: str,
    owner_id: str | None,
    target_id: str,
    content: str,
    gametime: int | None = None,
) -> Memory:
    """Create or update a memory.

    Uniqueness key: (owner_id, memory_type, target_id) for private memories,
    or (memory_type, visibility, target_id) for common memories (owner_id is None).

    Uses MERGE in Cypher. Creates HAS_MEMORY and ABOUT relationships
    if this is a new memory. Returns the Memory object.
    """
    sublabel = _TYPE_TO_SUBLABEL[memory_type]
    now = time.time()
    mem_id = str(uuid.uuid4())

    params: dict = {
        "id": mem_id,
        "content": content,
        "memory_type": memory_type.value,
        "visibility": visibility,
        "owner_id": owner_id,
        "target_id": target_id,
        "now": now,
        "gametime": gametime,
    }

    if owner_id is not None:
        # Private memory: merge on (owner_id, memory_type, target_id)
        cypher = (
            f"MERGE (m:Memory:{sublabel} "
            "{owner_id: $owner_id, memory_type: $memory_type, target_id: $target_id})\n"
            "ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0\n"
            "SET m.content = $content, m.updated_at = $now, m.visibility = $visibility, m.gametime = $gametime\n"
            "WITH m\n"
            "OPTIONAL MATCH (owner:Entity {id: $owner_id})\n"
            "FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |\n"
            "  MERGE (owner)-[:HAS_MEMORY]->(m)\n"
            ")\n"
            "WITH m\n"
            "OPTIONAL MATCH (target:Entity {id: $target_id})\n"
            "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
            "  MERGE (m)-[:ABOUT]->(target)\n"
            ")\n"
            "RETURN m"
        )
    else:
        # Common memory: merge on (memory_type, visibility, target_id)
        cypher = (
            f"MERGE (m:Memory:{sublabel} "
            "{memory_type: $memory_type, visibility: $visibility, target_id: $target_id})\n"
            "ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0\n"
            "SET m.content = $content, m.updated_at = $now, m.gametime = $gametime\n"
            "WITH m\n"
            "OPTIONAL MATCH (target:Entity {id: $target_id})\n"
            "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
            "  MERGE (m)-[:ABOUT]->(target)\n"
            ")\n"
            "RETURN m"
        )

    logger.info("Upserting %s memory target_id=%s owner_id=%s", sublabel, target_id, owner_id)
    logger.debug("Cypher: %s", cypher)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to upsert memory: {exc}") from exc

    if not result.result_set:
        raise QueryError("MERGE returned no results for memory upsert")

    return _node_to_memory(result.result_set[0][0])


async def upsert_scene_memory(client: GraphClient, owner_id: str, scene_id: str, content: str, gametime: int | None = None) -> Memory:
    """Upsert a character's private scene memory."""
    return await upsert_memory(
        client, MemoryType.SCENE, "private", owner_id, scene_id, content, gametime
    )


async def upsert_common_scene_memory(client: GraphClient, scene_id: str, content: str, gametime: int | None = None) -> Memory:
    """Upsert the common scene memory (visibility=common, no owner)."""
    return await upsert_memory(
        client, MemoryType.SCENE, "common", None, scene_id, content, gametime
    )


async def upsert_character_memory(client: GraphClient, owner_id: str, about_character_id: str, content: str, gametime: int | None = None) -> Memory:
    """Upsert a character's memory about another character."""
    return await upsert_memory(
        client, MemoryType.CHARACTER, "private", owner_id, about_character_id, content, gametime
    )


async def upsert_world_fact(client: GraphClient, about_entity_id: str, content: str, visibility: str = "common", owner_id: str | None = None) -> Memory:
    """Upsert a world fact. Common by default, or private to a specific character."""
    return await upsert_memory(
        client, MemoryType.WORLD_FACT, visibility, owner_id, about_entity_id, content
    )


# --- Read operations ---


async def get_scene_memory(client: GraphClient, owner_id: str, scene_id: str) -> Memory | None:
    """Get a character's private scene memory."""
    cypher = (
        "MATCH (m:Memory:SceneMemory {owner_id: $owner_id, memory_type: $memory_type, target_id: $scene_id})\n"
        "RETURN m"
    )
    params = {"owner_id": owner_id, "memory_type": "scene", "scene_id": scene_id}

    logger.debug("Getting scene memory owner=%s scene=%s", owner_id, scene_id)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to get scene memory: {exc}") from exc

    if not result.result_set:
        return None
    return _node_to_memory(result.result_set[0][0])


async def get_common_scene_memory(client: GraphClient, scene_id: str) -> Memory | None:
    """Get the common scene memory."""
    cypher = (
        "MATCH (m:Memory:SceneMemory {visibility: $visibility, memory_type: $memory_type, target_id: $scene_id})\n"
        "WHERE m.owner_id IS NULL\n"
        "RETURN m"
    )
    params = {"visibility": "common", "memory_type": "scene", "scene_id": scene_id}

    logger.debug("Getting common scene memory scene=%s", scene_id)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to get common scene memory: {exc}") from exc

    if not result.result_set:
        return None
    return _node_to_memory(result.result_set[0][0])


async def get_character_memory(client: GraphClient, owner_id: str, about_character_id: str) -> Memory | None:
    """Get a character's memory about another character."""
    cypher = (
        "MATCH (m:Memory:CharacterMemory {owner_id: $owner_id, memory_type: $memory_type, target_id: $target_id})\n"
        "RETURN m"
    )
    params = {"owner_id": owner_id, "memory_type": "character", "target_id": about_character_id}

    logger.debug("Getting character memory owner=%s about=%s", owner_id, about_character_id)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to get character memory: {exc}") from exc

    if not result.result_set:
        return None
    return _node_to_memory(result.result_set[0][0])


async def get_memories_for_context(
    client: GraphClient,
    character_id: str,
    scene_id: str,
    present_character_ids: list[str],
) -> ContextMemories:
    """Fetch all memories needed for a character's context assembly.

    Uses separate queries for each memory category. Returns a ContextMemories
    object grouping them by type.
    """
    # Query 1: common scene memory
    common_scene = await get_common_scene_memory(client, scene_id)

    # Query 2: private scene memory
    private_scene = await get_scene_memory(client, character_id, scene_id)

    # Query 3: character memories about present characters
    character_memories: dict[str, Memory] = {}
    if present_character_ids:
        cypher = (
            "MATCH (m:Memory:CharacterMemory {owner_id: $owner_id, memory_type: $memory_type})\n"
            "WHERE m.target_id IN $target_ids\n"
            "RETURN m"
        )
        params = {
            "owner_id": character_id,
            "memory_type": "character",
            "target_ids": present_character_ids,
        }
        try:
            result = await client.graph.query(cypher, params=params)
        except Exception as exc:
            raise QueryError(f"Failed to get character memories: {exc}") from exc

        for row in result.result_set:
            mem = _node_to_memory(row[0])
            character_memories[mem.target_id] = mem

    # Query 4: common world facts
    wf_cypher = (
        "MATCH (m:Memory:WorldFact {memory_type: $memory_type, visibility: $visibility})\n"
        "RETURN m"
    )
    wf_params = {"memory_type": "world_fact", "visibility": "common"}
    try:
        wf_result = await client.graph.query(wf_cypher, params=wf_params)
    except Exception as exc:
        raise QueryError(f"Failed to get world facts: {exc}") from exc

    world_facts = [_node_to_memory(row[0]) for row in wf_result.result_set]

    return ContextMemories(
        common_scene_memory=common_scene,
        private_scene_memory=private_scene,
        character_memories=character_memories,
        world_facts=world_facts,
    )


async def get_all_memories(client: GraphClient, owner_id: str, memory_type: MemoryType | None = None) -> list[Memory]:
    """Get all memories owned by a character, optionally filtered by type."""
    if memory_type is not None:
        cypher = (
            "MATCH (m:Memory {owner_id: $owner_id, memory_type: $memory_type})\n"
            "RETURN m"
        )
        params = {"owner_id": owner_id, "memory_type": memory_type.value if hasattr(memory_type, 'value') else memory_type}
    else:
        cypher = (
            "MATCH (m:Memory {owner_id: $owner_id})\n"
            "RETURN m"
        )
        params = {"owner_id": owner_id}

    logger.debug("Getting all memories owner=%s type=%s", owner_id, memory_type)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        raise QueryError(f"Failed to get all memories: {exc}") from exc

    return [_node_to_memory(row[0]) for row in result.result_set]


# --- Delete and Touch ---


async def delete_memory(client: GraphClient, memory_id: str) -> None:
    """Delete a memory and its relationships.

    Uses DETACH DELETE. Idempotent -- succeeds silently if memory_id does not exist.
    """
    cypher = "MATCH (m:Memory {id: $id}) DETACH DELETE m"

    logger.info("Deleting memory id=%s", memory_id)

    try:
        await client.graph.query(cypher, params={"id": memory_id})
    except Exception as exc:
        raise QueryError(f"Failed to delete memory '{memory_id}': {exc}") from exc


async def touch_memory(client: GraphClient, memory_id: str) -> None:
    """Increment access_count and update last_accessed_at.

    Called during context assembly. Separate from get to avoid
    inflating counts during debugging/admin.
    """
    cypher = (
        "MATCH (m:Memory {id: $id})\n"
        "SET m.access_count = m.access_count + 1, m.last_accessed_at = $now"
    )

    logger.debug("Touching memory id=%s", memory_id)

    try:
        await client.graph.query(cypher, params={"id": memory_id, "now": time.time()})
    except Exception as exc:
        raise QueryError(f"Failed to touch memory '{memory_id}': {exc}") from exc


# --- Vector search ---


async def search_similar(
    client: GraphClient,
    query_embedding: list[float],
    owner_id: str | None = None,
    visibility: str | None = None,
    limit: int = 10,
) -> list[tuple[Memory, float]]:
    """Find memories similar to query embedding.

    Uses FalkorDB vector index via CALL db.idx.vector.queryNodes.
    Post-filters by owner_id and/or visibility in the WHERE clause.
    Returns (Memory, similarity_score) tuples ordered by score descending.

    Returns empty list if the vector index does not exist or the query fails.
    """
    cypher = (
        "CALL db.idx.vector.queryNodes('Memory', 'embedding', $limit, vecf32($vec))\n"
        "YIELD node, score\n"
        "WHERE ($owner_id IS NULL OR node.owner_id = $owner_id)\n"
        "  AND ($visibility IS NULL OR node.visibility = $visibility)\n"
        "RETURN node, score\n"
        "ORDER BY score DESC"
    )
    params = {
        "limit": limit,
        "vec": query_embedding,
        "owner_id": owner_id,
        "visibility": visibility,
    }

    logger.debug("Searching similar memories limit=%d", limit)

    try:
        result = await client.graph.query(cypher, params=params)
    except Exception as exc:
        logger.warning("Vector search failed (index may not exist): %s", exc)
        return []

    return [(_node_to_memory(row[0]), row[1]) for row in result.result_set]
