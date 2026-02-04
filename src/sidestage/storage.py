import sqlite3
import json
from pathlib import Path
from typing import Type, List, Optional, cast, Union
from sidestage.models import Character, Location, Item, Entity, Scene, Event

class Storage:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS characters (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS locations (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS scenes (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, data TEXT)")

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

    # Character
    def add_character(self, character: Character):
        self._save_entity("characters", character)
    
    def update_character(self, character: Character):
        self._save_entity("characters", character)

    def get_character(self, character_id: str) -> Optional[Character]:
        return cast(Optional[Character], self._get_entity("characters", character_id, Character))

    def delete_character(self, character_id: str):
        self._delete_entity("characters", character_id)

    def list_characters(self) -> List[Character]:
        return cast(List[Character], self._list_entities("characters", Character))

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

    # Scene
    def add_scene(self, scene: Scene):
        self._save_entity("scenes", scene)

    def update_scene(self, scene: Scene):
        self._save_entity("scenes", scene)

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        return cast(Optional[Scene], self._get_entity("scenes", scene_id, Scene))

    def delete_scene(self, scene_id: str):
        self._delete_entity("scenes", scene_id)

    def list_scenes(self) -> List[Scene]:
        return cast(List[Scene], self._list_entities("scenes", Scene))

    # Event
    def add_event(self, event: Event):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO events (id, data) VALUES (?, ?)",
                (event.id, event.model_dump_json())
            )

    def list_all_entities(self) -> List[Entity]:
        all_entities: List[Entity] = []
        all_entities.extend(self.list_characters())
        all_entities.extend(self.list_locations())
        all_entities.extend(self.list_items())
        all_entities.extend(self.list_scenes())
        return all_entities
