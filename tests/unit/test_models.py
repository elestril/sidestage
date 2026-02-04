from sidestage.models import Character, Location, Item

def test_character_model():
    char = Character(id="test", name="Test", body="Test body")
    assert char.name == "Test"
    assert char.body == "Test body"

def test_location_model():
    loc = Location(id="test", name="Test", body="Test body")
    assert loc.name == "Test"
    assert loc.body == "Test body"

def test_item_model():
    item = Item(id="test", name="Test", body="Test body")
    assert item.name == "Test"
    assert item.body == "Test body"
