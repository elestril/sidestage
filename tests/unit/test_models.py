from sidestage.models import NPC, Location, Item

def test_npc_model():
    npc = NPC(id="test", name="Test", body="Test body")
    assert npc.name == "Test"
    assert npc.body == "Test body"

def test_location_model():
    loc = Location(id="test", name="Test", body="Test body")
    assert loc.name == "Test"
    assert loc.body == "Test body"

def test_item_model():
    item = Item(id="test", name="Test", body="Test body")
    assert item.name == "Test"
    assert item.body == "Test body"
