# `sidestage.bus`

## Classes

### `SceneMessageBus`

An asynchronous message bus dedicated to a single Scene.

The SceneMessageBus facilitates decoupled communication between components 
within a scene (e.g., Characters, Orchestrator, UI Sync). It supports:
- Multiple async subscribers (listeners).
- A single 'insert hook' for pre-processing or persistence before dispatch.
- Asynchronous publishing and processing via an asyncio Queue.

#### `__init__()`

Initialize the SceneMessageBus with an empty listener list and queue.

#### `publish(event: Event) -> None` *async*

Publish an event to the bus.

The event first passes through the insert hook (if configured). 
If the hook returns an event, it is added to the processing queue.

Args:
    event (Event): The event to publish.

#### `set_insert_hook(hook: Callable[Event, Awaitable[Event | None]]) -> None`

Set the insert hook for the bus.

The insert hook is called immediately upon `publish()`, BEFORE the event 
is added to the queue. It is useful for persistence, validation, or modification.

Args:
    hook (InsertHook): An async function that takes an Event and returns an Event (or None).

#### `start() -> None` *async*

Start the background worker task to process events from the queue.

This method is idempotent; calling it on an already running bus does nothing.

#### `stop() -> None` *async*

Stop the background worker task and cancel any pending processing.

This ensures the worker loop exits cleanly.

#### `subscribe(listener: Callable[Event, Coroutine[Any, Any, NoneType]]) -> None`

Add a listener to the bus.

Args:
    listener (EventListener): An async function to be called when an event is processed.

#### `unsubscribe(listener: Callable[Event, Coroutine[Any, Any, NoneType]]) -> None`

Remove a listener from the bus.

Args:
    listener (EventListener): The listener function to remove.
