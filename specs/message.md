# message: The unit of communication

A Message is created by an Actor and flows through the Scene from sender
to recipients via the event bus.

## message-dataflow

Every message flows through `scene.append(message)` — the POST handler
holds no special path. `append` records the message and emits
`EntityChanged`; reactions (npc response, SSE delivery) are driven by
listener fanout per `events-dataflow`. There is no Scene-side
orchestration (no `dispatch`, no `_respond`).

1. message-dataflow-receive: Message received by `Scene.append()` —
   either from REST (`rest-api-post-message`) or from a listener-spawned
   Actor response.
   - .implemented-by: Scene.append, rest-api-post-message
2. message-dataflow-record-emit: `scene.append` records the message,
   assigns the next index as MessageId, fires `EntityChanged` (per
   `events-dataflow-emit`).
   - .implemented-by: Scene.append, events-dataflow-emit
3. message-dataflow-react: Subscribed Characters' `notify` filters and
   spawns `_actor.respond` tasks; non-None responses recurse back through
   step 1 via `scene.append(response)`.
   - .implemented-by: Character.notify, events-dataflow-fan-out
