# `sidestage.character`

## Classes

### `AgentActor`

Represents the autonomous 'brain' of a Character in the simulation.

The AgentActor is responsible for:
1. Managing the LLM agent instance associated with the character.
2. Processing events dispatched by the scene's EventQueue worker.
3. Generating responses via the LLM and putting them back on the queue.

#### `__init__(character: Character, scene_logic: Any, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, scene_id: str | None = None, present_character_ids: list[str] | None = None, context_limit: int = 4096)`

#### `on_event(event: Event) -> None` *async*

Handle an event dispatched by the scene's queue worker.

Called directly by SceneLogic._dispatch_to_npcs for user-originated
messages. Generates a response and puts it back on the queue.

Args:
    event (Event): The event to process.

### `CharacterLogic`

Runtime wrapper for a Character entity within a Scene.

Manages the lifecycle of the character's 'brain' (AgentActor) and 
provides access to the underlying character data.

#### `__init__(character: Character, scene_logic: Any, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, scene_id: str | None = None, present_character_ids: list[str] | None = None, context_limit: int = 4096)`

#### `activate() -> None` *async*

Activate the character in the scene.

Instantiates the AgentActor so the scene's queue worker can dispatch
events to it.

#### `deactivate() -> None` *async*

Deactivate the character.
