"""Referential integrity and schema validation for parsed campaign data."""

from __future__ import annotations

from collections import Counter

from sidestage.memory.models import MemoryType
from sidestage.migration.models import (
    MigrationValidationIssue,
    MigrationValidationReport,
    ParseResult,
)
from sidestage.schemas import Character, Event, Location, Scene


def validate_parse_result(parse_result: ParseResult) -> MigrationValidationReport:
    """Validate referential integrity and required fields in parsed campaign data.

    Args:
        parse_result: Output of parse_directory(), containing entities, memories,
            chatlogs, and parse-level errors.

    Returns:
        MigrationValidationReport with valid flag, counts, errors, and warnings.
    """
    errors: list[MigrationValidationIssue] = []
    warnings: list[MigrationValidationIssue] = []

    # Step 1: Build lookup indices
    entity_ids: set[str] = set()
    location_ids: set[str] = set()
    item_ids: set[str] = set()
    scene_ids: set[str] = set()

    for entity in parse_result.entities:
        entity_ids.add(entity.id)
        if isinstance(entity, Location):
            location_ids.add(entity.id)
        elif isinstance(entity, Scene):
            scene_ids.add(entity.id)
        elif isinstance(entity, Event):
            pass  # Events don't form a reference target set
        else:
            from sidestage.schemas import Item
            if isinstance(entity, Item):
                item_ids.add(entity.id)

    # Step 2: Check entity ID uniqueness
    seen_ids: Counter[str] = Counter()
    for entity in parse_result.entities:
        seen_ids[entity.id] += 1
    for eid, count in seen_ids.items():
        if count > 1:
            errors.append(MigrationValidationIssue(
                entity_id=eid,
                file_path="",
                severity="error",
                message=f"Duplicate entity ID: {eid}",
            ))

    # Step 3: Check entity cross-references
    for entity in parse_result.entities:
        if isinstance(entity, Character):
            if entity.location_id is not None and entity.location_id not in location_ids:
                errors.append(MigrationValidationIssue(
                    entity_id=entity.id,
                    file_path="",
                    severity="error",
                    message=f"Character '{entity.id}' references non-existent location '{entity.location_id}'",
                ))
            for inv_id in entity.inventory:
                if inv_id not in item_ids:
                    errors.append(MigrationValidationIssue(
                        entity_id=entity.id,
                        file_path="",
                        severity="error",
                        message=f"Character '{entity.id}' references non-existent inventory item '{inv_id}'",
                    ))
        elif isinstance(entity, Location):
            for conn_id in entity.connected_locations:
                if conn_id not in location_ids:
                    errors.append(MigrationValidationIssue(
                        entity_id=entity.id,
                        file_path="",
                        severity="error",
                        message=f"Location '{entity.id}' references non-existent connected location '{conn_id}'",
                    ))
        elif isinstance(entity, Scene):
            if entity.location_id is not None and entity.location_id not in location_ids:
                errors.append(MigrationValidationIssue(
                    entity_id=entity.id,
                    file_path="",
                    severity="error",
                    message=f"Scene '{entity.id}' references non-existent location '{entity.location_id}'",
                ))
        elif isinstance(entity, Event):
            if entity.scene_id not in scene_ids:
                errors.append(MigrationValidationIssue(
                    entity_id=entity.id,
                    file_path="",
                    severity="error",
                    message=f"Event '{entity.id}' references non-existent scene '{entity.scene_id}'",
                ))

    # Step 4: Check required entity fields
    for entity in parse_result.entities:
        if not entity.id:
            errors.append(MigrationValidationIssue(
                entity_id=entity.id or None,
                file_path="",
                severity="error",
                message=f"Entity has empty id (name='{entity.name}')",
            ))
        if not entity.name:
            errors.append(MigrationValidationIssue(
                entity_id=entity.id or None,
                file_path="",
                severity="error",
                message=f"Entity '{entity.id}' has empty name",
            ))

    # Step 5: Check memory references
    valid_memory_types = {mt.value for mt in MemoryType}
    for mem in parse_result.memories:
        # Required fields
        if not getattr(mem, "id", None):
            errors.append(MigrationValidationIssue(
                entity_id=None,
                file_path="",
                severity="error",
                message=f"Memory has empty id",
            ))
        if not getattr(mem, "content", None):
            errors.append(MigrationValidationIssue(
                entity_id=getattr(mem, "id", None) or None,
                file_path="",
                severity="error",
                message=f"Memory '{getattr(mem, 'id', '')}' has empty content",
            ))
        if not getattr(mem, "target_id", None):
            errors.append(MigrationValidationIssue(
                entity_id=getattr(mem, "id", None) or None,
                file_path="",
                severity="error",
                message=f"Memory '{getattr(mem, 'id', '')}' has empty target_id",
            ))

        # memory_type validation
        mem_type = getattr(mem, "memory_type", None)
        mem_type_val = mem_type.value if isinstance(mem_type, MemoryType) else mem_type
        if mem_type_val not in valid_memory_types:
            errors.append(MigrationValidationIssue(
                entity_id=getattr(mem, "id", None) or None,
                file_path="",
                severity="error",
                message=f"Memory '{getattr(mem, 'id', '')}' has invalid memory_type '{mem_type_val}'",
            ))

        # Reference checks
        owner_id = getattr(mem, "owner_id", None)
        if owner_id is not None and owner_id not in entity_ids:
            errors.append(MigrationValidationIssue(
                entity_id=getattr(mem, "id", None) or None,
                file_path="",
                severity="error",
                message=f"Memory '{getattr(mem, 'id', '')}' references non-existent owner '{owner_id}'",
            ))

        target_id = getattr(mem, "target_id", None)
        if target_id and target_id not in entity_ids:
            errors.append(MigrationValidationIssue(
                entity_id=getattr(mem, "id", None) or None,
                file_path="",
                severity="error",
                message=f"Memory '{getattr(mem, 'id', '')}' references non-existent target '{target_id}'",
            ))

    # Step 6: Add data-loss warning
    warnings.append(MigrationValidationIssue(
        entity_id=None,
        file_path="",
        severity="warning",
        message="Importing will drop the existing graph and regenerate all embeddings. This operation cannot be undone.",
    ))

    # Step 7: Carry forward parse errors and warnings
    errors.extend(parse_result.errors)
    warnings.extend(parse_result.warnings)

    # Step 8: Build entity counts
    type_counts: Counter[str] = Counter()
    for entity in parse_result.entities:
        type_counts[type(entity).__name__] += 1

    return MigrationValidationReport(
        valid=len(errors) == 0,
        entities_found=len(parse_result.entities),
        memories_found=len(parse_result.memories),
        entity_counts=dict(type_counts),
        errors=errors,
        warnings=warnings,
    )
