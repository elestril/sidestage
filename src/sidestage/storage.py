import sqlite3
import json
from pathlib import Path
from typing import Type, List, Optional, cast
from agno.db.sqlite import SqliteDb
from sidestage.models import NPC, Location, Item, Entity

class Storage:
    def __init__(self, db: SqliteDb):
        self.db = db
        if db.db_file is None:
            raise ValueError("SqliteDb must have a db_file defined")
        self.db_path = Path(db.db_file)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS npcs (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS locations (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, data TEXT)")

    def _save_entity(self, table: str, entity: Entity):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} (id, data) VALUES (?, ?)",
                (entity.id, entity.model_dump_json())
            )

    def _get_entity(self, table: str, entity_id: str, model_cls: Type[Entity]) -> Optional[Entity]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            if row:
                return model_cls.model_validate_json(row[0])
            return None

    def _delete_entity(self, table: str, entity_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (entity_id,))

    def _list_entities(self, table: str, model_cls: Type[Entity]) -> List[Entity]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"SELECT data FROM {table}")
            return [model_cls.model_validate_json(row[0]) for row in cursor.fetchall()]

    # NPC
    def add_npc(self, npc: NPC):
        self._save_entity("npcs", npc)
    
    def update_npc(self, npc: NPC):
        self._save_entity("npcs", npc)

    def get_npc(self, npc_id: str) -> Optional[NPC]:
        return cast(Optional[NPC], self._get_entity("npcs", npc_id, NPC))

    def delete_npc(self, npc_id: str):
        self._delete_entity("npcs", npc_id)

    def list_npcs(self) -> List[NPC]:
        return cast(List[NPC], self._list_entities("npcs", NPC))

    # Location
    def add_location(self, location: Location):
        self._save_entity("locations", location)
    
    def update_location(self, location: Location):
        self._save_entity("locations", location)

    def get_location(self, location_id: str) -> Optional[Location]:
        return cast(Optional[Location], self._get_entity("locations", location_id, Location))

    def delete_location(self, location_id: str):
        self._delete_entity("locations", location_id)
        
    def list_locations(self) -> List[Location]:
        return cast(List[Location], self._list_entities("locations", Location))

    # Item
    def add_item(self, item: Item):
        self._save_entity("items", item)
    
    def update_item(self, item: Item):
        self._save_entity("items", item)

    def get_item(self, item_id: str) -> Optional[Item]:
        return cast(Optional[Item], self._get_entity("items", item_id, Item))

    def delete_item(self, item_id: str):
        self._delete_entity("items", item_id)

    def list_items(self) -> List[Item]:
        return cast(List[Item], self._list_entities("items", Item))
