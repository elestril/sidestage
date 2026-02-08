# `sidestage.bus`

## Classes

### `EventQueue`

A simple async event queue for a Scene.

Events are processed sequentially by a single handler callback.
No subscriptions, no hooks — the handler does all the work.

#### `put(event: EventModel) -> None` *async*

Add an event to the queue.

#### `start(handler: Callable[EventModel, Awaitable[NoneType]]) -> None` *async*

Start the background worker with the given handler.

#### `stop() -> None` *async*

Stop the background worker.
