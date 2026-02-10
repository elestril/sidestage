# `sidestage.scene`

Scene event loop.

Manages the runtime state of a Scene: event queue, character dispatch,
event persistence, and event creation factory.

## Classes

### `Scene`

Manages the runtime state and event loop of a specific Scene.

Orchestrates an EventQueue whose worker persists events, handles
event-type-specific logic, and dispatches to all present Actors.

#### `__init__(storage: Storage, data: SceneModel, campaign: Campaign, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, context_limit: int = 4096)`

#### `activate() -> None` *async*

Activate the scene: start event queue, load and activate characters.

#### `chat(actor_id: str, text: str, character_id: str | None = None) -> Event | None` *async*

Entry point for user chat. Creates event and enqueues it.

Returns the created Event, or None if chat was rejected.

#### `create_event(event_type: EventType, actor_id: str, body: str = '', character_id: str | None = None, metadata: dict[str, Any] | None = None, name: str | None = None) -> Event`

Factory to create an Event associated with this scene.

#### `deactivate() -> None` *async*

Deactivate the scene: stop queue and deactivate characters.

#### `id -> str` *property*

Get the unique identifier of the scene.

#### `process(event: Event) -> None` *async*

Enqueue an event into this scene's event loop.
