Now I have all the context needed. Let me generate the section content.

# Section 02: Serialization

## Overview

This section creates `src/sidestage/migration/serialization.py` -- the canonical frontmatter serialization layer that converts entities and memories to/from YAML frontmatter + markdown body format. It also provides filename sanitization and type-to-subdirectory mapping utilities. This module is the shared foundation used by both the exporter (backup) and parser (import) in later sections.

### Dependencies

- **section-01-data-models**: Provides `migration/__init__.py` and `migration/models.py` with `ParseResult` and other Pydantic models. Must be implemented first.

### What This Section Produces

- **Implementation file**: `/home/harald/src/sidestage/src/sidestage/migration/serialization.py`
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_serialization.py`

---

## Background: Existing Serialization

The codebase already has entity-to-markdown serialization in `/home/harald/src/sidestage/src/sidestage/entities.py`:

```python
def entity_to_markdown(entity: Entity) -> str:
    """Serializes an Entity to Markdown with YAML frontmatter."""
    data = entity.model_dump()
    body = data.pop("body", "")
    data["type"] = entity.__class__.__name__
    ordered_data = {}
    for key in ["name", "id", "type"]:
        if key in data:
            ordered_data[key] = data.pop(key)
    ordered_data.update(data)
    frontmatter = yaml.dump(ordered_data, sort_keys=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}"

def markdown_to_entity(content: str, override_id: Optional[str] = None) -> Entity:
    """Parses Markdown with YAML frontmatter into an Entity."""
    # Regex to split frontmatter from body
    # Uses type_map for Character, Location, Item, Scene, Event, Entity
```

The new serialization module builds on this pattern but with important differences:
1. Returns structured `(dict, body)` tuples instead of a rendered string, separating data from formatting
2. Covers all entity subtypes including `ChatMessage`, `JoinEvent`, `LeaveEvent`, `FastForwardEvent`
3. Also handles `Memory` models (excluding the `embedding` field)
4. Provides utility functions for filename sanitization and type-to-subdirectory mapping
5. The old functions in `entities.py` remain for backward compatibility; the new migration module uses the new unified functions

### Entity Models Reference

All entity models live in `/home/harald/src/sidestage/src/sidestage/schemas.py`:

- **Entity** (base): `name: str`, `body: str`, `id: str`
- **Item** extends Entity (no extra fields)
- **Location** extends Entity: `connected_locations: list[str]` (default `[]`)
- **Character** extends Entity: `unseen: bool` (default `False`), `location_id: str | None`, `inventory: list[str]` (default `[]`)
- **Event** extends Entity: `scene_id: str`, `gametime: int`, `walltime: str`
- **ChatMessage** extends Event: `character_id: str`, `actor_id: str | None`, `message: str`, `widget: dict | None`
- **JoinEvent** extends Event: `actor_id: str`
- **LeaveEvent** extends Event: `actor_id: str`
- **FastForwardEvent** extends Event: `duration_str: str`
- **Scene** extends Entity: `current_gametime: int | None`, `location_id: str | None`, `events: list[str]` (default `[]`), `messages: list[ChatMessage]` (default `[]`)

### Memory Model Reference

The Memory model lives in `/home/harald/src/sidestage/src/sidestage/memory/models.py`:

```python
class MemoryType(str, Enum):
    SCENE = "scene"
    CHARACTER = "character"
    WORLD_FACT = "world_fact"

class Memory(BaseModel):
    id: str
    content: str
    memory_type: MemoryType
    visibility: str
    embedding: list[float] | None = None
    owner_id: str | None = None
    target_id: str
    created_at: float
    updated_at: float
    gametime: int | None = None
    access_count: int = 0
    last_accessed_at: float | None = None
```

### Type-to-Subdirectory Mapping

| Entity Type | Subdirectory |
|---|---|
| Character | `characters/` |
| Location | `locations/` |
| Item | `items/` |
| Scene | `scenes/` |
| Event, ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent | `events/` |

### Type Map for Deserialization

The type discriminator string in YAML frontmatter must map to the correct Pydantic model class. The complete map:

```python
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
```

The existing `entities.py` type map only covers Character, Location, Item, Scene, Event, Entity -- the new one must include all Event subtypes.

### Subdirectory-to-Type Inference

When the `type` field is missing from frontmatter, the parser (section-04) infers the type from the subdirectory name. The serialization module provides the reverse mapping:

```python
SUBDIR_TO_DEFAULT_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}
```

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_serialization.py`. Tests use `pytest` and cover roundtrip fidelity for all entity types and memories, field ordering, type inference, error handling, and filename utilities.

```python
"""Tests for migration/serialization.py -- canonical frontmatter serialization."""

import pytest

from sidestage.schemas import (
    Character,
    ChatMessage,
    Event,
    FastForwardEvent,
    Item,
    JoinEvent,
    LeaveEvent,
    Location,
    Scene,
)
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.serialization import (
    entity_to_frontmatter_dict,
    frontmatter_dict_to_entity,
    memory_to_frontmatter_dict,
    frontmatter_dict_to_memory,
    sanitize_filename,
    entity_type_to_subdir,
    resolve_filename,
)


# --- entity_to_frontmatter_dict tests ---


def test_entity_to_frontmatter_dict_character_all_fields():
    """entity_to_frontmatter_dict returns (dict, body) for Character with all fields populated."""
    char = Character(
        id="char_eldric",
        name="Eldric the Bold",
        body="A brave warrior.",
        location_id="loc_tavern",
        inventory=["item_sword"],
        unseen=False,
    )
    fm, body = entity_to_frontmatter_dict(char)
    assert body == "A brave warrior."
    assert fm["name"] == "Eldric the Bold"
    assert fm["id"] == "char_eldric"
    assert fm["type"] == "Character"
    assert fm["location_id"] == "loc_tavern"
    assert fm["inventory"] == ["item_sword"]
    assert "body" not in fm


def test_entity_to_frontmatter_dict_location_with_connected():
    """entity_to_frontmatter_dict returns (dict, body) for Location with connected_locations."""
    loc = Location(
        id="loc_tavern",
        name="Rusty Tavern",
        body="A dingy tavern.",
        connected_locations=["loc_castle", "loc_square"],
    )
    fm, body = entity_to_frontmatter_dict(loc)
    assert fm["type"] == "Location"
    assert fm["connected_locations"] == ["loc_castle", "loc_square"]
    assert body == "A dingy tavern."


def test_entity_to_frontmatter_dict_item_minimal():
    """entity_to_frontmatter_dict returns (dict, body) for Item with minimal fields."""
    item = Item(id="item_sword", name="Sword", body="Sharp.")
    fm, body = entity_to_frontmatter_dict(item)
    assert fm["type"] == "Item"
    assert fm["id"] == "item_sword"
    assert body == "Sharp."


def test_entity_to_frontmatter_dict_scene_excludes_messages():
    """entity_to_frontmatter_dict excludes messages list from Scene frontmatter."""
    scene = Scene(
        id="scene_brawl",
        name="Tavern Brawl",
        body="A brawl breaks out.",
        location_id="loc_tavern",
        messages=[],
    )
    fm, body = entity_to_frontmatter_dict(scene)
    assert fm["type"] == "Scene"
    assert "messages" not in fm


def test_entity_to_frontmatter_dict_event_subtypes():
    """entity_to_frontmatter_dict handles ChatMessage and JoinEvent subtypes."""
    chat = ChatMessage(
        id="evt_chat_1",
        name="Chat",
        body="",
        scene_id="scene_brawl",
        gametime=100,
        walltime="2026-01-15T14:30:00Z",
        character_id="char_eldric",
        message="Hello!",
    )
    fm, body = entity_to_frontmatter_dict(chat)
    assert fm["type"] == "ChatMessage"
    assert fm["character_id"] == "char_eldric"
    assert fm["message"] == "Hello!"

    join = JoinEvent(
        id="evt_join_1",
        name="Join",
        body="",
        scene_id="scene_brawl",
        gametime=50,
        walltime="2026-01-15T14:29:00Z",
        actor_id="actor_1",
    )
    fm_j, body_j = entity_to_frontmatter_dict(join)
    assert fm_j["type"] == "JoinEvent"
    assert fm_j["actor_id"] == "actor_1"


def test_entity_to_frontmatter_dict_matches_model_dump_plus_type():
    """Frontmatter dict is identical to model_dump() + type, minus body."""
    char = Character(
        id="char_test",
        name="Test",
        body="Body text.",
        location_id="loc_1",
        inventory=["item_a"],
        unseen=True,
    )
    fm, body = entity_to_frontmatter_dict(char)
    expected = char.model_dump()
    expected.pop("body")
    expected["type"] = "Character"
    # Same key-value pairs, ignoring ordering
    assert dict(fm) == expected


def test_entity_to_frontmatter_dict_field_ordering():
    """Field ordering is deterministic: name, id, type first, then remaining."""
    char = Character(
        id="char_test",
        name="Test",
        body="Body.",
        location_id="loc_1",
        inventory=[],
    )
    fm, _ = entity_to_frontmatter_dict(char)
    keys = list(fm.keys())
    assert keys[0] == "name"
    assert keys[1] == "id"
    assert keys[2] == "type"


# --- frontmatter_dict_to_entity tests ---


def test_frontmatter_dict_to_entity_character():
    """frontmatter_dict_to_entity reconstructs Character from dict + body."""
    data = {
        "name": "Eldric",
        "id": "char_eldric",
        "type": "Character",
        "location_id": "loc_tavern",
        "inventory": ["item_sword"],
        "unseen": False,
    }
    entity = frontmatter_dict_to_entity(data, "A brave warrior.")
    assert isinstance(entity, Character)
    assert entity.name == "Eldric"
    assert entity.body == "A brave warrior."
    assert entity.location_id == "loc_tavern"


def test_frontmatter_dict_to_entity_location_connected():
    """frontmatter_dict_to_entity reconstructs Location with connected_locations."""
    data = {
        "name": "Tavern",
        "id": "loc_tavern",
        "type": "Location",
        "connected_locations": ["loc_castle"],
    }
    entity = frontmatter_dict_to_entity(data, "A tavern.")
    assert isinstance(entity, Location)
    assert entity.connected_locations == ["loc_castle"]


def test_frontmatter_dict_to_entity_infers_type_from_subdir():
    """When type field missing, infers from subdirectory hint."""
    data = {"name": "Sword", "id": "item_sword"}
    entity = frontmatter_dict_to_entity(data, "Sharp.", type_hint="items")
    assert isinstance(entity, Item)


def test_frontmatter_dict_to_entity_raises_on_unknown_type():
    """Raises ValueError on unknown type string."""
    data = {"name": "X", "id": "x_1", "type": "UnknownType"}
    with pytest.raises((ValueError, KeyError)):
        frontmatter_dict_to_entity(data, "")


def test_frontmatter_dict_to_entity_raises_on_missing_required():
    """Raises on missing required fields (id, name)."""
    data = {"type": "Character"}  # missing name and id
    with pytest.raises(Exception):
        frontmatter_dict_to_entity(data, "body")


# --- memory_to_frontmatter_dict tests ---


def test_memory_to_frontmatter_dict_excludes_embedding():
    """memory_to_frontmatter_dict excludes embedding field."""
    mem = Memory(
        id="mem_1",
        content="A fact.",
        memory_type=MemoryType.WORLD_FACT,
        visibility="common",
        target_id="loc_tavern",
        embedding=[0.1, 0.2, 0.3],
    )
    fm, content = memory_to_frontmatter_dict(mem)
    assert "embedding" not in fm
    assert content == "A fact."


def test_memory_to_frontmatter_dict_includes_all_fields():
    """memory_to_frontmatter_dict includes all Memory fields except embedding and content."""
    mem = Memory(
        id="mem_2",
        content="Something happened.",
        memory_type=MemoryType.SCENE,
        visibility="private",
        owner_id="char_eldric",
        target_id="scene_brawl",
        gametime=3600,
        access_count=5,
    )
    fm, content = memory_to_frontmatter_dict(mem)
    assert fm["id"] == "mem_2"
    assert fm["memory_type"] == "scene"
    assert fm["visibility"] == "private"
    assert fm["owner_id"] == "char_eldric"
    assert fm["target_id"] == "scene_brawl"
    assert fm["gametime"] == 3600
    assert fm["access_count"] == 5
    assert "content" not in fm
    assert content == "Something happened."


def test_frontmatter_dict_to_memory_reconstructs():
    """frontmatter_dict_to_memory reconstructs Memory from dict + body."""
    data = {
        "id": "mem_1",
        "memory_type": "world_fact",
        "visibility": "common",
        "target_id": "loc_tavern",
        "owner_id": None,
        "gametime": None,
        "access_count": 0,
        "created_at": 1706000000.0,
        "updated_at": 1706000000.0,
    }
    mem = frontmatter_dict_to_memory(data, "A fact about the tavern.")
    assert isinstance(mem, Memory)
    assert mem.content == "A fact about the tavern."
    assert mem.memory_type == MemoryType.WORLD_FACT
    assert mem.embedding is None


def test_memory_roundtrip():
    """Full roundtrip: Memory -> frontmatter_dict -> Memory preserves all fields."""
    original = Memory(
        id="mem_rt",
        content="Roundtrip content.",
        memory_type=MemoryType.CHARACTER,
        visibility="private",
        owner_id="char_1",
        target_id="char_2",
        gametime=7200,
        access_count=3,
        created_at=1706000000.0,
        updated_at=1706001000.0,
    )
    fm, content = memory_to_frontmatter_dict(original)
    restored = frontmatter_dict_to_memory(fm, content)
    assert restored.id == original.id
    assert restored.content == original.content
    assert restored.memory_type == original.memory_type
    assert restored.visibility == original.visibility
    assert restored.owner_id == original.owner_id
    assert restored.target_id == original.target_id
    assert restored.gametime == original.gametime
    assert restored.access_count == original.access_count
    assert restored.embedding is None


# --- Full entity roundtrip tests ---


def test_entity_roundtrip_all_types():
    """Full roundtrip entity -> frontmatter_dict -> entity for all entity types."""
    entities = [
        Character(id="c1", name="C", body="B", location_id="l1", inventory=["i1"]),
        Location(id="l1", name="L", body="B", connected_locations=["l2"]),
        Item(id="i1", name="I", body="B"),
        Scene(id="s1", name="S", body="B", location_id="l1"),
        Event(id="e1", name="E", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z"),
        JoinEvent(id="j1", name="J", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z", actor_id="a1"),
    ]
    for original in entities:
        fm, body = entity_to_frontmatter_dict(original)
        restored = frontmatter_dict_to_entity(fm, body)
        assert type(restored) is type(original)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.body == original.body


# --- Filename sanitization tests ---


def test_sanitize_filename_replaces_special_chars():
    """Special characters replaced with underscore."""
    assert sanitize_filename("Hello World!") == "Hello_World_"


def test_sanitize_filename_collapses_multiple_underscores():
    """Multiple consecutive underscores collapse to one."""
    assert sanitize_filename("a  b!!c") == "a_b_c"


def test_sanitize_filename_preserves_hyphens_and_underscores():
    """Hyphens and underscores pass through."""
    assert sanitize_filename("my-entity_name") == "my-entity_name"


def test_sanitize_filename_handles_empty_string():
    """Empty string produces a fallback name."""
    result = sanitize_filename("")
    assert len(result) > 0  # Should not be empty


# --- entity_type_to_subdir tests ---


def test_entity_type_to_subdir_mapping():
    """Maps entity type names to correct subdirectories."""
    assert entity_type_to_subdir("Character") == "characters"
    assert entity_type_to_subdir("Location") == "locations"
    assert entity_type_to_subdir("Item") == "items"
    assert entity_type_to_subdir("Scene") == "scenes"
    assert entity_type_to_subdir("Event") == "events"


def test_entity_type_to_subdir_event_subtypes():
    """Event subtypes all map to events/."""
    assert entity_type_to_subdir("ChatMessage") == "events"
    assert entity_type_to_subdir("JoinEvent") == "events"
    assert entity_type_to_subdir("LeaveEvent") == "events"
    assert entity_type_to_subdir("FastForwardEvent") == "events"


# --- resolve_filename tests ---


def test_resolve_filename_no_collision():
    """Returns original name when no collision."""
    used: set[str] = set()
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity"


def test_resolve_filename_appends_suffix_on_collision():
    """Appends _2, _3 on collision."""
    used = {"MyEntity"}
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity_2"

    used.add("MyEntity_2")
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity_3"
```

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/migration/serialization.py`

This module provides the canonical serialization layer. It contains six public functions and supporting constants/maps.

### Public API

```python
def entity_to_frontmatter_dict(entity: Entity) -> tuple[dict, str]:
    """Convert entity to (frontmatter_dict, body_markdown).

    The frontmatter_dict is the canonical representation -- identical
    to what model_dump() produces plus a 'type' discriminator field,
    minus the 'body' field. For Scene entities, the 'messages' field
    is also excluded (messages are stored separately as chat logs).

    Field ordering is deterministic: name, id, type first, then
    remaining fields in alphabetical order. The returned dict is
    an OrderedDict to preserve this ordering for YAML serialization.

    Args:
        entity: Any Entity subclass instance.

    Returns:
        Tuple of (frontmatter_dict, body_string).
    """
```

```python
def frontmatter_dict_to_entity(data: dict, body: str, type_hint: str | None = None) -> Entity:
    """Reconstruct entity from frontmatter dict + body.

    Inverse of entity_to_frontmatter_dict. The 'type' field in data
    determines which Pydantic model class to instantiate. If 'type'
    is missing, falls back to type_hint (a subdirectory name like
    'characters') mapped via SUBDIR_TO_DEFAULT_TYPE.

    Args:
        data: The frontmatter dict (will be modified -- 'type' key removed).
        body: The markdown body text.
        type_hint: Optional subdirectory name for type inference when
                   'type' field is missing from data.

    Returns:
        An Entity subclass instance.

    Raises:
        ValueError: If type cannot be determined or is unknown.
        ValidationError: If required Pydantic fields are missing.
    """
```

```python
def memory_to_frontmatter_dict(memory: Memory) -> tuple[dict, str]:
    """Convert memory to (frontmatter_dict, content_body).

    Excludes 'embedding' field (regenerated at runtime, not stored on disk).
    Excludes 'content' field (becomes the markdown body).
    The MemoryType enum is serialized as its string value.

    Args:
        memory: A Memory instance.

    Returns:
        Tuple of (frontmatter_dict, content_string).
    """
```

```python
def frontmatter_dict_to_memory(data: dict, body: str) -> Memory:
    """Reconstruct memory from frontmatter dict + body.

    Inverse of memory_to_frontmatter_dict. Sets content from body,
    leaves embedding as None.

    Args:
        data: The frontmatter dict.
        body: The markdown body (becomes memory.content).

    Returns:
        A Memory instance with embedding=None.
    """
```

```python
def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Replaces any character that is not alphanumeric, hyphen, or
    underscore with an underscore. Collapses consecutive underscores
    into a single one. Strips leading/trailing underscores.

    If the result is empty, returns '_unnamed'.

    Args:
        name: The raw string (typically entity.name or memory.id).

    Returns:
        A filesystem-safe filename stem (without extension).
    """
```

```python
def entity_type_to_subdir(type_name: str) -> str:
    """Map an entity type name to its directory name.

    Args:
        type_name: The class name string (e.g., 'Character', 'ChatMessage').

    Returns:
        The subdirectory name (e.g., 'characters', 'events').

    Raises:
        ValueError: If the type name is not recognized.
    """
```

```python
def resolve_filename(stem: str, used: set[str]) -> str:
    """Resolve filename collisions by appending _2, _3, etc.

    Checks if stem is already in the used set. If so, tries stem_2,
    stem_3, etc. until a unique name is found. Adds the result to
    the used set before returning.

    Args:
        stem: The desired filename stem (without extension).
        used: A mutable set of already-used stems (will be modified).

    Returns:
        A unique filename stem.
    """
```

### Constants and Maps

The module defines these module-level constants:

```python
from collections import OrderedDict

# Type string -> Pydantic model class
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

# Type string -> subdirectory name
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

# Subdirectory name -> default type string (for inference when type field missing)
SUBDIR_TO_DEFAULT_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}

# Priority ordering for frontmatter fields
_PRIORITY_KEYS = ["name", "id", "type"]
```

### Implementation Notes

**entity_to_frontmatter_dict logic:**
1. Call `entity.model_dump()` to get all fields as a dict.
2. Pop `"body"` from the dict -- this becomes the second return value.
3. Add `"type": entity.__class__.__name__` (e.g., `"Character"`, `"ChatMessage"`).
4. For Scene entities, pop `"messages"` from the dict (messages are stored as `chatlog.log`, not in frontmatter).
5. Build an `OrderedDict` with priority keys first (`name`, `id`, `type`), then remaining keys in sorted order.
6. Return `(ordered_dict, body)`.

**frontmatter_dict_to_entity logic:**
1. Make a copy of `data` to avoid mutating the caller's dict.
2. Extract and remove the `"type"` key. If missing, use `type_hint` with `SUBDIR_TO_DEFAULT_TYPE` to infer it.
3. Look up the model class in `TYPE_MAP`. Raise `ValueError` if not found.
4. Set `data["body"] = body`.
5. Instantiate and return `model_cls(**data)`. Pydantic validation handles missing/invalid fields.

**memory_to_frontmatter_dict logic:**
1. Call `memory.model_dump()`.
2. Pop `"content"` -- becomes the body return value.
3. Pop `"embedding"` -- excluded from disk storage.
4. Convert `memory_type` enum to its string value if needed (Pydantic's `model_dump()` with default mode already does this for str enums).
5. Return `(dict, content)`.

**frontmatter_dict_to_memory logic:**
1. Set `data["content"] = body`.
2. Ensure `"embedding"` is not in data (or set to `None`).
3. Instantiate and return `Memory(**data)`.

**sanitize_filename logic:**
1. Replace any character matching `[^a-zA-Z0-9_-]` with `_` using `re.sub`.
2. Collapse consecutive underscores with `re.sub(r'_+', '_', result)`.
3. Strip leading/trailing underscores.
4. If result is empty, return `"_unnamed"`.

**entity_type_to_subdir logic:**
1. Look up `type_name` in `TYPE_TO_SUBDIR`.
2. Raise `ValueError` if not found.

**resolve_filename logic:**
1. If `stem` not in `used`, add it to `used` and return it.
2. Otherwise, try `f"{stem}_{n}"` for `n = 2, 3, 4, ...` until one is not in `used`.
3. Add the result to `used` and return it.

### Imports

```python
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
```

### Key Constraint: Canonical Format = API Format

The frontmatter dict produced by `entity_to_frontmatter_dict()` MUST be identical to what `model_dump()` produces (plus the `type` field, minus `body`). This ensures that an entity serialized to disk in YAML and an entity serialized to JSON for the API carry exactly the same data. The only difference is the serialization format (YAML vs JSON) and that `body` is the markdown section below the frontmatter rather than a dict key.

This means:
- No field renaming, no field omission (except `body` and Scene `messages`)
- Default values are included (e.g., `unseen: false`, `inventory: []`)
- `None` values are included as `null` in YAML

### Relationship to Other Sections

- **section-04-parser** imports `frontmatter_dict_to_entity()`, `frontmatter_dict_to_memory()`, and `SUBDIR_TO_DEFAULT_TYPE` to parse markdown files from disk.
- **section-06-exporter** imports `entity_to_frontmatter_dict()`, `memory_to_frontmatter_dict()`, `sanitize_filename()`, `entity_type_to_subdir()`, and `resolve_filename()` to write markdown files to disk.
- **section-03-test-campaign** uses the canonical format defined here to create test fixture files.