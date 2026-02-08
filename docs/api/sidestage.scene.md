# `sidestage.scene`

## Classes

### `SceneLogic`

Manages the runtime state and logic of a specific Scene.

This class orchestrates:
- The SceneMessageBus for event distribution.
- Active CharacterLogic instances (agents).
- Persistence of scene data via Storage.
- Creation and routing of chat messages.

#### `__init__(storage: Storage, agent: LiteLLMAgent, data: Scene, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, context_limit: int = 4096)`

#### `activate() -> None` *async*

Activate the scene.

Starts the message bus and activates all characters present in the campaign/scene.
This prepares the scene for interactive events.

#### `add_message(message: ChatMessage) -> None`

Legacy method to add a message directly.

Deprecated: Use `bus.publish(message)` instead to ensure event distribution.

#### `chat(user_message: ChatMessage) -> None` *async*

Entry point for user chat interaction.

Publishes the user message to the bus, which will trigger any listening
AgentActors to generate responses asynchronously.

Args:
    user_message (ChatMessage): The message from the user.

#### `create_message(actor_id: str, text: str, character_id: str | None = None) -> ChatMessage`

Factory method to create a ChatMessage associated with this scene.

This creates the object but does NOT publish or persist it. 
Use `bus.publish(message)` to send it.

Args:
    actor_id (str): The ID of the actor (e.g., 'user', 'agent').
    text (str): The content of the message.
    character_id (Optional[str]): The ID of the character persona. Defaults to actor_id if None.

Returns:
    ChatMessage: The constructed message object.

#### `deactivate() -> None` *async*

Deactivate the scene.

Stops the message bus and deactivates all characters.

#### `id -> str` *property*

Get the unique identifier of the scene.

#### `messages -> list[ChatMessage]` *property*

Get the list of messages in this scene.
