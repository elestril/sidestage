from pathlib import Path
from sidestage.storage import Storage
from sidestage.models import NPC, Location, Item

def seed():
    db_path = Path(".workdir/dev/sidestage.db")
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
    storage = Storage(db_path=db_path)
    
    # NPCs
    storage.add_npc(NPC(id="npc_barnaby", name="Barnaby the Bold", body="A retired knight with a penchant for telling tall tales at the local tavern."))
    storage.add_npc(NPC(id="npc_elara", name="Elara the Wise", body="An elven scholar who knows more about the Whispering Woods than she lets on."))
    
    # Locations
    storage.add_location(Location(id="loc_tavern", name="The Rusty Tankard", body="A bustling tavern where adventurers gather to share stories and find work."))
    storage.add_location(Location(id="loc_woods", name="Whispering Woods", body="A dense forest where the trees seem to murmur secrets to those who listen."))
    
    # Items
    storage.add_item(Item(id="item_sword", name="Rusty Shortsword", body="A basic blade, weathered by time but still capable of dealing a decent blow."))
    storage.add_item(Item(id="item_map", name="Old Parchment Map", body="A tattered map showing the layout of the Whispering Woods, with several cryptic marks."))

    print("Seeded database with sample entities.")

if __name__ == "__main__":
    seed()
