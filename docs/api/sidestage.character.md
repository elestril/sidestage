# `sidestage.character`

## Classes

### `AgentActor`

Represents the autonomous 'brain' of a Character in the simulation.

The AgentActor is responsible for:
1. Managing the LLM agent instance associated with the character.
2. Listening to the SceneMessageBus for relevant events.
3. Deciding when to respond to events (filtering logic).
4. Generating responses via the LLM and publishing them back to the bus.

#### `__init__(character: Character, scene_logic: Any, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, scene_id: str | None = None, present_character_ids: list[str] | None = None, context_limit: int = 4096)`

#### `on_event(event: Event) -> None` *async*

Callback handler for events published to the SceneMessageBus.

Responds to all ChatMessages except those originated by this actor.
Loop detection relies solely on origin tagging - agents never respond
to their own messages.

Args:
    event (Event): The event to process.

### `CharacterLogic`

Runtime wrapper for a Character entity within a Scene.

Manages the lifecycle of the character's 'brain' (AgentActor) and 
provides access to the underlying character data.

#### `__init__(character: Character, scene_logic: Any, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, scene_id: str | None = None, present_character_ids: list[str] | None = None, context_limit: int = 4096)`

#### `activate() -> None` *async*

Activate the character in the scene.

If the character is autonomous (not explicitly user-controlled, though currently all are agents),
this instantiates the AgentActor and subscribes it to the message bus.

#### `deactivate() -> None` *async*

Deactivate the character.

Unsubscribes the AgentActor from the bus and cleans up resources.
