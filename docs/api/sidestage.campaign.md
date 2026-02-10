# `sidestage.campaign`

## Classes

### `Campaign`

Represents a specific Campaign (a distinct save/world).

The Campaign class serves as the container for:
- Configuration (LLM settings)
- Storage (Database connection)
- World Tools (Entity manipulation logic)
- Actor infrastructure (User actor, Character registry)
- Defaults/Seeding (Characters, Scenes)

#### `__init__(name: str, base_dir: Path)`

Initialize the Campaign.

Args:
    name (str): The name of the campaign.
    base_dir (Path): The root directory where campaign data is stored.

#### `create_scene(name: str, description: str, current_gametime: int | None) -> SceneModel` *async*

Create and persist a new scene.

#### `export_entities() -> int` *async*

Export all entities to markdown files in the campaign directory.

#### `get_character(model: CharacterModel) -> Character`

Get or create a Character instance for the given model.

#### `get_entity_markdown(entity_id: str) -> str | None` *async*

Retrieve the markdown representation of an entity by ID.

#### `get_llm_config(name: str = 'default') -> LLMConfig`

Get a named LLM configuration.

Args:
    name: The LLM config name (e.g. 'default', 'embed').

Raises:
    KeyError: If the named LLM config doesn't exist.

#### `get_scene_events(scene_id: str) -> list[EventModel] | None`

Get all events for a specific scene.

#### `get_scene_messages(scene_id: str) -> list[EventModel] | None`

Get chat message events for a specific scene.

#### `get_scene_object(scene_id: str) -> Scene | None`

Factory to get a Scene object for the given ID.

Args:
    scene_id (str): The scene ID.

Returns:
    Optional[Scene]: The logic object, or None if scene doesn't exist.

#### `import_entities() -> int` *async*

Import all entities from markdown files in the campaign directory.

#### `list_entities() -> list[dict[str, Any]]` *async*

List all entities as dictionaries with an added 'type' field.

#### `list_scenes() -> list[dict[str, Any]]` *async*

List all scenes in the campaign.

#### `reload_defaults() -> None`

Load default entities from data/campaign_defaults/markdown/.

Uses the migration parser to read all entity types (characters, scenes,
locations, items, events) and upserts them into the database.

#### `shutdown() -> None` *async*

Shut down the campaign, closing graph connections.

#### `start_graph() -> None` *async*

Initialize the FalkorDB graph connection.

Must be called after __init__ and before any graph operations.
Derives graph_name from campaign name if not configured.

#### `update_entity(entity_id: str, data: dict[str, Any]) -> bool` *async*

Update an entity with a dictionary of fields.

#### `update_entity_markdown(entity_id: str, markdown: str) -> bool` *async*

Update an entity based on its markdown representation.
