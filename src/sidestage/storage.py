import sqlite3
import json
from pathlib import Path
from typing import Type, List, Optional, cast, Union
from sidestage.models import CharacterModel, LocationModel, ItemModel, EntityModel, SceneModel, EventModel

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

    def _save_entity(self, table: str, entity: EntityModel):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} (id, data) VALUES (?, ?)",
                (entity.id, entity.model_dump_json())
            )

    def _get_entity(self, table: str, entity_id: str, model_cls: Type[EntityModel]) -> Optional[EntityModel]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            if row:
                return model_cls.model_validate_json(row[0])
            return None

    def _delete_entity(self, table: str, entity_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (entity_id,))

    def _list_entities(self, table: str, model_cls: Type[EntityModel]) -> List[EntityModel]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"SELECT data FROM {table}")
            return [model_cls.model_validate_json(row[0]) for row in cursor.fetchall()]

    # Character
    def add_character(self, character: CharacterModel):
        self._save_entity("characters", character)

    def update_character(self, character: CharacterModel):
        self._save_entity("characters", character)

    def get_character(self, character_id: str) -> Optional[CharacterModel]:
        return cast(Optional[CharacterModel], self._get_entity("characters", character_id, CharacterModel))

    def delete_character(self, character_id: str):
        self._delete_entity("characters", character_id)

    def list_characters(self) -> List[CharacterModel]:
        return cast(List[CharacterModel], self._list_entities("characters", CharacterModel))

    # Location
    def add_location(self, location: LocationModel):
        self._save_entity("locations", location)

    def update_location(self, location: LocationModel):
        self._save_entity("locations", location)

    def get_location(self, location_id: str) -> Optional[LocationModel]:
        return cast(Optional[LocationModel], self._get_entity("locations", location_id, LocationModel))

    def delete_location(self, location_id: str):
        self._delete_entity("locations", location_id)

    def list_locations(self) -> List[LocationModel]:
        return cast(List[LocationModel], self._list_entities("locations", LocationModel))

    # Item
    def add_item(self, item: ItemModel):
        self._save_entity("items", item)

    def update_item(self, item: ItemModel):
        self._save_entity("items", item)

    def get_item(self, item_id: str) -> Optional[ItemModel]:
        return cast(Optional[ItemModel], self._get_entity("items", item_id, ItemModel))

    def delete_item(self, item_id: str):
        self._delete_entity("items", item_id)

    def list_items(self) -> List[ItemModel]:
        return cast(List[ItemModel], self._list_entities("items", ItemModel))

    # Scene
    def add_scene(self, scene: SceneModel):
        self._save_entity("scenes", scene)

    def update_scene(self, scene: SceneModel):
        self._save_entity("scenes", scene)

    def get_scene(self, scene_id: str) -> Optional[SceneModel]:
        return cast(Optional[SceneModel], self._get_entity("scenes", scene_id, SceneModel))

    def delete_scene(self, scene_id: str):
        self._delete_entity("scenes", scene_id)

    def list_scenes(self) -> List[SceneModel]:
        return cast(List[SceneModel], self._list_entities("scenes", SceneModel))

    # Event
    def add_event(self, event: EventModel):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO events (id, data) VALUES (?, ?)",
                (event.id, event.model_dump_json())
            )

    def list_all_entities(self) -> List[EntityModel]:
        all_entities: List[EntityModel] = []
        all_entities.extend(self.list_characters())
        all_entities.extend(self.list_locations())
        all_entities.extend(self.list_items())
        all_entities.extend(self.list_scenes())
        return all_entities
