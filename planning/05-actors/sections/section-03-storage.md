Now I have a thorough understanding of all the context. Let me generate the section content.

# Section 03: Storage and Persistence

This section covers all storage, graph entity, and serialization changes needed to support the flattened EventModel. It updates the graph label system, entity markdown serialization, migration serialization, importer/exporter, SQLite storage, and graph property handling.

**Depends on:** section-01-event-model (EventType enum, Visibility enum, flattened EventModel with `event_type` instance field, `entity_type: ClassVar[str] = "Event"`)

**Blocks:** section-06-orchestrator

---

## Background

The Actor Restructuring plan (05-actors) flattens the four EventModel subclasses (`ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`) into a single `EventModel` with an `event_type: EventType` instance field discriminator. The ClassVar `entity_type` remains `"Event"` for all events.

This section updates every persistence and serialization layer to work with the flattened model:

1. **Graph labels** -- `entity_to_labels()` must inspect `event_type` to generate specific labels like `["Entity", "Event", "ChatMessage"]`
2. **Graph properties** -- `metadata` (dict) must be JSON-serialized, `walltime` (datetime) ISO-serialized, enums stored as strings
3. **Entity markdown** -- `entity_to_markdown()` / `markdown_to_entity()` must include `event_type` in frontmatter
4. **Migration serialization** -- `TYPE_MAP`, `TYPE_TO_SUBDIR`, frontmatter conversion functions updated
5. **Importer** -- `_parse_chatlog_lines` constructs `EventModel` instead of `ChatMessageModel`; `_restore_chatlogs` persists events individually
6. **Exporter** -- chatlog export queries events from storage/graph instead of reading `SceneModel.messages`
7. **SQLite storage** -- event retrieval by scene_id and event_type
8. **Clean break** -- `ConfigDict(extra='ignore')` safety net on EventModel

---

## Tests First

All tests should be written before implementation. The tests below define the expected behavior.

### File: `/home/harald/src/sidestage/tests/unit/test_graph_serialization.py`

This file already exists and tests the graph label/property/node serialization system. It must be rewritten to remove references to the deleted subclasses and test the new `event_type`-driven label system.

```python
"""Unit tests for entity serialization to/from graph node properties."""
import json
import pytest

from sidestage.models import (
    CharacterModel, LocationModel, ItemModel, SceneModel, EventModel,
    EventType, Visibility,
)
from sidestage.graph.entities import (
    LABEL_TO_MODEL,
    MODEL_TO_LABELS,
    EXCLUDED_FIELDS,
    entity_to_labels,
    entity_to_properties,
    node_to_entity,
)


# --- Label Registry ---


def test_label_registry_maps_event_type_values_to_event_model():
    """LABEL_TO_MODEL maps each EventType value string to EventModel class."""
    for et in EventType:
        assert et.value in LABEL_TO_MODEL
        assert LABEL_TO_MODEL[et.value] is EventModel


def test_label_registry_contains_core_entity_types():
    """LABEL_TO_MODEL contains Character, Location, Item, Scene, Event."""
    assert LABEL_TO_MODEL["Character"] is CharacterModel
    assert LABEL_TO_MODEL["Location"] is LocationModel
    assert LABEL_TO_MODEL["Item"] is ItemModel
    assert LABEL_TO_MODEL["Scene"] is SceneModel
    assert LABEL_TO_MODEL["Event"] is EventModel


def test_deleted_subclasses_not_in_registries():
    """ChatMessageModel, JoinEventModel, etc. no longer appear in registries."""
    for name in ["ChatMessageModel", "JoinEventModel", "LeaveEventModel", "FastForwardEventModel"]:
        # These class names should not appear as values in LABEL_TO_MODEL
        for cls in LABEL_TO_MODEL.values():
            assert cls.__name__ != name


# --- entity_to_labels with event_type ---


def test_entity_to_labels_chat_message_event():
    """entity_to_labels for EventModel with CHAT_MESSAGE returns ['Entity', 'Event', 'ChatMessage']."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "ChatMessage"]


def test_entity_to_labels_join_event():
    """entity_to_labels for EventModel with JOIN returns ['Entity', 'Event', 'JoinEvent']."""
    event = EventModel(
        id="e1", name="join", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.JOIN,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "JoinEvent"]


def test_entity_to_labels_leave_event():
    """entity_to_labels for EventModel with LEAVE returns ['Entity', 'Event', 'LeaveEvent']."""
    event = EventModel(
        id="e1", name="leave", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.LEAVE,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "LeaveEvent"]


def test_entity_to_labels_adjust_gametime_event():
    """entity_to_labels for ADJUST_GAMETIME returns ['Entity', 'Event', 'AdjustGametime']."""
    event = EventModel(
        id="e1", name="time", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.ADJUST_GAMETIME,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "AdjustGametime"]


def test_entity_to_labels_error_event():
    """entity_to_labels for ERROR returns ['Entity', 'Event', 'Error']."""
    event = EventModel(
        id="e1", name="Error", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.ERROR,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "Error"]


def test_entity_to_labels_non_event_types_unchanged():
    """entity_to_labels for non-event types still works as before."""
    char = CharacterModel(id="c1", name="Alice", body="desc")
    assert entity_to_labels(char) == ["Entity", "Character"]

    loc = LocationModel(id="l1", name="Tavern", body="desc")
    assert entity_to_labels(loc) == ["Entity", "Location"]

    scene = SceneModel(id="s1", name="Opening", body="desc")
    assert entity_to_labels(scene) == ["Entity", "Scene"]


# --- entity_to_properties: metadata, walltime, enums ---


def test_entity_to_properties_serializes_metadata_as_json_string():
    """metadata dict is serialized as a JSON string in graph properties."""
    event = EventModel(
        id="e1", name="msg", body="hi", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
        metadata={"widget": {"type": "card"}},
    )
    props = entity_to_properties(event)
    assert isinstance(props["metadata"], str)
    assert json.loads(props["metadata"]) == {"widget": {"type": "card"}}


def test_entity_to_properties_empty_metadata_serialized_as_json():
    """Empty metadata dict serialized as '{}' JSON string."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert props["metadata"] == "{}"


def test_entity_to_properties_walltime_as_iso_string():
    """walltime is stored as ISO string in graph properties."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T12:30:00+00:00", event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert isinstance(props["walltime"], str)


def test_entity_to_properties_event_type_as_string():
    """event_type stored as its string value."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert props["event_type"] == "ChatMessage"


def test_entity_to_properties_visibility_as_string():
    """visibility stored as its string value."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
        visibility=Visibility.GM_ONLY,
    )
    props = entity_to_properties(event)
    assert props["visibility"] == "gm_only"


# --- node_to_entity: round-trip ---


def test_node_to_entity_reconstructs_chat_message_event():
    """node_to_entity with ChatMessage label reconstructs EventModel with event_type=CHAT_MESSAGE."""
    labels = ["Entity", "Event", "ChatMessage"]
    properties = {
        "id": "e1", "name": "msg", "body": "hi", "scene_id": "s1",
        "gametime": 100, "walltime": "2024-01-01T00:00:00",
        "event_type": "ChatMessage", "character_id": "c1",
        "metadata": "{}",  "visibility": "public",
    }
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, EventModel)
    assert entity.event_type == EventType.CHAT_MESSAGE


def test_node_to_entity_reconstructs_join_event():
    """node_to_entity with JoinEvent label reconstructs EventModel with event_type=JOIN."""
    labels = ["Entity", "Event", "JoinEvent"]
    properties = {
        "id": "e1", "name": "join", "body": "", "scene_id": "s1",
        "gametime": 100, "walltime": "2024-01-01T00:00:00",
        "event_type": "JoinEvent", "metadata": "{}",
        "visibility": "public",
    }
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, EventModel)
    assert entity.event_type == EventType.JOIN


def test_node_to_entity_deserializes_metadata_from_json_string():
    """node_to_entity parses metadata JSON string back to dict."""
    labels = ["Entity", "Event", "ChatMessage"]
    properties = {
        "id": "e1", "name": "msg", "body": "", "scene_id": "s1",
        "gametime": 100, "walltime": "2024-01-01T00:00:00",
        "event_type": "ChatMessage", "metadata": '{"widget": "poll"}',
        "visibility": "public",
    }
    entity = node_to_entity(labels, properties)
    assert isinstance(entity.metadata, dict)
    assert entity.metadata["widget"] == "poll"


def test_event_model_roundtrip_through_graph_helpers():
    """EventModel survives entity_to_properties -> node_to_entity round-trip."""
    event = EventModel(
        id="e1", name="msg", body="hello", scene_id="s1", gametime=100,
        walltime="2024-01-01T00:00:00", event_type=EventType.CHAT_MESSAGE,
        character_id="c1", visibility=Visibility.PUBLIC,
        metadata={"key": "value"},
    )
    labels = entity_to_labels(event)
    props = entity_to_properties(event)
    restored = node_to_entity(labels, props)
    assert isinstance(restored, EventModel)
    assert restored.event_type == EventType.CHAT_MESSAGE
    assert restored.id == event.id
    assert restored.metadata == {"key": "value"}
```

### File: `/home/harald/src/sidestage/tests/unit/test_entities.py`

Extend with EventModel markdown round-trip tests.

```python
# Add to existing test_entities.py

def test_event_model_markdown_roundtrip():
    """EventModel with event_type survives markdown serialization round-trip."""
    from sidestage.models import EventModel, EventType
    from sidestage.entities import entity_to_markdown, markdown_to_entity

    event = EventModel(
        id="evt_abc123",
        name="Alice Message",
        body="Hello world",
        scene_id="scene_1",
        gametime=3600,
        walltime="2024-06-15T10:30:00Z",
        event_type=EventType.CHAT_MESSAGE,
        character_id="char_alice",
    )
    md = entity_to_markdown(event)
    assert "event_type: ChatMessage" in md
    assert "type: Event" in md

    restored = markdown_to_entity(md)
    assert isinstance(restored, EventModel)
    assert restored.event_type == EventType.CHAT_MESSAGE
    assert restored.character_id == "char_alice"
    assert restored.body == "Hello world"
```

### File: `/home/harald/src/sidestage/tests/unit/test_migration_serialization.py`

Replace subclass-specific tests with flattened EventModel tests.

```python
# Add/replace in existing test_migration_serialization.py

def test_entity_to_frontmatter_dict_event_includes_event_type():
    """entity_to_frontmatter_dict for EventModel includes event_type in frontmatter."""
    from sidestage.models import EventModel, EventType
    event = EventModel(
        id="evt_1", name="Chat", body="hi", scene_id="s1",
        gametime=100, walltime="2026-01-15T14:30:00Z",
        event_type=EventType.CHAT_MESSAGE, character_id="c1",
    )
    fm, body = entity_to_frontmatter_dict(event)
    assert fm["type"] == "Event"
    assert fm["event_type"] == "ChatMessage"


def test_frontmatter_dict_to_entity_event_with_event_type():
    """frontmatter_dict_to_entity handles type='Event' with event_type field."""
    data = {
        "name": "Chat", "id": "evt_1", "type": "Event",
        "event_type": "ChatMessage", "scene_id": "s1",
        "gametime": 100, "walltime": "2026-01-15T14:30:00Z",
        "character_id": "c1", "visibility": "public",
        "metadata": {},
    }
    from sidestage.models import EventModel, EventType
    entity = frontmatter_dict_to_entity(data, "hi")
    assert isinstance(entity, EventModel)
    assert entity.event_type == EventType.CHAT_MESSAGE


def test_type_map_maps_event_type_values_to_event_model():
    """TYPE_MAP maps EventType value strings to EventModel."""
    from sidestage.migration.serialization import TYPE_MAP
    from sidestage.models import EventModel
    for val in ["ChatMessage", "JoinEvent", "LeaveEvent", "AdjustGametime", "Error"]:
        assert TYPE_MAP[val] is EventModel


def test_type_to_subdir_maps_event_types_to_events():
    """TYPE_TO_SUBDIR maps all event type strings to 'events'."""
    from sidestage.migration.serialization import TYPE_TO_SUBDIR
    for val in ["Event", "ChatMessage", "JoinEvent", "LeaveEvent", "AdjustGametime", "Error"]:
        assert TYPE_TO_SUBDIR[val] == "events"


def test_entity_roundtrip_flattened_event():
    """Full roundtrip: EventModel -> frontmatter_dict -> EventModel preserves event_type."""
    from sidestage.models import EventModel, EventType
    original = EventModel(
        id="evt_rt", name="Roundtrip", body="Content",
        scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z",
        event_type=EventType.JOIN, actor_id="a1",
    )
    fm, body = entity_to_frontmatter_dict(original)
    restored = frontmatter_dict_to_entity(fm, body)
    assert type(restored) is EventModel
    assert restored.event_type == EventType.JOIN
    assert restored.actor_id == "a1"
```

### File: `/home/harald/src/sidestage/tests/unit/test_storage.py`

Add event storage tests.

```python
# Add to existing test_storage.py

def test_event_crud(storage):
    """Events can be stored and retrieved by scene_id."""
    from sidestage.models import EventModel, EventType
    event = EventModel(
        id="evt_1", name="Alice Message", body="Hello",
        scene_id="scene_1", gametime=100, walltime="2024-01-01T00:00:00",
        event_type=EventType.CHAT_MESSAGE, character_id="char_alice",
    )
    storage.add_event(event)
    events = storage.list_events_by_scene("scene_1")
    assert len(events) == 1
    assert events[0].id == "evt_1"
    assert events[0].event_type == EventType.CHAT_MESSAGE


def test_list_events_by_scene_and_type(storage):
    """list_events_by_scene filters by event_type when provided."""
    from sidestage.models import EventModel, EventType
    chat = EventModel(
        id="evt_1", name="msg", body="hi", scene_id="s1",
        gametime=100, walltime="2024-01-01T00:00:00",
        event_type=EventType.CHAT_MESSAGE,
    )
    join = EventModel(
        id="evt_2", name="join", body="", scene_id="s1",
        gametime=100, walltime="2024-01-01T00:00:00",
        event_type=EventType.JOIN,
    )
    storage.add_event(chat)
    storage.add_event(join)
    chat_only = storage.list_events_by_scene("s1", event_type=EventType.CHAT_MESSAGE)
    assert len(chat_only) == 1
    assert chat_only[0].event_type == EventType.CHAT_MESSAGE


def test_event_model_extra_ignore(storage):
    """EventModel with extra='ignore' gracefully handles unknown fields from storage."""
    from sidestage.models import EventModel
    # Simulate stale data with an extra 'message' field
    import json
    stale_data = {
        "id": "evt_stale", "name": "old", "body": "", "scene_id": "s1",
        "gametime": 0, "walltime": "2024-01-01T00:00:00",
        "event_type": "ChatMessage", "message": "stale field",
        "metadata": {}, "visibility": "public",
    }
    with __import__('sqlite3').connect(storage.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO events (id, data) VALUES (?, ?)",
            ("evt_stale", json.dumps(stale_data)),
        )
    # Should not raise even with the unknown 'message' field
    event = EventModel.model_validate_json(json.dumps(stale_data))
    assert event.id == "evt_stale"
```

---

## Implementation Details

### 1. Graph Entities (`/home/harald/src/sidestage/src/sidestage/graph/entities.py`)

#### 1.1 Update Imports

Remove imports of deleted subclasses:
- Remove: `ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`
- Add: `EventType` from `sidestage.models`
- Add: `import json` (for metadata serialization)

#### 1.2 Update `LABEL_TO_MODEL`

Replace the per-subclass entries with entries mapping each `EventType.value` string to `EventModel`:

```python
LABEL_TO_MODEL: dict[str, type[EntityModel]] = {
    "ChatMessage": EventModel,
    "JoinEvent": EventModel,
    "LeaveEvent": EventModel,
    "AdjustGametime": EventModel,
    "Error": EventModel,
    "Character": CharacterModel,
    "Location": LocationModel,
    "Item": ItemModel,
    "Scene": SceneModel,
    "Event": EventModel,
}
```

The ordering is still most-specific first so that `node_to_entity()` picks `"ChatMessage"` before the generic `"Event"` label.

#### 1.3 Update `MODEL_TO_LABELS`

Remove per-subclass entries. Keep only the base `EventModel` entry:

```python
MODEL_TO_LABELS: dict[type[EntityModel], list[str]] = {
    CharacterModel: ["Entity", "Character"],
    LocationModel: ["Entity", "Location"],
    ItemModel: ["Entity", "Item"],
    SceneModel: ["Entity", "Scene"],
    EventModel: ["Entity", "Event"],  # base labels only; entity_to_labels() overrides
}
```

#### 1.4 Update `EXCLUDED_FIELDS`

Remove `ChatMessageModel` entry. Remove `SceneModel`'s `"messages"` exclusion (the field no longer exists on SceneModel after section-01). Keep `LocationModel`'s `connected_locations` exclusion:

```python
EXCLUDED_FIELDS: dict[type[EntityModel], set[str]] = {
    LocationModel: {"connected_locations"},
}
```

#### 1.5 Override `entity_to_labels()`

When the entity is an `EventModel`, append `event_type.value` as the most-specific label:

```python
def entity_to_labels(entity: EntityModel) -> list[str]:
    """Return the FalkorDB labels for an entity instance."""
    labels = MODEL_TO_LABELS.get(type(entity), ["Entity"])
    if isinstance(entity, EventModel):
        # Append event_type value as most-specific label
        return labels + [entity.event_type.value]
    return labels
```

This produces `["Entity", "Event", "ChatMessage"]` for a chat message event, preserving query granularity.

#### 1.6 Override `entity_to_properties()`

Handle special serialization for `EventModel` fields:
- **`metadata`**: Serialize `dict` as JSON string via `json.dumps()`
- **`walltime`**: If it is a `datetime` object, call `.isoformat()`. If already a string, keep as-is.
- **`event_type`** and **`visibility`**: These are `str` enums; Pydantic's `model_dump()` already returns their `.value` strings. Confirm this works correctly.

```python
def entity_to_properties(entity: EntityModel) -> dict[str, Any]:
    """Convert a Pydantic entity to a dict of graph node properties."""
    excluded = EXCLUDED_FIELDS.get(type(entity), set())
    props = {}
    for key, value in entity.model_dump().items():
        if key in excluded or value is None:
            continue
        props[key] = value
    # Special handling for EventModel nested/complex types
    if isinstance(entity, EventModel):
        props["metadata"] = json.dumps(entity.metadata)
        if hasattr(entity.walltime, 'isoformat'):
            props["walltime"] = entity.walltime.isoformat()
    return props
```

#### 1.7 Override `node_to_entity()`

When deserializing an Event node, parse the `metadata` JSON string back to a dict before constructing the model:

```python
def node_to_entity(labels: list[str], properties: dict[str, Any]) -> EntityModel:
    """Reconstruct a Pydantic entity from graph node labels and properties."""
    label_set = set(labels)
    for label, model_cls in LABEL_TO_MODEL.items():
        if label in label_set:
            props = dict(properties)
            # Deserialize metadata JSON string for EventModel
            if model_cls is EventModel and "metadata" in props and isinstance(props["metadata"], str):
                props["metadata"] = json.loads(props["metadata"])
            return model_cls(**props)
    raise QueryError(f"Cannot deserialize node with labels {labels}: no matching model")
```

#### 1.8 Rebuild `_ALL_ENTITY_FIELDS`

The `_ALL_ENTITY_FIELDS` set is built from `MODEL_TO_LABELS` keys. Since the deleted subclasses are removed, update the set computation. Also add the new EventModel fields (`event_type`, `character_id`, `actor_id`, `metadata`, `visibility`) to the valid property key set. This happens automatically since `EventModel.model_fields` includes them.

---

### 2. Entity Markdown Serialization (`/home/harald/src/sidestage/src/sidestage/entities.py`)

#### 2.1 `entity_to_markdown()`

For `EventModel` instances, explicitly add `event_type` to the frontmatter. The `type` field stays `"Event"` (from `entity_type` ClassVar). The `event_type` field carries the discriminator:

```python
def entity_to_markdown(entity: EntityModel) -> str:
    """Serializes an Entity to a standardized Markdown format with YAML frontmatter."""
    data = entity.model_dump()
    body = data.pop("body", "")
    data["type"] = entity.entity_type

    # For EventModel, ensure event_type is explicitly in frontmatter
    # (model_dump() already includes it, but confirm it is present)

    ordered_data = {}
    for key in ["name", "id", "type"]:
        if key in data:
            ordered_data[key] = data.pop(key)
    ordered_data.update(data)

    frontmatter = yaml.dump(ordered_data, sort_keys=False).strip()
    return f"---\n{frontmatter}\n---\n\n{body}"
```

The `event_type` field is already included by `model_dump()` since it is an instance field on the flattened `EventModel`. No special handling needed beyond confirming it appears in the output.

#### 2.2 `markdown_to_entity()`

When `type == "Event"`, the `event_type` field is present in the frontmatter dict and gets passed through to the EventModel constructor. Update the `type_map` to remove deleted subclass entries:

```python
type_map: Dict[str, Type[EntityModel]] = {
    "Character": CharacterModel,
    "Location": LocationModel,
    "Item": ItemModel,
    "Scene": SceneModel,
    "Event": EventModel,
    "Entity": EntityModel,
    # Also map EventType value strings for backward compatibility
    "ChatMessage": EventModel,
    "JoinEvent": EventModel,
    "LeaveEvent": EventModel,
    "AdjustGametime": EventModel,
    "Error": EventModel,
}
```

When `type` is an EventType value string (e.g., `"ChatMessage"`) rather than `"Event"`, map it to `EventModel`. The `event_type` field in the frontmatter data populates the discriminator. If `type` matches an EventType value, also set `event_type` in the data dict if not already present:

```python
# After resolving model_cls:
if model_cls is EventModel and "event_type" not in data:
    # type field might be an EventType value (e.g., "ChatMessage")
    if entity_type in [et.value for et in EventType]:
        data["event_type"] = entity_type
```

---

### 3. Migration Serialization (`/home/harald/src/sidestage/src/sidestage/migration/serialization.py`)

#### 3.1 Update Imports

Remove: `ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`
Add: `EventType` from `sidestage.models`

#### 3.2 Update `TYPE_MAP`

```python
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
```

#### 3.3 Update `TYPE_TO_SUBDIR`

```python
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
```

#### 3.4 Update `entity_to_frontmatter_dict()`

For `EventModel`, include `event_type` in the frontmatter. The `type` field should be `"Event"` (from ClassVar), and `event_type` should carry the discriminator value:

```python
def entity_to_frontmatter_dict(entity: EntityModel) -> tuple[dict[str, Any], str]:
    """Convert entity to (frontmatter_dict, body_markdown)."""
    data = entity.model_dump()
    body = data.pop("body", "")
    data["type"] = entity.entity_type

    # SceneModel: remove messages field (no longer exists after section-01,
    # but keep the pop for safety during transition)
    if isinstance(entity, SceneModel):
        data.pop("messages", None)

    ordered = OrderedDict()
    for key in _PRIORITY_KEYS:
        if key in data:
            ordered[key] = data.pop(key)
    for key in sorted(data.keys()):
        ordered[key] = data[key]

    return ordered, body
```

The `event_type` key is already present from `model_dump()` because it is an instance field. It gets placed in the sorted remainder after the priority keys.

#### 3.5 Update `frontmatter_dict_to_entity()`

When `type_name` is an EventType value string, map to `EventModel` and populate `event_type`:

```python
def frontmatter_dict_to_entity(
    data: dict[str, Any], body: str, type_hint: str | None = None
) -> EntityModel:
    """Reconstruct entity from frontmatter dict + body."""
    data = dict(data)
    type_name = data.pop("type", None)
    if type_name is None:
        if type_hint and type_hint in SUBDIR_TO_DEFAULT_TYPE:
            type_name = SUBDIR_TO_DEFAULT_TYPE[type_hint]
        else:
            raise ValueError(...)

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
```

---

### 4. Migration Importer (`/home/harald/src/sidestage/src/sidestage/migration/importer.py`)

#### 4.1 Update Imports

Remove: `ChatMessageModel`
Add: `EventType` from `sidestage.models`
Remove: `SyncManager` from TYPE_CHECKING (it is eliminated)

#### 4.2 Update `import_campaign()` Signature

Remove the `sync_manager` parameter. Post-import broadcast uses `campaign.user.send()` instead (handled in section-06-orchestrator). For now, remove the broadcast call or make it conditional on the presence of a user attribute:

```python
async def import_campaign(
    campaign: Campaign,
    parse_result: ParseResult,
    active_scenes: dict[str, Any] | None = None,
) -> MigrationImportResult:
```

Remove the `if sync_manager is not None: await sync_manager.broadcast(...)` call.

#### 4.3 Update `_parse_chatlog_lines()`

Construct `EventModel` with `event_type=EventType.CHAT_MESSAGE` instead of `ChatMessageModel`. Use `evt_` ID prefix. Map the `message` field to `body`:

```python
def _parse_chatlog_lines(scene_id: str, lines: list[str]) -> list[EventModel]:
    """Parse raw chatlog lines into EventModel objects with event_type=CHAT_MESSAGE."""
    events: list[EventModel] = []
    for line in lines:
        match = _CHATLOG_RE.match(line.strip())
        if not match:
            continue
        walltime, character_id, name, message = match.groups()
        evt = EventModel(
            name=f"{name.strip()} Message",
            body=message,  # message content goes in body
            id=f"evt_{scene_id}_{len(events)}",
            scene_id=scene_id,
            gametime=0,
            walltime=walltime,
            character_id=character_id,
            event_type=EventType.CHAT_MESSAGE,
        )
        events.append(evt)
    return events
```

#### 4.4 Update `_restore_chatlogs()`

Instead of setting `existing.messages = messages` on the SceneModel (the `messages` field no longer exists), persist each event individually to `campaign.storage.add_event()`:

```python
def _restore_chatlogs(
    campaign: Campaign, chatlogs: dict[str, list[str]],
) -> list[str]:
    """Restore chat logs to SQLite storage as individual events."""
    errors: list[str] = []
    for scene_id, lines in chatlogs.items():
        if not lines:
            continue
        try:
            events = _parse_chatlog_lines(scene_id, lines)
            for event in events:
                campaign.storage.add_event(event)
        except Exception as exc:
            errors.append(f"Failed to restore chatlog for scene '{scene_id}': {exc}")
    return errors
```

---

### 5. Migration Exporter (`/home/harald/src/sidestage/src/sidestage/migration/exporter.py`)

#### 5.1 Update Imports

Remove: `ChatMessageModel`
Add: `EventModel` if not already imported (it is)

#### 5.2 Update Chatlog Export

The exporter currently reads `scene_data.messages` from SQLite. Since `SceneModel.messages` is removed, query events from storage instead:

```python
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
            errors.append(f"Failed to get chatlog for scene {entity.id}: {exc}")
```

#### 5.3 Update `_format_chatlog()`

Change the parameter type from `list[ChatMessageModel]` to `list[EventModel]` and update field references:

```python
def _format_chatlog(events: list[EventModel]) -> str:
    """Format chat events into chatlog.log content."""
    lines = []
    for evt in events:
        char_id = evt.character_id or "unknown"
        lines.append(f'[{evt.walltime}] ({char_id}) {evt.name}: "{evt.body}"')
    return "\n".join(lines)
```

---

### 6. SQLite Storage (`/home/harald/src/sidestage/src/sidestage/storage.py`)

#### 6.1 Add Event Query Methods

Add methods to retrieve events by `scene_id` and optionally by `event_type`:

```python
def list_events_by_scene(
    self, scene_id: str, event_type: "EventType | None" = None
) -> list[EventModel]:
    """List events for a scene, optionally filtered by event_type."""
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.execute("SELECT data FROM events")
        events = []
        for row in cursor.fetchall():
            event = EventModel.model_validate_json(row[0])
            if event.scene_id != scene_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            events.append(event)
        return events
```

This is a simple filtering approach. The events table uses the generic `(id, data)` schema where `data` is JSON. Filtering is done in Python after deserialization. For larger datasets, a more efficient approach with indexed columns would be needed, but that is out of scope for this restructuring.

#### 6.2 Update `update_scene()`

No code change needed here -- `update_scene()` calls `_save_entity("scenes", scene)` which serializes via `model_dump_json()`. Since `SceneModel` no longer has the `messages` field (removed in section-01), the serialized JSON naturally excludes it.

---

### 7. EventModel `ConfigDict` Safety Net

In section-01-event-model, the `EventModel` class should be configured with `model_config = ConfigDict(extra='ignore')`. This ensures that if the graph or SQLite contains stale properties from the old schema (e.g., `message`, `widget`, `duration_str`), deserialization does not fail.

This is technically part of section-01, but it is listed here as a dependency validation point. Confirm that EventModel includes:

```python
from pydantic import ConfigDict

class EventModel(EntityModel):
    model_config = ConfigDict(extra='ignore')
    # ... fields ...
```

---

## Files Modified (Summary)

| File | Change |
|---|---|
| `/home/harald/src/sidestage/src/sidestage/graph/entities.py` | Update registries, `entity_to_labels()`, `entity_to_properties()`, `node_to_entity()` for flattened EventModel |
| `/home/harald/src/sidestage/src/sidestage/entities.py` | Update `entity_to_markdown()` and `markdown_to_entity()` for event_type in frontmatter |
| `/home/harald/src/sidestage/src/sidestage/migration/serialization.py` | Update `TYPE_MAP`, `TYPE_TO_SUBDIR`, `entity_to_frontmatter_dict()`, `frontmatter_dict_to_entity()` |
| `/home/harald/src/sidestage/src/sidestage/migration/importer.py` | Update `_parse_chatlog_lines()`, `_restore_chatlogs()`, remove `sync_manager` param |
| `/home/harald/src/sidestage/src/sidestage/migration/exporter.py` | Update chatlog retrieval and `_format_chatlog()` |
| `/home/harald/src/sidestage/src/sidestage/storage.py` | Add `list_events_by_scene()` method |
| `/home/harald/src/sidestage/tests/unit/test_graph_serialization.py` | Rewrite for flattened EventModel |
| `/home/harald/src/sidestage/tests/unit/test_entities.py` | Add EventModel markdown round-trip test |
| `/home/harald/src/sidestage/tests/unit/test_migration_serialization.py` | Update for flattened EventModel |
| `/home/harald/src/sidestage/tests/unit/test_storage.py` | Add event query tests |

## Implementation Order Within This Section

1. Write all tests (they will fail initially)
2. Update `graph/entities.py` (registries, label/property/node functions)
3. Update `entities.py` (markdown serialization)
4. Update `migration/serialization.py` (TYPE_MAP, frontmatter functions)
5. Update `storage.py` (add `list_events_by_scene`)
6. Update `migration/importer.py` (chatlog parsing, restore)
7. Update `migration/exporter.py` (chatlog export)
8. Run tests, verify all pass