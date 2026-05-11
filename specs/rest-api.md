# rest-api: HTTP API endpoints

Sidestage exposes a REST API for all state reads and mutations, and an SSE
endpoint for push notifications. All API paths are prefixed `/api/`. The SPA
root is served at `/`. All endpoints return 503 while `App.state == LOADING`.

## sse-dataflow: SSE notification dataflow

The SSE connection is server→client only and per-entity. It carries
`EntityChanged` events (per `events.md`) — pure state-change hints —
all message content is fetched via REST.

1. sse-dataflow-connect: Client opens `GET /api/campaigns/{cid}/entities/{eid}/events`.
   - .implements: cuj-hello-respond
2. sse-dataflow-lameduck: Server returns 503 if `App.state == LOADING`.
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-entity-events
3. sse-dataflow-accept: Server creates an `asyncio.Queue` and routes it
   through the user's actor: `App.get_actor(current_user).subscribe_to(entity, queue)`.
   The actor wraps the queue in a `QueueListener` and registers it on the
   target entity (per `events-pattern-subscription`).
   - .implements: cuj-startup-ready
   - .implemented-by: rest-api-get-entity-events
4. sse-dataflow-event: Server yields each `EntityChanged` dequeued from
   the queue as `event: entity_changed\ndata: <json>\n\n`.
   - .implemented-by: UserActor.subscribe_to, rest-api-get-entity-events
5. sse-dataflow-fetch: On each `entity_changed` for a scene entity, the
   client issues `GET /api/campaigns/{cid}/scenes/{sid}/messages?from=…&to=…`
   to fetch the slice it hasn't seen.
   - .implemented-by: sse-client-event
6. sse-dataflow-disconnect: On client disconnect, server calls
   `App.get_actor(current_user).unsubscribe_from(entity, queue)`. The
   UserActor stays in place for any other connected clients.
   - .implemented-by: rest-api-get-entity-events
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
6. api-dataflow-dispatch: Server calls `scene.append(message)` synchronously
   (per `events-dataflow`); this fires `EntityChanged`, listeners react,
   the npc response cycle runs as listener-spawned background tasks.
   - .implemented-by: rest-api-post-message, events-dataflow-emit
7. api-dataflow-respond: Server returns `201 Created` with
   `MessageAccepted{scene_id, index}`. The message itself and any
   character response arrive via `entity_changed` SSE notifications
   followed by `GET /messages`.
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
    owner: Literal["user", "stub"]  # selects the runtime Actor via App.get_actor
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
`scene.append(message)`, and returns `(scene_id, index)`. The full message —
and any character response — arrives at all connected clients via SSE.

#### MessageRequest(BaseModel)

```python
class MessageRequest(BaseModel):
    sender_id: EntityId  # must be one of SceneResponse.player_character_ids
    body: str
```

#### MessageAccepted(BaseModel)

```python
class MessageAccepted(BaseModel):
    scene_id: EntityId
    index: int
```

**Request** `MessageRequest`
**Response 201** `MessageAccepted`

- rest-api-post-404: Returns 404 if `App.campaigns.get(cid)` is None or `campaign.scene(scene_id)` returns None.
- rest-api-post-422: Returns 422 if the request body fails Pydantic validation, or if `sender_id` is not in `player_character_ids`.
- rest-api-post-503: Returns 503 if `App.state == LOADING`.
- rest-api-post-dispatch: Constructs `Message(sender, body)`, calls `scene.append(message)` (per `events-dataflow`), packs the returned index plus the scene id into `MessageAccepted`. The handler does not await the npc response cycle — it fires asynchronously via listener fanout.
- rest-api-post-returns: Returns `201 Created` with `MessageAccepted{scene_id, index}`; the message itself and any character response arrive via SSE.
- .implements: api-dataflow-send, api-dataflow-dispatch, api-dataflow-respond
- .implemented-by: server-route-post-message

### rest-api-get-entity-events: GET /api/campaigns/{cid}/entities/{eid}/events

Per-entity SSE stream of `EntityChanged` events (per `events.md`). Clients
open one connection per entity they care about; no global firehose.

`EntityChanged` shape (from `events-event-changed`):

```python
class EntityChanged(BaseModel):
    entity_id: EntityId
    hint: ChangeHint | None = None   # discriminated union; SceneChangeHint today
```

**Response** `text/event-stream`
Each frame: `event: entity_changed\ndata: <EntityChanged JSON>\n\n`

- rest-api-events-503: Returns 503 if `App.state == LOADING`.
- rest-api-events-404: 404 if `cid` or `eid` doesn't resolve.
- rest-api-events-keepalive: `": keepalive"` comment every 15 s to prevent proxy timeouts.
- rest-api-events-accept: On connect, creates an `asyncio.Queue` and routes
  through `App.get_actor(current_user).subscribe_to(entity, queue)`. The
  UserActor wraps it in a `QueueListener` and registers with the entity.
- rest-api-events-yield: Yields each `EntityChanged` dequeued from the queue as an `entity_changed` event.
- rest-api-events-cleanup: On disconnect, calls `App.get_actor(current_user).unsubscribe_from(entity, queue)`.
- .implements: sse-dataflow-lameduck, sse-dataflow-accept, sse-dataflow-event, sse-dataflow-disconnect, events-subscription
- .implemented-by: server-route-entity-events
