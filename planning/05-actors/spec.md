Restructure Classes

## Actor class

* `class Actor()`: Class that respresents an entity that can control a Character
* `class NPCActor(Actor)`: Replaces `AgentActor`  
* `class User(Actor)`: Represents a player. For now each `Campaign` has a single `user`, but multi-user will be implemented in the future.

* All Websockets are owned by a `User` object.

## Event class

* `class EventModel(EntityModel)` has no children. All use cases of their current child classes directly use the EventModel class. 
* All events are triggered by a Character. Events have a `character_id` field that points at the character.
* EventModel.entity_type is per-instance, and determines the exact event type. 
* ChatMessages use the Event.body for the contents. This can be rich markdown and incorporate any widgets. 
* Delete the fast-forward message for now, it's unused.
* The fast-forward message becomes a 'adjust gametime' event, it simply sets the `Event.gametime` field. 
* Delete `SceneModel.messages`. Those are part of `SecenModel.events` 

## The Event loop

* `async Scene.process(event:Event) -> None` 
* * Enqueues the Event into the Scene's queue. 
* * The Scene has a background thread that keeps listening on the queue, and calls `Secene._dispatch(event) -> None` 
* * The default implementation of `Secene._dispatch simply calls process on all present actors

* `async NPCActor.process(event:Event) -> None` 
* * Checks if `isInstance(event.character.actor) == User`, if so calls the LLMAgent, then enqueues the response back to `event.scene.process` 

## Tracing

The `Event` class (But not the EventModel) has an opentelemetry span. 
* The `Scene.process()` method replaces the spans of the incoming event with a new root span, but links the two spans.
* Spans contain full, unabridged remote llm calls, full prompts, all parameters, full responses.
* The sidestage config can enable local traces, in this case the traces are writting to a seperate `telemetry.db` sqllite db in the campaign dir. 
* Sending to an external collector is optional. 
* The Tracing page on the Web-Ui is functional (requires local telemetry.db)
* * It has a custom trace view, that renders a single message's trace.
* * The trace links on the chat ui are functional
