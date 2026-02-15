from datetime import datetime
import pytest
from pathlib import Path
from sidestage.models import CharacterModel, LocationModel, ItemModel
from sidestage.storage import Storage

@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    db_file = tmp_path / "world.db"
    return Storage(db_path=db_file)

def test_character_crud(storage: Storage):
    char = CharacterModel(id="char_1", name="Grog", body="A big barbarian")
    
    # Create
    storage.add_character(char)
    
    # Read
    retrieved = storage.get_character("char_1")
    assert retrieved == char
    
    # Update
    char.body = "A very big barbarian"
    storage.update_character(char)
    retrieved_updated = storage.get_character("char_1")
    assert retrieved_updated is not None
    assert retrieved_updated.body == "A very big barbarian"
    
    # Delete
    storage.delete_character("char_1")
    assert storage.get_character("char_1") is None

def test_location_crud(storage: Storage):
    loc = LocationModel(id="loc_1", name="Tavern", body="A noisy place")
    storage.add_location(loc)
    assert storage.get_location("loc_1") == loc
    storage.delete_location("loc_1")
    assert storage.get_location("loc_1") is None

def test_item_crud(storage: Storage):
    item = ItemModel(id="item_1", name="Sword", body="Sharp")
    storage.add_item(item)
    assert storage.get_item("item_1") == item
    storage.delete_item("item_1")
    assert storage.get_item("item_1") is None

def test_list_entities(storage: Storage):
    storage.add_character(CharacterModel(id="n1", name="A", body=""))
    storage.add_character(CharacterModel(id="n2", name="B", body=""))

    chars = storage.list_characters()
    assert len(chars) == 2
    assert {c.id for c in chars} == {"n1", "n2"}


def test_event_crud(storage: Storage):
    """Events can be stored and retrieved by scene_id."""
    from sidestage.models import EventModel, EventType
    event = EventModel(
        id="evt_1", name="Alice Message", body="Hello",
        scene_id="scene_1", gametime=100, walltime=datetime.fromisoformat("2024-01-01T00:00:00"),
        event_type=EventType.CHAT_MESSAGE, character_id="char_alice",
    )
    storage.add_event(event)
    events = storage.list_events_by_scene("scene_1")
    assert len(events) == 1
    assert events[0].id == "evt_1"
    assert events[0].event_type == EventType.CHAT_MESSAGE


def test_list_events_by_scene_and_type(storage: Storage):
    """list_events_by_scene filters by event_type when provided."""
    from sidestage.models import EventModel, EventType
    chat = EventModel(
        id="evt_1", name="msg", body="hi", scene_id="s1",
        gametime=100, walltime=datetime.fromisoformat("2024-01-01T00:00:00"),
        event_type=EventType.CHAT_MESSAGE,
    )
    join = EventModel(
        id="evt_2", name="join", body="", scene_id="s1",
        gametime=100, walltime=datetime.fromisoformat("2024-01-01T00:00:00"),
        event_type=EventType.JOIN,
    )
    storage.add_event(chat)
    storage.add_event(join)
    chat_only = storage.list_events_by_scene("s1", event_type=EventType.CHAT_MESSAGE)
    assert len(chat_only) == 1
    assert chat_only[0].event_type == EventType.CHAT_MESSAGE


def test_event_model_extra_ignore(storage: Storage):
    """EventModel with extra='ignore' gracefully handles unknown fields from storage."""
    from sidestage.models import EventModel
    import json
    stale_data = {
        "id": "evt_stale", "name": "old", "body": "", "scene_id": "s1",
        "gametime": 0, "walltime": "2024-01-01T00:00:00",
        "event_type": "ChatMessage", "message": "stale field",
        "metadata": {}, "visibility": "public",
    }
    # Should not raise even with the unknown 'message' field
    event = EventModel.model_validate(stale_data)
    assert event.id == "evt_stale"
