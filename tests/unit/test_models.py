from sidestage.models import CharacterModel, LocationModel, ItemModel

def test_character_model():
    char = CharacterModel(id="test", name="Test", body="Test body")
    assert char.name == "Test"
    assert char.body == "Test body"

def test_location_model():
    loc = LocationModel(id="test", name="Test", body="Test body")
    assert loc.name == "Test"
    assert loc.body == "Test body"

def test_item_model():
    item = ItemModel(id="test", name="Test", body="Test body")
    assert item.name == "Test"
    assert item.body == "Test body"
