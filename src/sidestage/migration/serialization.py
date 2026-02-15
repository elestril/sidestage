"""Canonical frontmatter serialization for campaign migration.

Converts entities and memories to/from YAML frontmatter dict + markdown body
format. Also provides filename sanitization and type-to-subdirectory mapping.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from sidestage.memory.models import Memory
from sidestage.models import (
    CharacterModel,
    EntityModel,
    EventModel,
    EventType,
    ItemModel,
    LocationModel,
    SceneModel,
)

TYPE_MAP: dict[str, type[EntityModel]] = {
    "Character": CharacterModel,
    "Location": LocationModel,
    "Item": ItemModel,
    "Scene": SceneModel,
    "Event": EventModel,
    "ChatMessage": EventModel,
    "JoinEvent": EventModel,
    "LeaveEvent": EventModel,
    "AdjustGametime": EventModel,
    "Error": EventModel,
}

TYPE_TO_SUBDIR: dict[str, str] = {
    "Character": "characters",
    "Location": "locations",
    "Item": "items",
    "Scene": "scenes",
    "Event": "events",
    "ChatMessage": "events",
    "JoinEvent": "events",
    "LeaveEvent": "events",
    "AdjustGametime": "events",
    "Error": "events",
}

SUBDIR_TO_DEFAULT_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}

_PRIORITY_KEYS = ["name", "id", "type"]


def entity_to_frontmatter_dict(entity: EntityModel) -> tuple[dict[str, Any], str]:
    """Convert entity to (frontmatter_dict, body_markdown)."""
    data = entity.model_dump(mode="json")
    body = data.pop("body", "")
    data["type"] = entity.entity_type

    # Exclude messages from Scene (stored as chatlog.log)
    if isinstance(entity, SceneModel):
        data.pop("messages", None)

    # Build ordered dict: name, id, type first, then remaining sorted
    ordered = OrderedDict()
    for key in _PRIORITY_KEYS:
        if key in data:
            ordered[key] = data.pop(key)
    for key in sorted(data.keys()):
        ordered[key] = data[key]

    return ordered, body


def frontmatter_dict_to_entity(
    data: dict[str, Any], body: str, type_hint: str | None = None
) -> EntityModel:
    """Reconstruct entity from frontmatter dict + body."""
    data = dict(data)  # copy to avoid mutating caller's dict

    type_name = data.pop("type", None)
    if type_name is None:
        if type_hint and type_hint in SUBDIR_TO_DEFAULT_TYPE:
            type_name = SUBDIR_TO_DEFAULT_TYPE[type_hint]
        else:
            raise ValueError(
                f"Cannot determine entity type: no 'type' field and no valid type_hint (got {type_hint!r})"
            )

    model_cls = TYPE_MAP.get(type_name)
    if model_cls is None:
        raise ValueError(f"Unknown entity type: {type_name!r}")

    # If type_name is an EventType value, ensure event_type is set
    if model_cls is EventModel and "event_type" not in data:
        event_type_values = {et.value for et in EventType}
        if type_name in event_type_values:
            data["event_type"] = type_name

    data["body"] = body
    return model_cls(**data)


def memory_to_frontmatter_dict(memory: Memory) -> tuple[dict[str, Any], str]:
    """Convert memory to (frontmatter_dict, content_body)."""
    data = memory.model_dump(mode="json")
    content = data.pop("content")
    data.pop("embedding", None)
    return data, content


def frontmatter_dict_to_memory(data: dict[str, Any], body: str) -> Memory:
    """Reconstruct memory from frontmatter dict + body."""
    data = dict(data)
    data["content"] = body
    data.pop("embedding", None)
    return Memory(**data)


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    result = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    result = re.sub(r"_+", "_", result)
    result = result.strip("_")
    return result if result else "_unnamed"


def entity_type_to_subdir(type_name: str) -> str:
    """Map an entity type name to its directory name."""
    subdir = TYPE_TO_SUBDIR.get(type_name)
    if subdir is None:
        raise ValueError(f"Unknown entity type: {type_name!r}")
    return subdir


def resolve_filename(stem: str, used: set[str]) -> str:
    """Resolve filename collisions by appending _2, _3, etc."""
    if stem not in used:
        used.add(stem)
        return stem
    n = 2
    while f"{stem}_{n}" in used:
        n += 1
    result = f"{stem}_{n}"
    used.add(result)
    return result
