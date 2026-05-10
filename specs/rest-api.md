# rest-api: HTTP API endpoints

Sidestage exposes a REST API for all state reads and mutations, and an SSE
endpoint for push notifications. All API paths are prefixed `/api/`. The SPA
root is served at `/`. All endpoints return 503 while `App.state == LOADING`.

## sse-dataflow: SSE notification dataflow

The SSE connection is server→client only. It carries `SceneUpdatedEvent`
notifications — pure state-change hints — all message content is fetched
via REST.

1. sse-dataflow-connect: Client opens `GET /api/events`.
   - .implements: cuj-hello-respond
2. sse-dataflow-lameduck: Server returns 503 if `App.state == LOADING`.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-events
3. sse-dataflow-accept: Server creates an `asyncio.Queue`, instantiates a
   `UserActor` bound to the active scene's human character, and injects
   the queue.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-events
4. sse-dataflow-event: Server yields each `SceneUpdatedEvent` dequeued
   from the queue as `event: scene_updated\ndata: <json>\n\n`.
   - .implemented-by: UserActor.notify_messages, rest-api-get-events
5. sse-dataflow-fetch: On each `scene_updated`, the client issues
   `GET /api/scenes/{scene_id}/messages?from=…&to=…` to fetch the slice
   it hasn't seen.
6. sse-dataflow-disconnect: On client disconnect, server removes `UserActor`,
   restores `StubActor`, and discards the queue.
   - .implemented-by: rest-api-get-events
7. sse-dataflow-reconnect: A new connection re-enters at sse-dataflow-connect.
   Missed events are NOT replayed; the client refetches via `GET /messages`.

## api-dataflow: REST request dataflow

The subscribe-then-fetch pattern ensures no events are missed between opening
the SSE stream and loading scene state.

1. api-dataflow-subscribe: Client opens SSE before fetching any state.
   - .implements: cuj-startup-ready
2. api-dataflow-scene: Client fetches `GET /api/scenes/active`; response
   yields `character_ids` and `player_character_ids`.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-scene
2a. api-dataflow-entities: Client fetches `GET /api/entities/{id}` for each
   `character_id`; responses populate the entity cache.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-entity
2b. api-dataflow-history: Client fetches `GET /api/scenes/{scene_id}/messages`
   to load existing history (omitting `from`/`to` for a full fetch).
3. api-dataflow-send: Client POSTs `MessageRequest` to
   `POST /api/scenes/{scene_id}/messages`.
   - .implements: cuj-hello-send, message-dataflow-receive
   - .implemented-by: rest-api-post-message
4. api-dataflow-dispatch: Server constructs `Message(sender, body)` and calls
   `scene.dispatch(message)` synchronously; the npc response cycle runs in
   a background task.
   - .implements: message-simplescene-dispatch
   - .implemented-by: rest-api-post-message
5. api-dataflow-respond: Server returns `201 Created` with `MessageAccepted{id}`.
   The message itself and any character response arrive via `scene_updated`
   SSE notifications followed by `GET /messages`.
   - .implements: cuj-hello-send
   - .implemented-by: rest-api-post-message

## rest-api-endpoints: Endpoints

### rest-api-get-root: GET /

- rest-api-root-static: Serves `src/sidestage/static/index.html` if the
  static directory exists.
- rest-api-root-fallback: Falls back to inline HTML if static dir is absent.
- rest-api-root-503: Returns 503 if `App.state == LOADING`.
- .implements: cuj-startup-ready
- .implemented-by: server-route-root

### rest-api-get-scene: GET /api/scenes/active

Returns the active scene. Entity content is NOT embedded — resolve each id
via `GET /api/entities/{id}`.

#### SceneResponse(BaseModel)

```python
class SceneResponse(BaseModel):
    id: EntityId
    name: str
    character_ids: list[EntityId]         # resolve each via GET /api/entities/{id}
    player_character_ids: list[EntityId]  # EntityIds this connection may send as
```

**Response 200** `SceneResponse`

- rest-api-scene-503: Returns 503 if `App.state == LOADING`.
- .implements: api-dataflow-scene
- .implemented-by: server-route-scene

### rest-api-get-entity: GET /api/entities/{entity_id}

Single source of truth for entity content. Returns `entity.serialize()` —
the concrete `Model` subclass discriminated by `type`.

```python
class EntityModel(BaseModel):       # base — Entity.Model
    id: EntityId
    name: str
    type: EntityType                 # discriminant
    body: str

class CharacterModel(EntityModel):  # Character.Model
    actor_type: str                  # "user" | "npc"
    model: str | None = None         # LLM model identifier for npc actors
```

**Response 200** `EntityModel` (or concrete subclass)
**Response 404** entity unknown or unresolved

- rest-api-entity-503: Returns 503 if `App.state == LOADING`.
- rest-api-entity-404: Returns 404 if `factory.get(entity_id)` returns None or the entity is unresolved.
- .implements: api-dataflow-entities
- .implemented-by: server-route-entity

### rest-api-get-messages: GET /api/scenes/{scene_id}/messages

Authoritative source for all messages in the scene, in append order. Clients
fetch this on initial load and on each `scene_updated` SSE notification —
typically requesting only the slice they don't already have.

**Query**
- `from: int` (optional, default `0`) — first message index, inclusive.
- `to: int` (optional, default `len(scene.messages) - 1`) — last message index, inclusive.

**Response 200** `list[Message.Model]`

- rest-api-get-messages-404: Returns 404 if `scene_id` does not match the active scene.
- rest-api-get-messages-503: Returns 503 if `App.state == LOADING`.
- rest-api-get-messages-422: Returns 422 if `from` or `to` are out of range, or if `from > to`.
- rest-api-get-messages-build: Builds the response as `[scene.serialize_message(i) for i in range(from, to + 1)]`.
- .implemented-by: server-route-get-messages

### rest-api-post-message: POST /api/scenes/{scene_id}/messages

Non-blocking acknowledgement endpoint. The handler resolves the sender, calls
`scene.dispatch(message)`, and returns the assigned `MessageId`. The full
message — and any character response — arrives at all connected clients via SSE.

#### MessageRequest(BaseModel)

```python
class MessageRequest(BaseModel):
    sender_id: EntityId  # must be one of SceneResponse.player_character_ids
    body: str
```

#### MessageAccepted(BaseModel)

```python
class MessageAccepted(BaseModel):
    id: MessageId  # the id assigned to the incoming message
```

**Request** `MessageRequest`
**Response 201** `MessageAccepted`

- rest-api-post-404: Returns 404 if `scene_id` does not match the active scene.
- rest-api-post-422: Returns 422 if the request body fails Pydantic validation, or if `sender_id` is not in `player_character_ids`.
- rest-api-post-503: Returns 503 if `App.state == LOADING`.
- rest-api-post-dispatch: Constructs `Message(sender, body)` (no id), calls `scene.dispatch(message)`, and returns the assigned `MessageId`. The handler does not await any response cycle.
- rest-api-post-returns: Returns `201 Created` with `MessageAccepted{id}`; the message itself and any character response arrive via SSE.
- .implements: api-dataflow-send, api-dataflow-dispatch, api-dataflow-respond,
  message-dataflow-receive, message-simplescene-dispatch
- .implemented-by: server-route-post-message

### rest-api-get-events: GET /api/events

SSE stream of scene-state notifications. Each event tells the client which
scene changed and what the latest message index is — content is fetched via
`GET /api/scenes/{scene_id}/messages?from=…&to=…`.

#### SceneUpdatedEvent(BaseModel)

```python
class SceneUpdatedEvent(BaseModel):
    scene_id: EntityId
    latest_message_index: int  # latest valid index in scene.messages
```

The shape is intentionally extensible — future fields can carry update hints
for other entity classes (e.g. `latest_character_revision`).

**Response** `text/event-stream`
Each frame: `event: scene_updated\ndata: <SceneUpdatedEvent JSON>\n\n`

- rest-api-events-503: Returns 503 if `App.state == LOADING`.
- rest-api-events-keepalive: Sends `": keepalive"` comment every 15 s to prevent proxy timeouts.
- rest-api-events-accept: On connect, creates an `asyncio.Queue`, instantiates a `UserActor` with that queue bound to the active scene's human character.
- rest-api-events-yield: Yields each `SceneUpdatedEvent` dequeued from the queue as a `scene_updated` event.
- rest-api-events-cleanup: On disconnect, removes the `UserActor`, restores a `StubActor`, and discards the queue.
- .implements: sse-dataflow-lameduck, sse-dataflow-accept, sse-dataflow-event, sse-dataflow-disconnect
- .implemented-by: server-route-events
