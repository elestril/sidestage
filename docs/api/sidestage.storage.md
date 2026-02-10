# `sidestage.storage`

## Classes

### `Storage`

#### `__init__(db_path: str | Path)`

#### `add_character(character: CharacterModel)`

#### `add_event(event: EventModel)`

#### `add_item(item: ItemModel)`

#### `add_location(location: LocationModel)`

#### `add_scene(scene: SceneModel)`

#### `delete_character(character_id: str)`

#### `delete_item(item_id: str)`

#### `delete_location(location_id: str)`

#### `delete_scene(scene_id: str)`

#### `get_character(character_id: str) -> CharacterModel | None`

#### `get_item(item_id: str) -> ItemModel | None`

#### `get_location(location_id: str) -> LocationModel | None`

#### `get_scene(scene_id: str) -> SceneModel | None`

#### `list_all_entities() -> list[EntityModel]`

#### `list_characters() -> list[CharacterModel]`

#### `list_events_by_scene(scene_id: str, event_type: EventType | None = None) -> list[EventModel]`

List events for a scene, optionally filtered by event_type.

#### `list_items() -> list[ItemModel]`

#### `list_locations() -> list[LocationModel]`

#### `list_scenes() -> list[SceneModel]`

#### `update_character(character: CharacterModel)`

#### `update_item(item: ItemModel)`

#### `update_location(location: LocationModel)`

#### `update_scene(scene: SceneModel)`
