from __future__ import annotations

from typing import List, Optional, Callable, Any, TYPE_CHECKING
import json
from sidestage.storage import Storage
from sidestage.models import Character, Location, Item

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient


class WorldTools:
    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None,
                 graph_client: GraphClient | None = None):
        self.storage = storage
        self.on_change = on_change
        self.graph_client = graph_client

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    async def create_character(self, name: str, body: str, location_id: Optional[str] = None) -> str:
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

        if self.graph_client is not None:
            from sidestage.graph import create_entity, link
            await create_entity(self.graph_client, char)
            if location_id:
                await link(self.graph_client, char.id, "LOCATED_IN", location_id)
        else:
            self.storage.add_character(char)

        self._notify_change()
        return char.model_dump_json()

    async def update_character(self, character_id: str, name: Optional[str] = None, body: Optional[str] = None, location_id: Optional[str] = None) -> str:
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
        if self.graph_client is not None:
            from sidestage.graph import get_entity, update_entity, link, unlink
            existing = await get_entity(self.graph_client, character_id)
            if not existing:
                return f"Error: Character with ID {character_id} not found."

            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = name
            if body is not None:
                updates["body"] = body
            if location_id is not None:
                updates["location_id"] = location_id
                # Update LOCATED_IN relationship
                old_loc = getattr(existing, "location_id", None)
                if old_loc and old_loc != location_id:
                    await unlink(self.graph_client, character_id, "LOCATED_IN", old_loc)
                if location_id:
                    await link(self.graph_client, character_id, "LOCATED_IN", location_id)

            if updates:
                updated = await update_entity(self.graph_client, character_id, updates)
            else:
                updated = existing
            self._notify_change()
            return updated.model_dump_json()
        else:
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

    async def get_character(self, character_id: str) -> str:
        """
        Retrieves details of a Character by ID.

        Args:
            character_id: The unique ID of the Character.

        Returns:
            JSON string of the Character details or "Not found".
        """
        if self.graph_client is not None:
            from sidestage.graph import get_entity
            entity = await get_entity(self.graph_client, character_id)
            if entity:
                return entity.model_dump_json()
            return "Character not found."
        else:
            char = self.storage.get_character(character_id)
            if char:
                return char.model_dump_json()
            return "Character not found."

    async def list_characters(self) -> str:
        """
        Lists all Characters in the world.

        Returns:
            JSON list of all Characters.
        """
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            chars = await list_entities(self.graph_client, entity_type="Character")
            return json.dumps([c.model_dump() for c in chars])
        else:
            chars = self.storage.list_characters()
            return json.dumps([n.model_dump() for n in chars])

    async def create_location(self, name: str, body: str) -> str:
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

        if self.graph_client is not None:
            from sidestage.graph import create_entity
            await create_entity(self.graph_client, loc)
        else:
            self.storage.add_location(loc)

        self._notify_change()
        return loc.model_dump_json()

    async def update_location(self, location_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str:
        """
        Updates an existing location.

        Args:
            location_id: The ID of the location to update.
            name: New name (optional).
            body: New markdown body (optional).

        Returns:
            JSON string of the updated location or error message.
        """
        if self.graph_client is not None:
            from sidestage.graph import get_entity, update_entity
            existing = await get_entity(self.graph_client, location_id)
            if not existing:
                return f"Error: Location with ID {location_id} not found."

            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = name
            if body is not None:
                updates["body"] = body

            if updates:
                updated = await update_entity(self.graph_client, location_id, updates)
            else:
                updated = existing
            self._notify_change()
            return updated.model_dump_json()
        else:
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

    async def list_locations(self) -> str:
        """
        Lists all locations in the world.

        Returns:
            JSON list of all locations.
        """
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            locs = await list_entities(self.graph_client, entity_type="Location")
            return json.dumps([loc.model_dump() for loc in locs])
        else:
            locs = self.storage.list_locations()
            return json.dumps([l.model_dump() for l in locs])

    async def create_item(self, name: str, body: str) -> str:
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

        if self.graph_client is not None:
            from sidestage.graph import create_entity
            await create_entity(self.graph_client, item)
        else:
            self.storage.add_item(item)

        self._notify_change()
        return item.model_dump_json()

    async def update_item(self, item_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str:
        """
        Updates an existing item.

        Args:
            item_id: The ID of the item to update.
            name: New name (optional).
            body: New markdown body (optional).

        Returns:
            JSON string of the updated item or error message.
        """
        if self.graph_client is not None:
            from sidestage.graph import get_entity, update_entity
            existing = await get_entity(self.graph_client, item_id)
            if not existing:
                return f"Error: Item with ID {item_id} not found."

            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = name
            if body is not None:
                updates["body"] = body

            if updates:
                updated = await update_entity(self.graph_client, item_id, updates)
            else:
                updated = existing
            self._notify_change()
            return updated.model_dump_json()
        else:
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

    async def list_items(self) -> str:
        """
        Lists all items in the world.

        Returns:
            JSON list of all items.
        """
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            items = await list_entities(self.graph_client, entity_type="Item")
            return json.dumps([i.model_dump() for i in items])
        else:
            items = self.storage.list_items()
            return json.dumps([i.model_dump() for i in items])
