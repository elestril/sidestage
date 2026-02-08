# `sidestage.tools`

## Classes

### `WorldTools`

#### `__init__(storage: Storage, on_change: Optional[Callable[[], Any]] = None, graph_client: GraphClient | None = None)`

#### `create_character(name: str, body: str, location_id: Optional[str] = None) -> str` *async*

Creates a new Character in the world.

Args:
    name: Name of the Character.
    body: Markdown description of the Character.
    location_id: Optional ID of the location where the Character starts.

Returns:
    JSON string of the created Character.

#### `create_item(name: str, body: str) -> str` *async*

Creates a new item in the world.

Args:
    name: Name of the item.
    body: Markdown description of the item.

Returns:
    JSON string of the created item.

#### `create_location(name: str, body: str) -> str` *async*

Creates a new location in the world.

Args:
    name: Name of the location.
    body: Markdown description of the location.

Returns:
    JSON string of the created location.

#### `get_character(character_id: str) -> str` *async*

Retrieves details of a Character by ID.

Args:
    character_id: The unique ID of the Character.

Returns:
    JSON string of the Character details or "Not found".

#### `list_characters() -> str` *async*

Lists all Characters in the world.

Returns:
    JSON list of all Characters.

#### `list_items() -> str` *async*

Lists all items in the world.

Returns:
    JSON list of all items.

#### `list_locations() -> str` *async*

Lists all locations in the world.

Returns:
    JSON list of all locations.

#### `update_character(character_id: str, name: Optional[str] = None, body: Optional[str] = None, location_id: Optional[str] = None) -> str` *async*

Updates an existing Character.

Args:
    character_id: The ID of the Character to update.
    name: New name (optional).
    body: New markdown body (optional).
    location_id: New location ID (optional).

Returns:
    JSON string of the updated Character or error message.

#### `update_item(item_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str` *async*

Updates an existing item.

Args:
    item_id: The ID of the item to update.
    name: New name (optional).
    body: New markdown body (optional).

Returns:
    JSON string of the updated item or error message.

#### `update_location(location_id: str, name: Optional[str] = None, body: Optional[str] = None) -> str` *async*

Updates an existing location.

Args:
    location_id: The ID of the location to update.
    name: New name (optional).
    body: New markdown body (optional).

Returns:
    JSON string of the updated location or error message.
