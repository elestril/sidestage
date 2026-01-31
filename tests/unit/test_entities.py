import pytest
from sidestage.models import NPC, Location, Item
from sidestage.entities import entity_to_markdown, markdown_to_entity

def test_npc_markdown_roundtrip():
    npc = NPC(
        id="npc_barnaby",
        name="Barnaby the Bold",
        description="A retired knight.",
        location_id="loc_tavern",
        inventory=["item_sword"]
    )
    
    md = entity_to_markdown(npc)
    assert "name: Barnaby the Bold" in md
    assert "type: NPC" in md
    assert "A retired knight." in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, NPC)
    assert parsed.id == npc.id
    assert parsed.name == npc.name
    assert parsed.description == npc.description
    assert parsed.location_id == npc.location_id
    assert parsed.inventory == npc.inventory

def test_location_markdown_roundtrip():
    loc = Location(
        id="loc_woods",
        name="Whispering Woods",
        description="A spooky forest.",
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
        description="Sharp blade."
    )
    
    md = entity_to_markdown(item)
    assert "type: Item" in md
    
    parsed = markdown_to_entity(md)
    assert isinstance(parsed, Item)
    assert parsed.name == item.name
