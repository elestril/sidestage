"""Export campaign data from FalkorDB/SQLite to a structured markdown directory."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from sidestage.graph.entities import list_entities
from sidestage.graph.relationships import get_related
from sidestage.memory.models import Memory
from sidestage.migration.models import BackupStatus, MigrationBackupResult
from sidestage.migration.serialization import (
    entity_to_frontmatter_dict,
    entity_type_to_subdir,
    memory_to_frontmatter_dict,
    resolve_filename,
    sanitize_filename,
)
from sidestage.models import CharacterModel, EntityModel, EventModel, EventType, LocationModel, SceneModel

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

SUBDIRS = ["characters", "locations", "items", "scenes", "events"]


async def export_campaign(campaign: Campaign) -> MigrationBackupResult:
    """Backup all entities, memories, and chat logs to the markdown/ directory.

    Reads from FalkorDB (entities, memories, relationships) and SQLite (chat logs).
    Writes a structured markdown/ directory tree with atomic swap.

    Args:
        campaign: The Campaign object (provides graph_client, storage, campaign_dir, health).

    Returns:
        MigrationBackupResult with counts of written entities, memories, and chatlogs.
    """
    errors: list[str] = []
    fatal_error = False

    if campaign.graph_client is None:
        return MigrationBackupResult(
            phase="failed",
            total_entities=0,
            total_memories=0,
            written_entities=0,
            written_memories=0,
            written_chatlogs=0,
            errors=["No graph client available"],
        )

    client = campaign.graph_client

    # Step 1: Query all entities
    try:
        entities = await list_entities(client)
    except Exception as exc:
        return MigrationBackupResult(
            phase="failed",
            total_entities=0,
            total_memories=0,
            written_entities=0,
            written_memories=0,
            written_chatlogs=0,
            errors=[f"Failed to query entities: {exc}"],
        )

    # Step 2: Query all memories
    try:
        memories = await _query_all_memories(client)
    except Exception as exc:
        logger.warning("Failed to query memories: %s", exc)
        errors.append(f"Failed to query memories: {exc}")
        memories = []

    # Step 3: Enrich entities with relationship data
    for entity in entities:
        try:
            await _enrich_entity_relationships(client, entity)
        except Exception as exc:
            logger.warning("Failed to enrich entity %s: %s", entity.id, exc)
            errors.append(f"Failed to enrich entity {entity.id}: {exc}")

    # Step 4: Retrieve chat logs from storage (events, not SceneModel.messages)
    chatlogs: dict[str, str] = {}
    for entity in entities:
        if isinstance(entity, SceneModel):
            try:
                events = campaign.storage.list_events_by_scene(entity.id)
                chat_events = [e for e in events if e.event_type == EventType.CHAT_MESSAGE]
                if chat_events:
                    chatlogs[entity.id] = _format_chatlog(chat_events)
            except Exception as exc:
                logger.warning("Failed to get chatlog for scene %s: %s", entity.id, exc)
                errors.append(f"Failed to get chatlog for scene {entity.id}: {exc}")

    # Step 5: Build directory tree in temp location
    tmp_dir = campaign.campaign_dir / ".tmp_backup"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    for subdir in SUBDIRS:
        (tmp_dir / subdir).mkdir()

    # Write entities
    entity_id_to_path: dict[str, Path] = {}
    used_filenames: dict[str, set[str]] = {s: set() for s in SUBDIRS}
    written_entities = 0

    for entity in entities:
        try:
            eid, fpath = _write_entity_file(tmp_dir, entity, used_filenames)
            entity_id_to_path[eid] = fpath
            written_entities += 1
        except Exception as exc:
            logger.warning("Failed to write entity %s: %s", entity.id, exc)
            errors.append(f"Failed to write entity {entity.id}: {exc}")
            fatal_error = True

    # Write memories
    written_memories = 0
    for memory in memories:
        try:
            if _write_memory_file(entity_id_to_path, memory):
                written_memories += 1
            else:
                errors.append(
                    f"Memory {memory.id}: no parent entity found "
                    f"(owner_id={memory.owner_id}, target_id={memory.target_id})"
                )
        except Exception as exc:
            logger.warning("Failed to write memory %s: %s", memory.id, exc)
            errors.append(f"Failed to write memory {memory.id}: {exc}")
            fatal_error = True

    # Write chat logs
    written_chatlogs = 0
    for scene_id, chatlog_content in chatlogs.items():
        try:
            if _write_chatlog_file(entity_id_to_path, scene_id, chatlog_content):
                written_chatlogs += 1
        except Exception as exc:
            logger.warning("Failed to write chatlog for scene %s: %s", scene_id, exc)
            errors.append(f"Failed to write chatlog for scene {scene_id}: {exc}")

    # Step 6: Write status.json
    entity_counts: dict[str, int] = {}
    for entity in entities:
        type_name = entity.entity_type
        entity_counts[type_name] = entity_counts.get(type_name, 0) + 1

    status = BackupStatus(
        timestamp=datetime.now(timezone.utc).isoformat(),
        success=written_entities == len(entities) and not fatal_error,
        entity_counts=entity_counts,
        memory_count=written_memories,
        chatlog_count=written_chatlogs,
        errors=errors,
        sidestage_version="0.1.0",
    )
    (tmp_dir / "status.json").write_text(
        json.dumps(status.model_dump(), indent=2)
    )

    # Step 7: Atomic swap (only if at least some entities were written, or campaign is empty)
    markdown_dir = campaign.campaign_dir / "markdown"
    if written_entities == 0 and len(entities) > 0:
        # All entity writes failed -- don't swap
        shutil.rmtree(tmp_dir, ignore_errors=True)
        errors.append("No entities were written successfully; aborting swap")
        return MigrationBackupResult(
            phase="failed",
            total_entities=len(entities),
            total_memories=len(memories),
            written_entities=0,
            written_memories=written_memories,
            written_chatlogs=written_chatlogs,
            errors=errors,
        )

    try:
        _atomic_swap(tmp_dir, markdown_dir)
    except Exception as exc:
        errors.append(f"Atomic swap failed: {exc}")
        return MigrationBackupResult(
            phase="failed",
            total_entities=len(entities),
            total_memories=len(memories),
            written_entities=written_entities,
            written_memories=written_memories,
            written_chatlogs=written_chatlogs,
            errors=errors,
        )

    # Step 8: Return result
    return MigrationBackupResult(
        phase="complete",
        total_entities=len(entities),
        total_memories=len(memories),
        written_entities=written_entities,
        written_memories=written_memories,
        written_chatlogs=written_chatlogs,
        errors=errors,
    )


async def _query_all_memories(client: GraphClient) -> list[Memory]:
    """Query all Memory nodes from FalkorDB."""
    result = await client.graph.query("MATCH (m:Memory) RETURN m")
    memories = []
    for row in result.result_set:
        node = row[0]
        props = dict(node.properties)
        if "embedding" in props and props["embedding"] is not None:
            props["embedding"] = list(props["embedding"])
        memories.append(Memory(**props))
    return memories


async def _enrich_entity_relationships(client: GraphClient, entity: EntityModel) -> None:
    """Populate relationship-derived fields on entity in-place."""
    if isinstance(entity, CharacterModel):
        related = await get_related(client, entity.id, "LOCATED_IN", "outgoing")
        if related:
            entity.location_id = related[0].id

    elif isinstance(entity, LocationModel):
        related = await get_related(client, entity.id, "CONNECTS_TO", "both")
        entity.connected_locations = [r.id for r in related]

    elif isinstance(entity, SceneModel):
        related = await get_related(client, entity.id, "AT_LOCATION", "outgoing")
        if related:
            entity.location_id = related[0].id
        # Populate scene cast from PARTICIPATES_IN edges (incoming: characters -> scene)
        participants = await get_related(client, entity.id, "PARTICIPATES_IN", "incoming")
        entity.character_ids = [p.id for p in participants]


def _format_chatlog(events: list[EventModel]) -> str:
    """Format chat events into chatlog.log content."""
    lines = []
    for evt in events:
        char_id = evt.character_id or "unknown"
        lines.append(f'[{evt.walltime}] ({char_id}) {evt.name}: "{evt.body}"')
    return "\n".join(lines)


def _write_entity_file(
    base_dir: Path,
    entity: EntityModel,
    used_filenames: dict[str, set[str]],
) -> tuple[str, Path]:
    """Write a single entity markdown file, returning (entity_id, file_path)."""
    fm_dict, body = entity_to_frontmatter_dict(entity)
    subdir = entity_type_to_subdir(entity.entity_type)
    stem = sanitize_filename(entity.name)
    stem = resolve_filename(stem, used_filenames[subdir])
    filename = stem + ".md"

    file_path = base_dir / subdir / filename
    content = "---\n" + yaml.safe_dump(dict(fm_dict), sort_keys=False, allow_unicode=True, default_flow_style=False) + "---\n"
    if body:
        content += "\n" + body + "\n"
    file_path.write_text(content)

    return entity.id, file_path


def _write_memory_file(
    entity_id_to_path: dict[str, Path],
    memory: Memory,
) -> bool:
    """Write a single memory markdown file into the appropriate .d/ directory."""
    # Try owner first, fall back to target if owner is missing or unknown
    parent_id = None
    if memory.owner_id and memory.owner_id in entity_id_to_path:
        parent_id = memory.owner_id
    elif memory.target_id and memory.target_id in entity_id_to_path:
        parent_id = memory.target_id

    if parent_id is None:
        return False

    entity_path = entity_id_to_path[parent_id]
    dot_d_dir = entity_path.parent / (entity_path.stem + ".d")
    dot_d_dir.mkdir(exist_ok=True)

    fm_dict, content_body = memory_to_frontmatter_dict(memory)
    filename = sanitize_filename(memory.id) + ".md"
    file_path = dot_d_dir / filename

    content = "---\n" + yaml.safe_dump(dict(fm_dict), sort_keys=False, allow_unicode=True, default_flow_style=False) + "---\n"
    if content_body:
        content += "\n" + content_body + "\n"
    file_path.write_text(content)
    return True


def _write_chatlog_file(
    entity_id_to_path: dict[str, Path],
    scene_id: str,
    chatlog_content: str,
) -> bool:
    """Write chatlog.log into the scene's .d/ directory."""
    if scene_id not in entity_id_to_path:
        return False

    entity_path = entity_id_to_path[scene_id]
    dot_d_dir = entity_path.parent / (entity_path.stem + ".d")
    dot_d_dir.mkdir(exist_ok=True)

    (dot_d_dir / "chatlog.log").write_text(chatlog_content)
    return True


def _atomic_swap(tmp_dir: Path, target_dir: Path) -> None:
    """Atomically swap tmp_dir into target_dir position, preserving old as fallback."""
    old_backup = target_dir.parent / ".old_backup"

    # Clean up any leftover old backup
    if old_backup.exists():
        shutil.rmtree(old_backup)

    if target_dir.exists():
        target_dir.rename(old_backup)

    try:
        tmp_dir.rename(target_dir)
    except Exception:
        # Restore old directory if swap fails
        if old_backup.exists() and not target_dir.exists():
            old_backup.rename(target_dir)
        raise

    # Clean up old backup
    if old_backup.exists():
        shutil.rmtree(old_backup)
