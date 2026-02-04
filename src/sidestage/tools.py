from typing import List, Optional, Callable, Any
import json
from sidestage.storage import Storage
from sidestage.models import Character, Location, Item

class WorldTools:
    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None):
        self.storage = storage
        self.on_change = on_change

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def create_character(self, name: str, body: str, location_id: Optional[str] = None) -> str:
        """
        Creates a new Character in the world.
        
        Args:
            name: Name of the Character.
            body: Markdown description of the Character.
            location_id: Optional ID of the location where the Character starts.
            
        Returns:
            JSON string of the created Character.
        """
        import uuid
        entity_id = f"char_{str(uuid.uuid4())[:8]}"
        
        char = Character(id=entity_id, name=name, body=body, location_id=location_id)
        self.storage.add_character(char)
        self._notify_change()
        return char.model_dump_json()

    def update_character(self, character_id: str, name: Optional[str] = None, body: Optional[str] = None, location_id: Optional[str] = None) -> str:
        """
        Updates an existing Character.
        
        Args:
            character_id: The ID of the Character to update.
            name: New name (optional).
            body: New markdown body (optional).
            location_id: New location ID (optional).
            
        Returns:
            JSON string of the updated Character or error message.
        """
        char = self.storage.get_character(character_id)
        if not char:
            return f"Error: Character with ID {character_id} not found."
            
        if name is not None:
            char.name = name
        if body is not None:
            char.body = body
        if location_id is not None:
            char.location_id = location_id
            
        self.storage.update_character(char)
        self._notify_change()
        return char.model_dump_json()

    def get_character(self, character_id: str) -> str:
        """
        Retrieves details of a Character by ID.
        
        Args:
            character_id: The unique ID of the Character.
            
        Returns:
            JSON string of the Character details or "Not found".
        """
        char = self.storage.get_character(character_id)
        if char:
            return char.model_dump_json()
        return "Character not found."

    def list_characters(self) -> str:
        """
        Lists all Characters in the world.
        
        Returns:
            JSON list of all Characters.
        """
        chars = self.storage.list_characters()
        return json.dumps([n.model_dump() for n in chars])

    def create_location(self, name: str, body: str) -> str:
        """
        Creates a new location in the world.
        
        Args:
            name: Name of the location.
            body: Markdown description of the location.
            
        Returns:
            JSON string of the created location.
        """
        import uuid
        entity_id = f"loc_{str(uuid.uuid4())[:8]}"
        loc = Location(id=entity_id, name=name, body=body)
        self.storage.add_location(loc)
        self._notify_change()
        return loc.model_dump_json()

    def update_location(self, location_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str:
        """
        Updates an existing location.
        
        Args:
            location_id: The ID of the location to update.
            name: New name (optional).
            body: New markdown body (optional).
            
        Returns:
            JSON string of the updated location or error message.
        """
        loc = self.storage.get_location(location_id)
        if not loc:
            return f"Error: Location with ID {location_id} not found."
            
        if name is not None:
            loc.name = name
        if body is not None:
            loc.body = body
            
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

    def create_item(self, name: str, body: str) -> str:
        """
        Creates a new item in the world.
        
        Args:
            name: Name of the item.
            body: Markdown description of the item.
            
        Returns:
            JSON string of the created item.
        """
        import uuid
        entity_id = f"item_{str(uuid.uuid4())[:8]}"
        item = Item(id=entity_id, name=name, body=body)
        self.storage.add_item(item)
        self._notify_change()
        return item.model_dump_json()

    def update_item(self, item_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str:
        """
        Updates an existing item.
        
        Args:
            item_id: The ID of the item to update.
            name: New name (optional).
            body: New markdown body (optional).
            
        Returns:
            JSON string of the updated item or error message.
        """
        item = self.storage.get_item(item_id)
        if not item:
            return f"Error: Item with ID {item_id} not found."
            
        if name is not None:
            item.name = name
        if body is not None:
            item.body = body
            
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
