import pytest
from pathlib import Path
from sidestage.models import NPC, Location, Item
from sidestage.storage import Storage

@pytest.fixture
def storage(tmp_path):
    db_file = tmp_path / "world.db"
    return Storage(db_path=db_file)

def test_npc_crud(storage):
    npc = NPC(id="npc_1", name="Grog", body="A big barbarian")
    
    # Create
    storage.add_npc(npc)
    
    # Read
    retrieved = storage.get_npc("npc_1")
    assert retrieved == npc
    
    # Update
    npc.body = "A very big barbarian"
    storage.update_npc(npc)
    retrieved_updated = storage.get_npc("npc_1")
    assert retrieved_updated.body == "A very big barbarian"
    
    # Delete
    storage.delete_npc("npc_1")
    assert storage.get_npc("npc_1") is None

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
    storage.add_npc(NPC(id="n1", name="A", body=""))
    storage.add_npc(NPC(id="n2", name="B", body=""))
    
    npcs = storage.list_npcs()
    assert len(npcs) == 2
    assert {n.id for n in npcs} == {"n1", "n2"}
