# `sidestage.actors`

Actor hierarchy for Sidestage.

Actors control Characters in Scenes. The base Actor ABC defines the interface,
NPCActor provides LLM-driven NPC behavior, and User represents a human player
with WebSocket connections.

## Classes

### `Actor(ABC)`

Base class for anything that controls Characters in a Scene.

#### `__init__(actor_id: str)`

#### `process(event: Event) -> None` *async*

Handle an event. May enqueue response events via event.scene.process().

### `NPCActor(Actor)`

LLM-driven actor controlling an NPC character.

One NPCActor per NPC Character (1:1 mapping). The process() method
reacts to User-originated CHAT_MESSAGE events by generating LLM responses.

#### `__init__(actor_id: str, system_actor: bool = False, character: Any = None, scene_logic: Any = None, graph_client: Any = None, embed_config: Any = None, health: Any = None, scene_id: str | None = None, present_character_ids: list[str] | None = None, context_limit: int = 4096)`

#### `process(event: Event) -> None` *async*

React to events from User actors by generating LLM responses.

### `User(Actor)`

Represents a human player. Owns WebSocket connections.

One User per Campaign. The process() method sends events to all
connected WebSockets, replacing SyncManager.broadcast().

#### `__init__(actor_id: str = 'user')`

#### `connect(ws: Any) -> None` *async*

Accept and register a WebSocket connection.

#### `disconnect(ws: Any) -> None`

Remove a WebSocket connection.

#### `process(event: Event) -> None` *async*

Send event to all WebSocket connections.

#### `send(message: dict, exclude: Any = None) -> None` *async*

Send to all connections, optionally excluding one.
