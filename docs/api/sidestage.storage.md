# `sidestage.storage`

## Classes

### `Storage`

#### `__init__(db_path: str | Path)`

#### `add_character(character: Character)`

#### `add_event(event: Event)`

#### `add_item(item: Item)`

#### `add_location(location: Location)`

#### `add_scene(scene: Scene)`

#### `delete_character(character_id: str)`

#### `delete_item(item_id: str)`

#### `delete_location(location_id: str)`

#### `delete_scene(scene_id: str)`

#### `get_character(character_id: str) -> Character | None`

#### `get_item(item_id: str) -> Item | None`

#### `get_location(location_id: str) -> Location | None`

#### `get_scene(scene_id: str) -> Scene | None`

#### `list_all_entities() -> list[Entity]`

#### `list_characters() -> list[Character]`

#### `list_items() -> list[Item]`

#### `list_locations() -> list[Location]`

#### `list_scenes() -> list[Scene]`

#### `update_character(character: Character)`

#### `update_item(item: Item)`

#### `update_location(location: Location)`

#### `update_scene(scene: Scene)`
