from sidestage.models import NPC, Location, Item

def test_npc_model():
    npc = NPC(id="test", name="Test", description="Test Description")
    assert npc.id == "test"
    assert npc.name == "Test"

def test_location_model():
    loc = Location(id="test", name="Test", description="Test Description")
    assert loc.id == "test"
    assert loc.name == "Test"

def test_item_model():
    item = Item(id="test", name="Test", description="Test Description")
    assert item.id == "test"
    assert item.name == "Test"
