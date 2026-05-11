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
3. sse-dataflow-accept: Server creates an `asyncio.Queue` and registers it with
   the shared user actor via `App.get_actor("user").add_queue(queue)`.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-events
4. sse-dataflow-event: Server yields each `SceneUpdatedEvent` dequeued
   from the queue as `event: scene_updated\ndata: <json>\n\n`.
   - .implemented-by: UserActor.notify_messages, rest-api-get-events
5. sse-dataflow-fetch: On each `scene_updated`, the client issues
   `GET /api/campaigns/{cid}/scenes/{scene_id}/messages?from=…&to=…` to
   fetch the slice it hasn't seen.
   - .implemented-by: sse-client-event
6. sse-dataflow-disconnect: On client disconnect, server calls
   `App.get_actor("user").remove_queue(queue)` and discards the queue. The
   `UserActor` singleton stays in place for any other connected clients.
   - .implemented-by: rest-api-get-events
7. sse-dataflow-reconnect: A new connection re-enters at sse-dataflow-connect.
   Missed events are NOT replayed; the client refetches via `GET /messages`.
   - .implemented-by: sse-client-reconnect

## api-dataflow: REST request dataflow

The subscribe-then-fetch pattern ensures no events are missed between opening
the SSE stream and loading scene state. There is no singular "active scene" —
the client navigates to a scene of its choosing; multiple clients may attach
to different scenes simultaneously. Every campaign-bearing endpoint is
prefixed `/api/campaigns/{cid}` — today there is exactly one loaded campaign
but the prefix is the multi-campaign scaffold.

1. api-dataflow-subscribe: Client opens SSE before fetching any state.
   - .implements: cuj-startup-ready
2. api-dataflow-list-campaigns: Client fetches `GET /api/campaigns`; response
   yields the list of loaded campaigns. Today there is exactly one entry —
   the client picks it (or selects by name when multi-campaign loading lands).
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-list-campaigns
3. api-dataflow-campaign: Client fetches `GET /api/campaigns/{cid}`; response
   yields `name` and `default_scene_id` (a hint for which scene to load if
   the client has no other navigation context).
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-campaign
4. api-dataflow-scene: Client fetches `GET /api/campaigns/{cid}/scenes/{scene_id}`
   for the scene it wants to display (typically `default_scene_id`); response
   yields `character_ids` and `player_character_ids`.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-scene
4a. api-dataflow-entities: Client fetches `GET /api/campaigns/{cid}/entities/{id}`
   for each `character_id`; responses populate the entity cache.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-entity
4b. api-dataflow-history: Client fetches
   `GET /api/campaigns/{cid}/scenes/{scene_id}/messages` to load existing
   history (omitting `from`/`to` for a full fetch).
5. api-dataflow-send: Client POSTs `MessageRequest` to
   `POST /api/campaigns/{cid}/scenes/{scene_id}/messages`.
   - .implements: cuj-hello-send, message-dataflow-receive
   - .implemented-by: rest-api-post-message
6. api-dataflow-dispatch: Server calls `scene.dispatch(message)` synchronously;
   the npc response cycle runs in a background task.
   - .implements: message-simplescene-dispatch
   - .implemented-by: rest-api-post-message
7. api-dataflow-respond: Server returns `201 Created` with `MessageAccepted{id}`.
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

### rest-api-list-campaigns: GET /api/campaigns

Returns the list of loaded campaigns. The client calls this first on load,
then picks a campaign id (or chooses by name) and uses it as the `{cid}` path
parameter on every subsequent campaign-scoped endpoint. Today the list always
contains exactly one entry; the shape is the multi-campaign scaffold.

**Response 200** `list[CampaignResponse]`

- rest-api-list-campaigns-503: Returns 503 if `App.state == LOADING`.
- .implements: api-dataflow-list-campaigns
- .implemented-by: server-route-list-campaigns

### rest-api-get-campaign: GET /api/campaigns/{cid}

Returns campaign-level metadata. Used by the client after `GET /api/campaigns`
to learn the campaign name and the optional `default_scene_id` hint.

#### CampaignResponse(BaseModel)

```python
class CampaignResponse(BaseModel):
    name: str
    default_scene_id: EntityId | None  # hint for the client; absent = "client picks"
```

**Response 200** `CampaignResponse`
**Response 404** `cid` not found in `App.campaigns`

- rest-api-campaign-503: Returns 503 if `App.state == LOADING`.
- rest-api-campaign-404: Returns 404 if `App.campaigns.get(cid)` is None.
- .implements: api-dataflow-campaign
- .implemented-by: server-route-campaign

### rest-api-get-scenes: GET /api/campaigns/{cid}/scenes

Returns the list of scenes in the campaign. Each entry is a `SceneResponse`
(same shape as `GET /api/campaigns/{cid}/scenes/{id}`); the client uses the
list to navigate.

**Response 200** `list[SceneResponse]`
**Response 404** `cid` not found

- rest-api-scenes-503: Returns 503 if `App.state == LOADING`.
- rest-api-scenes-404: Returns 404 if `App.campaigns.get(cid)` is None.
- .implements: api-dataflow-scene
- .implemented-by: server-route-scenes

### rest-api-get-scene: GET /api/campaigns/{cid}/scenes/{scene_id}

Returns the named scene. Entity content is NOT embedded — resolve each id
via `GET /api/campaigns/{cid}/entities/{id}`.

#### SceneResponse(BaseModel)

```python
class SceneResponse(BaseModel):
    id: EntityId
    name: str
    character_ids: list[EntityId]         # resolve each via GET /api/campaigns/{cid}/entities/{id}
    player_character_ids: list[EntityId]  # EntityIds this connection may send as
```

**Response 200** `SceneResponse`
**Response 404** `cid` or `scene_id` not found in this campaign

- rest-api-scene-503: Returns 503 if `App.state == LOADING`.
- rest-api-scene-404: Returns 404 if `App.campaigns.get(cid)` is None or `campaign.scene(scene_id)` returns None.
- .implements: api-dataflow-scene
- .implemented-by: server-route-scene

### rest-api-get-entity: GET /api/campaigns/{cid}/entities/{entity_id}

Single source of truth for entity content. Returns `entity.serialize()` —
the concrete `Model` subclass discriminated by `type`.

```python
class EntityModel(BaseModel):       # base — Entity.Model
    id: EntityId
    name: str
    type: EntityType                 # discriminant
    body: str

class CharacterModel(EntityModel):  # Character.Model
    owner: Literal["user", "npc", "stub"]  # selects the runtime Actor via App.get_actor
```

**Response 200** `EntityModel` (or concrete subclass)
**Response 404** campaign unknown, or entity unknown / unresolved

- rest-api-entity-503: Returns 503 if `App.state == LOADING`.
- rest-api-entity-404: Returns 404 if `App.campaigns.get(cid)` is None, if `campaign.factory.get(entity_id)` returns None, or if the entity is unresolved.
- .implements: api-dataflow-entities
- .implemented-by: server-route-entity

### rest-api-get-messages: GET /api/campaigns/{cid}/scenes/{scene_id}/messages

Authoritative source for all messages in the scene, in append order. Clients
fetch this on initial load and on each `scene_updated` SSE notification —
typically requesting only the slice they don't already have.

**Query** — half-open range, Python slice semantics:
- `from: int` (optional, default `0`) — first message index, inclusive.
- `to: int` (optional, default `len(scene.messages)`) — end of range, exclusive.

**Response 200** `list[Message.Model]`

- rest-api-get-messages-404: Returns 404 if `App.campaigns.get(cid)` is None or `campaign.scene(scene_id)` returns None.
- rest-api-get-messages-503: Returns 503 if `App.state == LOADING`.
- rest-api-get-messages-empty: An empty scene returns 200 with `[]` for the default range
  (`from=0, to=0`). Empty result is a valid state, NOT a 422.
- rest-api-get-messages-422: Returns 422 if `from` or `to` are negative, if `from > to`, or
  if `to > len(scene.messages)`.
- rest-api-get-messages-build: Builds the response as `[scene.serialize_message(i) for i in range(from, to)]`.
- .implemented-by: server-route-get-messages

### rest-api-post-message: POST /api/campaigns/{cid}/scenes/{scene_id}/messages

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

- rest-api-post-404: Returns 404 if `App.campaigns.get(cid)` is None or `campaign.scene(scene_id)` returns None.
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
- rest-api-events-accept: On connect, creates an `asyncio.Queue` and registers it with the
  user-owned actor: `App.get_actor("user").add_queue(queue)`. The UserActor singleton is shared
  across all connected SSE clients; no actor swap happens at connect time.
- rest-api-events-yield: Yields each `SceneUpdatedEvent` dequeued from the queue as a `scene_updated` event.
- rest-api-events-cleanup: On disconnect, calls `App.get_actor("user").remove_queue(queue)`
  and discards the queue. The UserActor singleton remains in place for other connected clients.
- .implements: sse-dataflow-lameduck, sse-dataflow-accept, sse-dataflow-event, sse-dataflow-disconnect
- .implemented-by: server-route-events
