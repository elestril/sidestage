import pytest
from sidestage.models import Character, Location, Item
from sidestage.entities import entity_to_markdown, markdown_to_entity

def test_character_markdown_roundtrip():
    char = Character(
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
    assert isinstance(parsed, Character)
    assert parsed.id == char.id
    assert parsed.name == char.name
    assert parsed.body == char.body
    assert parsed.location_id == char.location_id
    assert parsed.inventory == char.inventory

def test_location_markdown_roundtrip():
    loc = Location(
        id="loc_woods",
        name="Whispering Woods",
        body="A spooky forest.",
        connected_locations=["loc_tavern"]
    )
    
    md = entity_to_markdown(loc)
    assert "type: Location" in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, Location)
    assert parsed.name == loc.name
    assert parsed.connected_locations == loc.connected_locations

def test_item_markdown_roundtrip():
    item = Item(
        id="item_sword",
        name="Sword",
        body="Sharp blade."
    )
    
    md = entity_to_markdown(item)
    assert "type: Item" in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, Item)
    assert parsed.name == item.name
