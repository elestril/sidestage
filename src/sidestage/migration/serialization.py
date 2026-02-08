"""Canonical frontmatter serialization for campaign migration.

Converts entities and memories to/from YAML frontmatter dict + markdown body
format. Also provides filename sanitization and type-to-subdirectory mapping.
"""

from __future__ import annotations

import re
from collections import OrderedDict

from sidestage.memory.models import Memory
from sidestage.schemas import (
    Character,
    ChatMessage,
    Entity,
    Event,
    FastForwardEvent,
    Item,
    JoinEvent,
    LeaveEvent,
    Location,
    Scene,
)

TYPE_MAP: dict[str, type[Entity]] = {
    "Character": Character,
    "Location": Location,
    "Item": Item,
    "Scene": Scene,
    "Event": Event,
    "ChatMessage": ChatMessage,
    "JoinEvent": JoinEvent,
    "LeaveEvent": LeaveEvent,
    "FastForwardEvent": FastForwardEvent,
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
    "FastForwardEvent": "events",
}

SUBDIR_TO_DEFAULT_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}

_PRIORITY_KEYS = ["name", "id", "type"]


def entity_to_frontmatter_dict(entity: Entity) -> tuple[dict, str]:
    """Convert entity to (frontmatter_dict, body_markdown)."""
    data = entity.model_dump()
    body = data.pop("body", "")
    data["type"] = entity.__class__.__name__

    # Exclude messages from Scene (stored as chatlog.log)
    if isinstance(entity, Scene):
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
    data: dict, body: str, type_hint: str | None = None
) -> Entity:
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

    data["body"] = body
    return model_cls(**data)


def memory_to_frontmatter_dict(memory: Memory) -> tuple[dict, str]:
    """Convert memory to (frontmatter_dict, content_body)."""
    data = memory.model_dump()
    content = data.pop("content")
    data.pop("embedding", None)
    return data, content


def frontmatter_dict_to_memory(data: dict, body: str) -> Memory:
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
