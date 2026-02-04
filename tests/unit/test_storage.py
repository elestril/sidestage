import pytest
from pathlib import Path
from sidestage.models import Character, Location, Item
from sidestage.storage import Storage

@pytest.fixture
def storage(tmp_path):
    db_file = tmp_path / "world.db"
    return Storage(db_path=db_file)

def test_character_crud(storage):
    char = Character(id="char_1", name="Grog", body="A big barbarian")
    
    # Create
    storage.add_character(char)
    
    # Read
    retrieved = storage.get_character("char_1")
    assert retrieved == char
    
    # Update
    char.body = "A very big barbarian"
    storage.update_character(char)
    retrieved_updated = storage.get_character("char_1")
    assert retrieved_updated.body == "A very big barbarian"
    
    # Delete
    storage.delete_character("char_1")
    assert storage.get_character("char_1") is None

def test_location_crud(storage):
    loc = Location(id="loc_1", name="Tavern", body="A noisy place")
    storage.add_location(loc)
    assert storage.get_location("loc_1") == loc
    storage.delete_location("loc_1")
    assert storage.get_location("loc_1") is None

def test_item_crud(storage):
    item = Item(id="item_1", name="Sword", body="Sharp")
    storage.add_item(item)
    assert storage.get_item("item_1") == item
    storage.delete_item("item_1")
    assert storage.get_item("item_1") is None

def test_list_entities(storage):
    storage.add_character(Character(id="n1", name="A", body=""))
    storage.add_character(Character(id="n2", name="B", body=""))
    
    chars = storage.list_characters()
    assert len(chars) == 2
    assert {c.id for c in chars} == {"n1", "n2"}
