# `sidestage.event`

Runtime event wrapper and async event queue.

The Event class carries an EventModel plus runtime context (tracing, scene
reference) that should NOT be persisted. The EventQueue processes Event
objects sequentially through a handler callback.

## Classes

### `Event`

Runtime event wrapper carrying model data, tracing context, and scene reference.

#### `__init__(model: EventModel, span_context: SpanContext | None = None, scene: object | None = None) -> None`

#### `character` *property*

Look up the originating Character via the scene's character registry.

#### `from_model(model: EventModel) -> Event`

Create an Event from an EventModel, capturing the current span context.

### `EventQueue`

Async event queue for sequential event processing.

Events (Event wrappers, not raw EventModel) are processed one at a time
by a single handler callback.

#### `put(event: Event) -> None` *async*

Add an event to the queue.

#### `start(handler: EventHandler) -> None` *async*

Start the background worker with the given handler.

#### `stop() -> None` *async*

Stop the background worker.
