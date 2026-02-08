"""Parse markdown/ directory tree into entities, memories, and chat logs."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from sidestage.memory.models import Memory
from sidestage.migration.models import MigrationValidationIssue, ParseResult
from sidestage.migration.serialization import (
    frontmatter_dict_to_entity,
    frontmatter_dict_to_memory,
)
from sidestage.schemas import Entity

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

SUBDIR_TO_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}


def _parse_frontmatter(content: str, file_path: str) -> tuple[dict[str, Any], str] | None:
    """Split markdown content into (frontmatter_dict, body).

    Returns None if the content has no valid frontmatter.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None
    raw_yaml, body = match.group(1), match.group(2).strip()
    data = yaml.safe_load(raw_yaml)
    if not isinstance(data, dict):
        raise yaml.YAMLError(f"Frontmatter is not a mapping in {file_path}")
    return data, body


def _parse_entity_file(
    file_path: Path,
    subdir_type: str,
    errors: list[MigrationValidationIssue],
    warnings: list[MigrationValidationIssue],
) -> Entity | None:
    """Parse a single entity .md file. Returns entity or None on failure."""
    path_str = str(file_path)
    content = file_path.read_text()

    try:
        result = _parse_frontmatter(content, path_str)
    except yaml.YAMLError as exc:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message=f"Malformed YAML: {exc}",
        ))
        return None

    if result is None:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message="Missing YAML frontmatter",
        ))
        return None

    data, body = result

    # Type inference
    if "type" not in data:
        inferred = SUBDIR_TO_TYPE.get(subdir_type)
        if inferred:
            data["type"] = inferred
            warnings.append(MigrationValidationIssue(
                file_path=path_str, severity="warning",
                message=f"Type field missing, inferred as {inferred} from subdirectory.",
            ))
        # If subdir_type not recognized, let frontmatter_dict_to_entity handle it

    # Strip messages from Scene frontmatter
    type_name = data.get("type", "")
    if type_name == "Scene":
        data.pop("messages", None)

    # Use type_hint for subdirectory-based fallback in serialization
    type_hint = subdir_type if "type" not in data else None

    try:
        entity = frontmatter_dict_to_entity(data, body, type_hint=type_hint)
    except Exception as exc:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message=f"Failed to construct entity: {exc}",
        ))
        return None

    return entity


def _parse_memory_file(
    file_path: Path,
    errors: list[MigrationValidationIssue],
) -> Memory | None:
    """Parse a single memory .md file from a .d/ directory."""
    path_str = str(file_path)
    content = file_path.read_text()

    try:
        result = _parse_frontmatter(content, path_str)
    except yaml.YAMLError as exc:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message=f"Malformed YAML: {exc}",
        ))
        return None

    if result is None:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message="Missing YAML frontmatter",
        ))
        return None

    data, body = result

    try:
        return frontmatter_dict_to_memory(data, body)
    except Exception as exc:
        errors.append(MigrationValidationIssue(
            file_path=path_str, severity="error",
            message=f"Failed to construct memory: {exc}",
        ))
        return None


def _read_chatlog(file_path: Path) -> list[str]:
    """Read chatlog.log and return non-empty lines."""
    return [line for line in file_path.read_text().splitlines() if line.strip()]


def parse_directory(markdown_dir: Path) -> ParseResult:
    """Parse the markdown/ directory tree into entities, memories, and chat logs.

    Reads all type subdirectories (characters/, locations/, items/, scenes/,
    events/), parses .md files as entities, reads .d/ companion directories
    for memories and chat logs.

    Args:
        markdown_dir: Path to the markdown/ directory.

    Returns:
        ParseResult with parsed entities, memories, chatlogs, and any
        errors/warnings encountered during parsing. Never raises exceptions
        for bad input -- all issues are reported in the result.
    """
    errors: list[MigrationValidationIssue] = []
    warnings: list[MigrationValidationIssue] = []
    entities: list[Entity] = []
    memories: list[Memory] = []
    chatlogs: dict[str, list[str]] = {}

    # entity ID -> index in entities list, for duplicate detection
    seen_ids: dict[str, str] = {}
    id_to_index: dict[str, int] = {}
    # (subdir, file_stem) -> (entity_id, entity_type_name), for .d/ association
    stem_to_entity: dict[tuple[str, str], tuple[str, str]] = {}

    # Step 1 & 2: Parse entity files from each type subdirectory
    for subdir_name in SUBDIR_TO_TYPE:
        subdir_path = markdown_dir / subdir_name
        if not subdir_path.is_dir():
            continue

        for md_file in sorted(subdir_path.glob("*.md")):
            if not md_file.is_file():
                continue

            entity = _parse_entity_file(md_file, subdir_name, errors, warnings)
            if entity is None:
                continue

            entity_id = entity.id
            file_str = str(md_file)

            # Duplicate ID check
            if entity_id in seen_ids:
                warnings.append(MigrationValidationIssue(
                    entity_id=entity_id, file_path=file_str, severity="warning",
                    message=f"Duplicate entity ID '{entity_id}', previously in {seen_ids[entity_id]}. Last-wins.",
                ))
                # Replace previous entity
                entities[id_to_index[entity_id]] = entity
            else:
                id_to_index[entity_id] = len(entities)
                entities.append(entity)

            seen_ids[entity_id] = file_str
            stem_to_entity[(subdir_name, md_file.stem)] = (entity_id, type(entity).__name__)

    # Step 3: Parse companion .d/ directories
    for subdir_name in SUBDIR_TO_TYPE:
        subdir_path = markdown_dir / subdir_name
        if not subdir_path.is_dir():
            continue

        for entry in sorted(subdir_path.iterdir()):
            if not entry.is_dir() or not entry.name.endswith(".d"):
                continue

            stem = entry.name[:-2]  # strip .d
            entity_info = stem_to_entity.get((subdir_name, stem))

            if entity_info is None:
                warnings.append(MigrationValidationIssue(
                    file_path=str(entry), severity="warning",
                    message=f"Orphaned .d/ directory: {entry.name} has no matching entity file.",
                ))
                entity_id = None
                entity_type_name = None
            else:
                entity_id, entity_type_name = entity_info

            # Parse memory .md files in .d/
            for mem_file in sorted(entry.glob("*.md")):
                if not mem_file.is_file():
                    continue
                mem = _parse_memory_file(mem_file, errors)
                if mem is not None:
                    memories.append(mem)

            # Handle chatlog.log
            chatlog_path = entry / "chatlog.log"
            if chatlog_path.is_file():
                if entity_type_name == "Scene" and entity_id is not None:
                    chatlogs[entity_id] = _read_chatlog(chatlog_path)
                else:
                    warnings.append(MigrationValidationIssue(
                        file_path=str(chatlog_path), severity="warning",
                        message=f"chatlog.log found in non-scene .d/ directory '{entry.name}', ignoring.",
                    ))

    return ParseResult(
        entities=entities,
        memories=memories,
        chatlogs=chatlogs,
        errors=errors,
        warnings=warnings,
    )
