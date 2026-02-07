"""Unit tests for entity serialization to/from graph node properties."""
import pytest

from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent
from sidestage.graph.entities import (
    LABEL_TO_MODEL,
    MODEL_TO_LABELS,
    EXCLUDED_FIELDS,
    entity_to_labels,
    entity_to_properties,
    node_to_entity,
)


# --- Label Registry ---


def test_label_registry_contains_all_entity_types():
    """LABEL_TO_MODEL registry contains all entity types and maps to correct classes."""
    expected = {
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
    for label, model_cls in expected.items():
        assert label in LABEL_TO_MODEL, f"Missing label: {label}"
        assert LABEL_TO_MODEL[label] is model_cls


# --- entity_to_labels ---


def test_entity_to_labels_character():
    """entity_to_labels returns ['Entity', 'Character'] for a Character."""
    char = Character(id="c1", name="Alice", body="desc")
    assert entity_to_labels(char) == ["Entity", "Character"]


def test_entity_to_labels_location():
    """entity_to_labels returns ['Entity', 'Location'] for a Location."""
    loc = Location(id="l1", name="Tavern", body="desc")
    assert entity_to_labels(loc) == ["Entity", "Location"]


def test_entity_to_labels_item():
    """entity_to_labels returns ['Entity', 'Item'] for an Item."""
    item = Item(id="i1", name="Sword", body="desc")
    assert entity_to_labels(item) == ["Entity", "Item"]


def test_entity_to_labels_scene():
    """entity_to_labels returns ['Entity', 'Scene'] for a Scene."""
    scene = Scene(id="s1", name="Opening", body="desc")
    assert entity_to_labels(scene) == ["Entity", "Scene"]


def test_entity_to_labels_event():
    """entity_to_labels returns ['Entity', 'Event'] for an Event."""
    event = Event(id="e1", name="Battle", body="desc", scene_id="s1", gametime=100, walltime="2024-01-01T00:00:00")
    assert entity_to_labels(event) == ["Entity", "Event"]


def test_entity_to_labels_chat_message():
    """entity_to_labels returns ['Entity', 'Event', 'ChatMessage'] for a ChatMessage."""
    msg = ChatMessage(
        id="m1", name="msg", body="desc", scene_id="s1",
        gametime=100, walltime="2024-01-01T00:00:00",
        character_id="c1", message="Hello",
    )
    assert entity_to_labels(msg) == ["Entity", "Event", "ChatMessage"]


def test_entity_to_labels_join_event():
    """entity_to_labels returns ['Entity', 'Event', 'JoinEvent'] for a JoinEvent."""
    evt = JoinEvent(id="j1", name="join", body="desc", scene_id="s1", gametime=100, walltime="2024-01-01T00:00:00", actor_id="a1")
    assert entity_to_labels(evt) == ["Entity", "Event", "JoinEvent"]


def test_entity_to_labels_leave_event():
    """entity_to_labels returns ['Entity', 'Event', 'LeaveEvent'] for a LeaveEvent."""
    evt = LeaveEvent(id="l1", name="leave", body="desc", scene_id="s1", gametime=100, walltime="2024-01-01T00:00:00", actor_id="a1")
    assert entity_to_labels(evt) == ["Entity", "Event", "LeaveEvent"]


def test_entity_to_labels_fast_forward_event():
    """entity_to_labels returns ['Entity', 'Event', 'FastForwardEvent'] for a FastForwardEvent."""
    evt = FastForwardEvent(id="f1", name="ff", body="desc", scene_id="s1", gametime=100, walltime="2024-01-01T00:00:00", duration_str="2 hours")
    assert entity_to_labels(evt) == ["Entity", "Event", "FastForwardEvent"]


# --- entity_to_properties ---


def test_entity_to_properties_character():
    """entity_to_properties converts Character fields to property dict."""
    char = Character(
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
    """entity_to_properties excludes connected_locations for Location."""
    loc = Location(id="l1", name="Tavern", body="desc", connected_locations=["l2"])
    props = entity_to_properties(loc)
    assert "connected_locations" not in props
    assert props["id"] == "l1"


def test_entity_to_properties_excludes_messages_for_scene():
    """entity_to_properties excludes messages for Scene."""
    scene = Scene(id="s1", name="Opening", body="desc", messages=[])
    props = entity_to_properties(scene)
    assert "messages" not in props


def test_entity_to_properties_excludes_widget_for_chat_message():
    """entity_to_properties excludes widget for ChatMessage."""
    msg = ChatMessage(
        id="m1", name="msg", body="desc", scene_id="s1",
        gametime=100, walltime="2024-01-01T00:00:00",
        character_id="c1", message="Hello", widget={"type": "poll"},
    )
    props = entity_to_properties(msg)
    assert "widget" not in props
    assert props["message"] == "Hello"


def test_entity_to_properties_handles_none_optional_fields():
    """entity_to_properties omits None optional fields."""
    char = Character(id="c1", name="Alice", body="desc", location_id=None)
    props = entity_to_properties(char)
    assert "location_id" not in props


def test_entity_to_properties_includes_array_fields():
    """entity_to_properties includes list fields like inventory."""
    char = Character(id="c1", name="Alice", body="desc", inventory=["sword", "shield"])
    props = entity_to_properties(char)
    assert props["inventory"] == ["sword", "shield"]


# --- node_to_entity ---


def test_node_to_entity_reconstructs_character():
    """node_to_entity reconstructs a Character from labels and properties."""
    labels = ["Entity", "Character"]
    properties = {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []}
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, Character)
    assert entity.id == "c1"
    assert entity.name == "Alice"


def test_node_to_entity_reconstructs_chat_message():
    """node_to_entity reconstructs ChatMessage from multi-label node."""
    labels = ["Entity", "Event", "ChatMessage"]
    properties = {
        "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
        "gametime": 100, "walltime": "2024-01-01T00:00:00",
        "character_id": "c1", "message": "Hello",
    }
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, ChatMessage)
    assert entity.message == "Hello"


def test_node_to_entity_picks_chat_message_over_event():
    """node_to_entity picks ChatMessage (most specific) when both Event and ChatMessage labels present."""
    labels = ["Entity", "Event", "ChatMessage"]
    properties = {
        "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
        "gametime": 100, "walltime": "2024-01-01T00:00:00",
        "character_id": "c1", "message": "Hello",
    }
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, ChatMessage)
    assert type(entity) is ChatMessage  # Exact type, not bare Event


def test_node_to_entity_reconstructs_location():
    """node_to_entity reconstructs a Location from labels and properties."""
    labels = ["Entity", "Location"]
    properties = {"id": "l1", "name": "Tavern", "body": "A cozy tavern"}
    entity = node_to_entity(labels, properties)
    assert isinstance(entity, Location)
    assert entity.name == "Tavern"
    assert entity.connected_locations == []  # Default empty list


def test_node_to_entity_raises_on_unknown_labels():
    """node_to_entity raises QueryError for unrecognized labels."""
    from sidestage.graph.errors import QueryError
    labels = ["Unknown"]
    properties = {"id": "x1"}
    with pytest.raises(QueryError):
        node_to_entity(labels, properties)
