# `sidestage.scene`

## Classes

### `Scene`

Manages the runtime state and logic of a specific Scene.

This class orchestrates:
- An EventQueue whose worker persists, broadcasts, and dispatches events.
- Active Character instances (agents).
- Persistence of scene data via Storage.
- Creation and routing of chat messages.

#### `__init__(storage: Storage, agent: LiteLLMAgent, data: SceneModel, graph_client: GraphClient | None = None, embed_config: LLMConfig | None = None, health: CampaignHealth | None = None, context_limit: int = 4096)`

#### `activate() -> None` *async*

Activate the scene.

Starts the event queue and activates all characters present in the campaign/scene.

#### `chat(user_message: ChatMessageModel) -> None` *async*

Entry point for user chat interaction.

Puts the user message on the event queue. The queue worker will
persist it, broadcast it, and dispatch it to NPCs.

Args:
    user_message (ChatMessageModel): The message from the user.

#### `create_message(actor_id: str, text: str, character_id: str | None = None) -> ChatMessageModel`

Factory method to create a ChatMessage associated with this scene.

This creates the object but does NOT publish or persist it.
Use `queue.put(message)` to send it.

Args:
    actor_id (str): The ID of the actor (e.g., 'user', 'agent').
    text (str): The content of the message.
    character_id (Optional[str]): The ID of the character persona. Defaults to actor_id if None.

Returns:
    ChatMessageModel: The constructed message object.

#### `deactivate() -> None` *async*

Deactivate the scene.

Stops the event queue and deactivates all characters.

#### `id -> str` *property*

Get the unique identifier of the scene.

#### `messages -> list[ChatMessageModel]` *property*

Get the list of messages in this scene.

#### `set_broadcast(fn: Callable[ChatMessageModel, Awaitable[NoneType]]) -> None`

Set the callback used to broadcast events to websocket clients.
