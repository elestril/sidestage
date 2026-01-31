from typing import List, Optional, Callable, Any
import json
from sidestage.storage import Storage
from sidestage.models import NPC, Location, Item

class WorldTools:
    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None):
        self.storage = storage
        self.on_change = on_change

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def create_npc(self, name: str, description: str, location_id: Optional[str] = None) -> str:
        """
        Creates a new NPC in the world.
        
        Args:
            name: Name of the NPC.
            description: Description of the NPC.
            location_id: Optional ID of the location where the NPC starts.
            
        Returns:
            JSON string of the created NPC.
        """
        import uuid
        entity_id = f"npc_{str(uuid.uuid4())[:8]}"
        
        npc = NPC(id=entity_id, name=name, description=description, location_id=location_id)
        self.storage.add_npc(npc)
        self._notify_change()
        return npc.model_dump_json()

    def update_npc(self, npc_id: str, name: Optional[str] = None, description: Optional[str] = None, location_id: Optional[str] = None) -> str:
        """
        Updates an existing NPC.
        
        Args:
            npc_id: The ID of the NPC to update.
            name: New name (optional).
            description: New description (optional).
            location_id: New location ID (optional).
            
        Returns:
            JSON string of the updated NPC or error message.
        """
        npc = self.storage.get_npc(npc_id)
        if not npc:
            return f"Error: NPC with ID {npc_id} not found."
            
        if name is not None:
            npc.name = name
        if description is not None:
            npc.description = description
        if location_id is not None:
            npc.location_id = location_id
            
        self.storage.update_npc(npc)
        self._notify_change()
        return npc.model_dump_json()

    def get_npc(self, npc_id: str) -> str:
        """
        Retrieves details of an NPC by ID.
        
        Args:
            npc_id: The unique ID of the NPC.
            
        Returns:
            JSON string of the NPC details or "Not found".
        """
        npc = self.storage.get_npc(npc_id)
        if npc:
            return npc.model_dump_json()
        return "NPC not found."

    def list_npcs(self) -> str:
        """
        Lists all NPCs in the world.
        
        Returns:
            JSON list of all NPCs.
        """
        npcs = self.storage.list_npcs()
        return json.dumps([n.model_dump() for n in npcs])

    def create_location(self, name: str, description: str) -> str:
        """
        Creates a new location in the world.
        
        Args:
            name: Name of the location.
            description: Description of the location.
            
        Returns:
            JSON string of the created location.
        """
        import uuid
        entity_id = f"loc_{str(uuid.uuid4())[:8]}"
        loc = Location(id=entity_id, name=name, description=description)
        self.storage.add_location(loc)
        self._notify_change()
        return loc.model_dump_json()

    def update_location(self, location_id: str, name: Optional[str] = None, description: Optional[str] = None) -> str:
        """
        Updates an existing location.
        
        Args:
            location_id: The ID of the location to update.
            name: New name (optional).
            description: New description (optional).
            
        Returns:
            JSON string of the updated location or error message.
        """
        loc = self.storage.get_location(location_id)
        if not loc:
            return f"Error: Location with ID {location_id} not found."
            
        if name is not None:
            loc.name = name
        if description is not None:
            loc.description = description
            
        self.storage.update_location(loc)
        self._notify_change()
        return loc.model_dump_json()

    def list_locations(self) -> str:
        """
        Lists all locations in the world.
        
        Returns:
            JSON list of all locations.
        """
        locs = self.storage.list_locations()
        return json.dumps([l.model_dump() for l in locs])

    def create_item(self, name: str, description: str) -> str:
        """
        Creates a new item in the world.
        
        Args:
            name: Name of the item.
            description: Description of the item.
            
        Returns:
            JSON string of the created item.
        """
        import uuid
        entity_id = f"item_{str(uuid.uuid4())[:8]}"
        item = Item(id=entity_id, name=name, description=description)
        self.storage.add_item(item)
        self._notify_change()
        return item.model_dump_json()

    def update_item(self, item_id: str, name: Optional[str] = None, description: Optional[str] = None) -> str:
        """
        Updates an existing item.
        
        Args:
            item_id: The ID of the item to update.
            name: New name (optional).
            description: New description (optional).
            
        Returns:
            JSON string of the updated item or error message.
        """
        item = self.storage.get_item(item_id)
        if not item:
            return f"Error: Item with ID {item_id} not found."
            
        if name is not None:
            item.name = name
        if description is not None:
            item.description = description
            
        self.storage.update_item(item)
        self._notify_change()
        return item.model_dump_json()

    def list_items(self) -> str:
        """
        Lists all items in the world.
        
        Returns:
            JSON list of all items.
        """
        items = self.storage.list_items()
        return json.dumps([i.model_dump() for i in items])
