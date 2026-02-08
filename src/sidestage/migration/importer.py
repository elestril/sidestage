"""Import parsed campaign data into FalkorDB, replacing the existing graph."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sidestage.graph.entities import create_entity, list_entities
from sidestage.graph.relationships import link
from sidestage.graph.schema import initialize_schema
from sidestage.health import HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.memory.store import _TYPE_TO_SUBLABEL
from sidestage.migration.models import MigrationImportResult, ParseResult
from sidestage.schemas import Character, ChatMessage, Entity, Event, Location, Scene

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.graph.client import GraphClient
    from sidestage.sync import SyncManager

logger = logging.getLogger(__name__)

_CHATLOG_RE = re.compile(
    r"^\[([^\]]+)\]\s+\(([^)]+)\)\s+([^:]+):\s+\"(.*)\"$"
)


async def import_campaign(
    campaign: Campaign,
    parse_result: ParseResult,
    sync_manager: SyncManager | None = None,
    active_scenes: dict | None = None,
) -> MigrationImportResult:
    """Import parsed entities and memories into FalkorDB, replacing the existing graph.

    This is a destructive operation: the existing graph is dropped and recreated.

    Args:
        campaign: The Campaign object (provides graph_client, storage, health, config).
        parse_result: The parsed directory tree (entities, memories, chatlogs, errors).
        sync_manager: Optional SyncManager for broadcasting entities_updated.
        active_scenes: Optional dict of active scenes to clear after import.

    Returns:
        MigrationImportResult with counts of processed entities and memories.
    """
    errors: list[str] = []
    processed_entities = 0
    processed_memories = 0

    if campaign.graph_client is None:
        return MigrationImportResult(
            phase="failed",
            total_entities=len(parse_result.entities),
            total_memories=len(parse_result.memories),
            processed_entities=0,
            processed_memories=0,
            errors=["No graph_client available on campaign"],
        )

    try:
        await campaign.health.set_status(HealthStatus.DEGRADED, "Importing campaign data")

        # Step 2: Drop and recreate graph
        try:
            await _drop_and_recreate_graph(campaign)
        except Exception as exc:
            errors.append(f"Graph drop failed: {exc}")
            return MigrationImportResult(
                phase="failed",
                total_entities=len(parse_result.entities),
                total_memories=len(parse_result.memories),
                processed_entities=0,
                processed_memories=0,
                errors=errors,
            )

        # Step 4: Insert entities
        processed_entities, entity_errors = await _insert_entities(
            campaign.graph_client, parse_result.entities
        )
        errors.extend(entity_errors)

        # Step 5: Create relationships
        rel_errors = await _create_relationships(
            campaign.graph_client, parse_result.entities
        )
        errors.extend(rel_errors)

        # Step 6: Insert memories
        processed_memories, mem_errors = await _insert_memories(
            campaign.graph_client, parse_result.memories
        )
        errors.extend(mem_errors)

        # Step 7: Restore chat logs
        chatlog_errors = _restore_chatlogs(campaign, parse_result.chatlogs)
        errors.extend(chatlog_errors)

        # Step 8: Verify counts
        try:
            inserted = await list_entities(campaign.graph_client)
            if len(inserted) != processed_entities:
                logger.warning(
                    "Entity count mismatch: expected %d, got %d",
                    processed_entities, len(inserted),
                )
        except Exception as exc:
            logger.warning("Failed to verify entity counts: %s", exc)

        try:
            mem_result = await campaign.graph_client.graph.query(
                "MATCH (m:Memory) RETURN count(m) as count"
            )
            if mem_result.result_set:
                mem_count = mem_result.result_set[0][0]
                if mem_count != processed_memories:
                    logger.warning(
                        "Memory count mismatch: expected %d, got %d",
                        processed_memories, mem_count,
                    )
        except Exception as exc:
            logger.warning("Failed to verify memory counts: %s", exc)

        # Step 9: Post-import cleanup
        if active_scenes is not None:
            active_scenes.clear()

        if sync_manager is not None:
            await sync_manager.broadcast({"type": "entities_updated"})

        phase = "failed" if processed_entities == 0 and len(parse_result.entities) > 0 else "complete"

        return MigrationImportResult(
            phase=phase,
            total_entities=len(parse_result.entities),
            total_memories=len(parse_result.memories),
            processed_entities=processed_entities,
            processed_memories=processed_memories,
            errors=errors,
        )

    finally:
        await campaign.health.set_status(HealthStatus.HEALTHY, "")


async def _drop_and_recreate_graph(campaign: Campaign) -> None:
    """Drop the existing graph and reinitialize the schema."""
    client = campaign.graph_client
    await client.graph.delete()
    client.graph = client.db.select_graph(client.graph_name)
    await initialize_schema(
        client,
        vector_dimension=campaign.config.graph.vector_dimension,
    )


async def _insert_entities(
    client: GraphClient, entities: list[Entity],
) -> tuple[int, list[str]]:
    """Insert all entities into the graph. Returns (success_count, errors)."""
    count = 0
    errors: list[str] = []
    for entity in entities:
        try:
            await create_entity(client, entity)
            count += 1
        except Exception as exc:
            errors.append(f"Failed to insert entity '{entity.id}': {exc}")
            logger.warning("Failed to insert entity %s: %s", entity.id, exc)
    return count, errors


async def _create_relationships(
    client: GraphClient, entities: list[Entity],
) -> list[str]:
    """Create all entity-to-entity relationship edges.

    Handles LOCATED_IN, CONNECTS_TO (deduplicated), AT_LOCATION, HAS_EVENT.
    """
    errors: list[str] = []
    connected_pairs: set[frozenset[str]] = set()

    for entity in entities:
        try:
            if isinstance(entity, Character) and entity.location_id:
                await link(client, entity.id, "LOCATED_IN", entity.location_id)
        except Exception as exc:
            errors.append(f"LOCATED_IN failed for '{entity.id}': {exc}")

        if isinstance(entity, Location):
            for other_id in entity.connected_locations:
                pair = frozenset({entity.id, other_id})
                if pair not in connected_pairs:
                    try:
                        await link(client, entity.id, "CONNECTS_TO", other_id)
                        connected_pairs.add(pair)
                    except Exception as exc:
                        errors.append(f"CONNECTS_TO failed for '{entity.id}' -> '{other_id}': {exc}")

        try:
            if isinstance(entity, Scene) and entity.location_id:
                await link(client, entity.id, "AT_LOCATION", entity.location_id)
        except Exception as exc:
            errors.append(f"AT_LOCATION failed for '{entity.id}': {exc}")

        try:
            if isinstance(entity, Event):
                await link(client, entity.scene_id, "HAS_EVENT", entity.id)
        except Exception as exc:
            errors.append(f"HAS_EVENT failed for '{entity.id}': {exc}")

    return errors


async def _insert_memories(
    client: GraphClient, memories: list[Memory],
) -> tuple[int, list[str]]:
    """Insert all memories with HAS_MEMORY/ABOUT relationships."""
    count = 0
    errors: list[str] = []
    for memory in memories:
        try:
            await _insert_memory(client, memory)
            count += 1
        except Exception as exc:
            errors.append(f"Failed to insert memory '{memory.id}': {exc}")
            logger.warning("Failed to insert memory %s: %s", memory.id, exc)
    return count, errors


async def _insert_memory(client: GraphClient, memory: Memory) -> None:
    """Insert a single memory node with HAS_MEMORY and ABOUT relationships.

    Uses CREATE (not MERGE) since we are starting from an empty graph.
    Preserves the original memory ID from the import data.
    """
    sublabel = _TYPE_TO_SUBLABEL[memory.memory_type]

    params = {
        "id": memory.id,
        "content": memory.content,
        "memory_type": memory.memory_type.value,
        "visibility": memory.visibility,
        "owner_id": memory.owner_id,
        "target_id": memory.target_id,
        "gametime": memory.gametime,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "access_count": memory.access_count,
    }

    if memory.last_accessed_at is not None:
        params["last_accessed_at"] = memory.last_accessed_at

    # Build property assignments
    prop_parts = ", ".join(f"{k}: ${k}" for k in params)

    cypher = (
        f"CREATE (m:Memory:{sublabel} {{{prop_parts}}})\n"
        "WITH m\n"
        "OPTIONAL MATCH (owner:Entity {id: $owner_id})\n"
        "FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |\n"
        "  CREATE (owner)-[:HAS_MEMORY]->(m)\n"
        ")\n"
        "WITH m\n"
        "OPTIONAL MATCH (target:Entity {id: $target_id})\n"
        "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
        "  CREATE (m)-[:ABOUT]->(target)\n"
        ")"
    )

    await client.graph.query(cypher, params=params)


def _restore_chatlogs(
    campaign: Campaign, chatlogs: dict[str, list[str]],
) -> list[str]:
    """Restore chat logs to SQLite storage. Returns list of error messages."""
    errors: list[str] = []

    for scene_id, lines in chatlogs.items():
        if not lines:
            continue
        try:
            messages = _parse_chatlog_lines(scene_id, lines)
            existing = campaign.storage.get_scene(scene_id)
            if existing is not None:
                existing.messages = messages
                campaign.storage.update_scene(existing)
            else:
                scene = Scene(
                    name=scene_id, body="", id=scene_id, messages=messages,
                )
                campaign.storage.add_scene(scene)
        except Exception as exc:
            errors.append(f"Failed to restore chatlog for scene '{scene_id}': {exc}")
            logger.warning("Failed to restore chatlog for %s: %s", scene_id, exc)

    return errors


def _parse_chatlog_lines(scene_id: str, lines: list[str]) -> list[ChatMessage]:
    """Parse raw chatlog lines into ChatMessage objects.

    Format: [{walltime}] ({character_id}) {name}: "{message}"
    """
    messages: list[ChatMessage] = []
    for line in lines:
        match = _CHATLOG_RE.match(line.strip())
        if not match:
            logger.warning("Unparseable chatlog line: %s", line)
            continue
        walltime, character_id, name, message = match.groups()
        msg = ChatMessage(
            name=name.strip(),
            body="",
            id=f"{scene_id}_msg_{len(messages)}",
            scene_id=scene_id,
            gametime=0,
            walltime=walltime,
            character_id=character_id,
            message=message,
        )
        messages.append(msg)
    return messages
