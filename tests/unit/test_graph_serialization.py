from datetime import datetime
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
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "ChatMessage"]


def test_entity_to_labels_join_event():
    """entity_to_labels for EventModel with JOIN returns ['Entity', 'Event', 'JoinEvent']."""
    event = EventModel(
        id="e1", name="join", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.JOIN,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "JoinEvent"]


def test_entity_to_labels_leave_event():
    """entity_to_labels for EventModel with LEAVE returns ['Entity', 'Event', 'LeaveEvent']."""
    event = EventModel(
        id="e1", name="leave", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.LEAVE,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "LeaveEvent"]


def test_entity_to_labels_adjust_gametime_event():
    """entity_to_labels for ADJUST_GAMETIME returns ['Entity', 'Event', 'AdjustGametime']."""
    event = EventModel(
        id="e1", name="time", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.ADJUST_GAMETIME,
    )
    assert entity_to_labels(event) == ["Entity", "Event", "AdjustGametime"]


def test_entity_to_labels_error_event():
    """entity_to_labels for ERROR returns ['Entity', 'Event', 'Error']."""
    event = EventModel(
        id="e1", name="Error", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.ERROR,
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
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
        metadata={"widget": {"type": "card"}},
    )
    props = entity_to_properties(event)
    assert isinstance(props["metadata"], str)
    assert json.loads(props["metadata"]) == {"widget": {"type": "card"}}


def test_entity_to_properties_empty_metadata_serialized_as_json():
    """Empty metadata dict serialized as '{}' JSON string."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert props["metadata"] == "{}"


def test_entity_to_properties_walltime_as_iso_string():
    """walltime is stored as ISO string in graph properties."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T12:30:00+00:00"), event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert isinstance(props["walltime"], str)


def test_entity_to_properties_event_type_as_string():
    """event_type stored as its string value."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
    )
    props = entity_to_properties(event)
    assert props["event_type"] == "ChatMessage"


def test_entity_to_properties_visibility_as_string():
    """visibility stored as its string value."""
    event = EventModel(
        id="e1", name="msg", body="", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
        visibility=Visibility.GM_ONLY,
    )
    props = entity_to_properties(event)
    assert props["visibility"] == "gm_only"


def test_entity_to_properties_character():
    """entity_to_properties converts CharacterModel fields to property dict."""
    char = CharacterModel(
        id="c1", name="Alice", body="A brave warrior",
        location_id="loc_1", inventory=["item_sword"],
    )
    props = entity_to_properties(char)
    assert props["id"] == "c1"
    assert props["name"] == "Alice"
    assert props["body"] == "A brave warrior"
    assert props["unseen"] is False
    assert props["location_id"] == "loc_1"
    assert props["inventory"] == ["item_sword"]


def test_entity_to_properties_excludes_connected_locations_for_location():
    """entity_to_properties excludes connected_locations for LocationModel."""
    loc = LocationModel(id="l1", name="Tavern", body="desc", connected_locations=["l2"])
    props = entity_to_properties(loc)
    assert "connected_locations" not in props
    assert props["id"] == "l1"


def test_entity_to_properties_handles_none_optional_fields():
    """entity_to_properties omits None optional fields."""
    char = CharacterModel(id="c1", name="Alice", body="desc", location_id=None)
    props = entity_to_properties(char)
    assert "location_id" not in props


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
    assert isinstance(entity, EventModel)
    assert isinstance(entity.metadata, dict)
    assert entity.metadata["widget"] == "poll"


def test_event_model_roundtrip_through_graph_helpers():
    """EventModel survives entity_to_properties -> node_to_entity round-trip."""
    event = EventModel(
        id="e1", name="msg", body="hello", scene_id="s1", gametime=100,
        walltime=datetime.fromisoformat("2024-01-01T00:00:00"), event_type=EventType.CHAT_MESSAGE,
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


def test_node_to_entity_reconstructs_character():
    """node_to_entity reconstructs a CharacterModel from labels and properties."""
    labels = ["Entity", "Character"]
    properties = {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []}
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, CharacterModel)
    assert entity.id == "c1"
    assert entity.name == "Alice"


def test_node_to_entity_reconstructs_location():
    """node_to_entity reconstructs a LocationModel from labels and properties."""
    labels = ["Entity", "Location"]
    properties = {"id": "l1", "name": "Tavern", "body": "A cozy tavern"}
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, LocationModel)
    assert entity.name == "Tavern"
    assert entity.connected_locations == []


def test_node_to_entity_raises_on_unknown_labels():
    """node_to_entity raises QueryError for unrecognized labels."""
    from sidestage.graph.errors import QueryError
    labels = ["Unknown"]
    properties = {"id": "x1"}
    with pytest.raises(QueryError):
        node_to_entity(labels, properties)
