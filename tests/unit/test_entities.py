from datetime import datetime
import pytest
from sidestage.models import CharacterModel, LocationModel, ItemModel
from sidestage.entities import entity_to_markdown, markdown_to_entity

def test_character_markdown_roundtrip():
    char = CharacterModel(
        id="char_barnaby",
        name="Barnaby the Bold",
        body="A retired knight.",
        location_id="loc_tavern",
        inventory=["item_sword"]
    )
    
    md = entity_to_markdown(char)
    assert "name: Barnaby the Bold" in md
    assert "type: Character" in md
    assert "A retired knight." in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, CharacterModel)
    assert parsed.id == char.id
    assert parsed.name == char.name
    assert parsed.body == char.body
    assert parsed.location_id == char.location_id
    assert parsed.inventory == char.inventory

def test_location_markdown_roundtrip():
    loc = LocationModel(
        id="loc_woods",
        name="Whispering Woods",
        body="A spooky forest.",
        connected_locations=["loc_tavern"]
    )
    
    md = entity_to_markdown(loc)
    assert "type: Location" in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, LocationModel)
    assert parsed.name == loc.name
    assert parsed.connected_locations == loc.connected_locations

def test_item_markdown_roundtrip():
    item = ItemModel(
        id="item_sword",
        name="Sword",
        body="Sharp blade."
    )

    md = entity_to_markdown(item)
    assert "type: Item" in md

    parsed = markdown_to_entity(md)
    assert isinstance(parsed, ItemModel)
    assert parsed.name == item.name


def test_event_model_markdown_roundtrip():
    """EventModel with event_type survives markdown serialization round-trip."""
    from sidestage.models import EventModel, EventType

    event = EventModel(
        id="evt_abc123",
        name="Alice Message",
        body="Hello world",
        scene_id="scene_1",
        gametime=3600,
        walltime=datetime.fromisoformat("2024-06-15T10:30:00Z"),
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
