# frontend: React workspace UI

The Sidestage frontend is a React + TypeScript + Tailwind single-page
application built with Vite. In development, Vite's dev server proxies `/api`
to FastAPI. In production, FastAPI serves the built static bundle.

The SPA is organised as a **workspace** that hosts **panels**. A panel is
either bound to a single Entity (an *entity panel*, live-subscribed to that
entity's `entity_changed` stream) or carries no entity binding (a *workspace
panel*, e.g. the selector). Every Entity additionally has a compact
**bubble** renderer used by selectors and lists.

## frontend-project: Project layout

```
frontend/
|- package.json
|- vite.config.ts      proxy /api → localhost:8000 in dev
|- tailwind.config.ts
|- index.html
|- src/
   |- main.tsx
   |- types.ts                wire format types + EntityId brand
   |- types_ext.ts            branded EntityId + EntityResponse union
   |- hooks/
   |  |- useEntity.ts         per-panel bootstrap + SSE
   |  |- useSendMessage.ts
   |- components/
      |- App.tsx              renders Workspace
      |- Workspace.tsx        campaign bootstrap + two-slot layout
      |- EntitySelector.tsx   workspace panel: filtered bubble list
      |- SceneBubble.tsx      compact Scene snapshot
      |- EntityPanel.tsx      dispatcher on entity.type
      |- SceneEntityPanel.tsx scene header + chat
      |- MessageList.tsx      Scene panel internal
      |- MessageItem.tsx      Scene panel internal
      |- MessageInput.tsx     Scene panel internal
```

Build output: `frontend/dist/` copied to `src/sidestage/static/` by the
production build step.

- frontend-vite-root: `vite.config.ts` sets `root` to `path.resolve(__dirname)` so all paths resolve relative to the config file regardless of invocation directory.
- frontend-vite-proxy: `vite.config.ts` proxies `/api` to `http://localhost:8000` with `changeOrigin: true`. SSE works through this proxy without special config.
- frontend-build-output: `vite.config.ts` sets `build.outDir` to `path.resolve(__dirname, '../src/sidestage/static')` — absolute, invocation-independent.

## frontend-serve: Production static serving

- frontend-serve-mount: `App._setup_routes()` mounts `StaticFiles` at `/` serving
  `src/sidestage/static/` when that directory exists, replacing the inline HTML fallback.
- frontend-serve-spa: The mount uses `html=True` so all non-API paths return `index.html`
  (standard SPA routing support).
- .implements: cuj-startup-ready

## frontend-types: TypeScript wire types

`frontend/src/types.ts` is **auto-generated** and **gitignored** — it is
recreated from the Pydantic models on every consumer invocation (typecheck,
test, build, dev-server). It is never hand-edited.

- frontend-types-generated: `frontend/src/types.ts` is produced by
  `just _gen-types`, which runs
  `uv run pydantic2ts --module sidestage.server --output frontend/src/types.ts
  --json2ts-cmd frontend/node_modules/.bin/json2ts`. Every consumer
  recipe (`_tsc`, `test-fe`, `build`, `_vite-up`) declares `_gen-types`
  as a dependency, so the file is always fresh against the current
  backend wire shape.
- frontend-types-gitignored: `frontend/src/types.ts` is listed in
  `.gitignore`. It does NOT live in version control; the source of
  truth is the Pydantic models. A fresh clone gets a working file on
  the first `just <consumer>` invocation.
- frontend-types-source: The authoritative source is the Pydantic
  `BaseModel` subclasses reachable from `sidestage.server`:
  `CampaignResponse`, `CharacterResponse`, `SceneResponse`,
  `MessageRequest`, `MessageAccepted`. Two wire types pydantic2ts
  cannot surface (`MessageModel` — a nested `Message.Model`;
  `EntityChangedEvent` — a `@dataclass`, not Pydantic) are hand-rolled
  in `types_ext.ts` and must be kept in sync with the backend manually.
- frontend-types-entityid: `EntityId` is generated as `string` (Pydantic's
  `NewType` has no TypeScript equivalent). A branded alias
  `type EntityId = string & { readonly _brand: 'EntityId' }` is added
  manually in a thin `frontend/src/types_ext.ts` that re-exports everything
  from `types.ts` with id-bearing fields rebranded. All application
  code imports from `types_ext.ts`, never directly from `types.ts`.
- frontend-types-discriminated: `ServerEvent = EntityChangedEvent` is
  defined in `types_ext.ts`. Today there is exactly one event variant;
  the type is a discriminated union scaffold for future variants.
- frontend-types-entity-response: `types_ext.ts` defines
  `EntityResponse = SceneResponse | CharacterResponse` as a discriminated
  union over `type`. This shape is the wire result of
  `GET /api/campaigns/{cid}/entities/{eid}`; the FE panel dispatcher
  narrows on `response.type`.

## frontend-workspace: Workspace shell

The Workspace is the SPA's top-level shell. It is **campaign-scoped**:
one campaign is active at a time; there is no campaign-switcher UI today.
Its layout is a **static two-slot grid** — a selector slot on the left,
a single main slot on the right. The user-arrangeable, multi-panel UI
is future work; today's static layout MUST be implementable on a panel
model that survives that evolution without rework.

- frontend-workspace-state: Workspace state is
  `{ campaignId: string | null, defaultSceneId: EntityId | null, mainEntityId: EntityId | null }`.
  Each per-panel data stream (entity, dependents, messages, connected)
  lives inside the panel's own `useEntity` hook — NOT at the workspace
  level. The workspace owns only what the slots themselves need.
- frontend-workspace-layout: Static two-slot CSS layout. Left slot
  renders `<EntitySelector campaignId={campaignId} />`. Right slot
  renders `<EntityPanel entityId={mainEntityId} campaignId={campaignId} />`
  when both ids are set, otherwise a "select a scene from the left"
  placeholder.
- frontend-workspace-bootstrap: On mount the Workspace fetches
  `GET /api/campaigns` → picks the first entry's `name` as `campaignId`
  (today's single-campaign assumption) → fetches `GET /api/campaigns/{cid}`
  → stores `default_scene_id` as `defaultSceneId`. The Workspace's
  bootstrap is the only thing in the SPA that runs before any panel
  mounts.
  - .implements: cuj-startup-ready
- frontend-workspace-initial-main: After bootstrap, `mainEntityId` is set
  to the URL fragment (if present) else `defaultSceneId`. If both are
  null, `mainEntityId` stays null and the main slot shows the empty
  placeholder.
- frontend-workspace-open-entity: The selector emits `onOpenEntity(id)`
  on double-click; the workspace sets `mainEntityId = id`. If the
  emitted id equals the current `mainEntityId`, the call is a no-op
  (idempotent). Single-click is currently unbound.
- frontend-workspace-remount-on-change: When `mainEntityId` changes the
  right-slot `EntityPanel` unmounts and the new one mounts. Per-panel
  state (half-typed input, scroll position, message history) does not
  bleed across entity switches.

## frontend-panel-taxonomy: Panel taxonomy

Three kinds of renderer; each entity type defines its first two; the
third is the workspace's own.

- frontend-panel-entity: An **entity panel** is bound to one entity by id,
  fetches that entity (and any dependents it needs), and subscribes to
  `/api/campaigns/{cid}/entities/{eid}/events`. Dispatched by `entity.type`.
- frontend-panel-bubble: An **entity bubble** is a compact snapshot
  renderer for an entity, used inside selectors and lists. Bubbles do
  NOT subscribe to events today — they render whatever snapshot the
  parent passed them, and refresh only when the parent re-fetches.
  Live-subscribing bubbles is deferred to a later iteration.
- frontend-panel-workspace: A **workspace panel** carries no entity
  binding. It may fetch and render entity data (the selector renders a
  list of bubbles) but is itself a property of the workspace, not of
  an entity.

## frontend-panel-registry: Today's registered types

Only the Scene entity has a registered panel and bubble. Other entity
types (Character, generic Entity, …) appear in the data model but have
no registered renderers — see `frontend-entitypanel-fallback`.

- frontend-panel-registry-scene: `entity.type === 'scene'` →
  `SceneEntityPanel` (entity panel) and `SceneBubble` (bubble).
- frontend-panel-registry-fallback: Any other `entity.type` →
  `UnknownEntityPanel` placeholder; bubble dispatch returns a generic
  text fallback. Adding a new entity type's panel is a pure additive
  spec change (extend `frontend-panel-registry-*`, add the dispatch
  case in `EntityPanel.tsx`).

## frontend-workspace-be-consistency: Per-panel SPA/backend consistency

The consistency rule from the previous architecture (SPA state equals
the backend's authoritative state, modulo at most one in-flight
`entity_changed` event) survives intact — it now applies **per panel**.
Each entity panel's `useEntity` hook independently re-fetches the full
state of its entity (and dependents) on any disconnect/reconnect window.

- frontend-be-consistency-event-loss: Per panel, any disconnect window
  (SSE close, reconnect backoff, panel mount) is an event-loss window.
  The panel cannot rely on incremental catch-up — the backend's history
  may have shrunk (a dev reload that wiped runtime state) or diverged.
  The reconnect path re-fetches the FULL history (no `from=` query) for
  the panel's scene and overwrites local `messages` outright; that's the
  only approach that converges correctly across all transitions.
- frontend-be-consistency-bootstrap-first: Within a panel, SSE opens
  AFTER its bootstrap completes. Opening SSE first and bootstrapping in
  parallel would create a race where an `entity_changed` event arrives
  before `lastFetchedIndex` is set, with no defined ordering.
- frontend-be-consistency-messages-overwritten: A panel's `messages`
  state is preserved across the clear-and-bootstrap cycle for UX
  continuity (no empty-flicker during transient reconnects), but the
  history re-fetch REPLACES `messages` with the freshly-fetched history.
  The state can only be stale during the in-flight reconnect window,
  never after a successful bootstrap.
- .tested-by: test_frontend_be_consistency_on_reconnect
- .implemented-by: useEntity

## frontend-sse-client-dataflow: Per-panel SSE dataflow

Per **entity panel** instance. The workspace's own bootstrap (campaign
list + campaign read) is separate; see `frontend-workspace-bootstrap`.

1. sse-client-entity: Fetch `GET /api/campaigns/{cid}/entities/{eid}` →
   the typed `EntityResponse` (see `frontend-be-dep-entity-typed`).
   Dispatch the panel renderer on `response.type`.
   - .implements: cuj-startup-ready
2. sse-client-dependents: For Scene panels, fetch each
   `character_id` in parallel via `GET /api/campaigns/{cid}/entities/{eid}`
   → populate the panel's local `entityCache` (resolves message senders).
   - .implements: cuj-startup-ready
3. sse-client-history: For Scene panels, fetch
   `GET /api/campaigns/{cid}/scenes/{eid}/messages` → resolve senders from
   the panel's `entityCache` → replace `messages`. Track
   `lastFetchedIndex` from the last entry.
   - .implements: cuj-startup-ready
4. sse-client-connect: Open
   `EventSource('/api/campaigns/{cid}/entities/{eid}/events')` —
   per-entity stream per `events-subscription`. Opens AFTER bootstrap so
   the URL is well-defined.
   - .implements: cuj-hello-respond
5. sse-client-event: Receive `entity_changed` SSE event with payload
   `{entity_id, attributes}` → if `entity_id` equals the panel's entity
   AND `attributes` contains `"messages"`, fetch the new slice via
   `GET /scenes/{eid}/messages?from={lastFetchedIndex+1}` → resolve
   senders → append to `messages` → update `lastFetchedIndex`.
   - .implements: cuj-hello-respond
   - sse-client-event-serialized: Concurrent `entity_changed` events
     MUST NOT trigger overlapping slice fetches. Two fetches reading
     `lastFetchedIndex` before either's append completes would both
     compute the same `from` and double-append. Slice fetches are
     serialized via a per-panel promise chain so each fetch
     observes the prior fetch's `setMessages` effect.
     - .tested-by: test_sse_client_event_serialized
6. sse-client-disconnect: On SSE close, the panel sets `connected = false`;
   reconnects with exponential backoff (initial 1 s, max 30 s).
7. sse-client-reconnect: On reconnect, the panel clears its local
   `entityCache`, dependents, and `lastFetchedIndex`; retains `messages`.
   Re-enters at `sse-client-entity`.

## frontend-handles-api-503: SPA tolerates LOADING state

While `App.state == LOADING` every API endpoint returns 503 (per
`rest-api-*-503`). The SPA shell itself is just static assets — it loads
regardless of backend state. The SPA treats 503 from any endpoint as a
transient "backend loading" signal, not an error.

- frontend-handles-api-503-no-crash: A 503 response from any endpoint
  (`/api/campaigns`, `/api/campaigns/{cid}`, `/entities/{eid}`,
  `/scenes/{eid}/messages`, …) does NOT propagate as an uncaught error.
  The workspace's bootstrap and each `useEntity` instance catch the
  failure and route it through their respective reconnect paths.
- frontend-handles-api-503-retry: Workspace bootstrap retries on the
  same exponential backoff as SSE reconnect (1 s → 30 s) until the
  backend flips to SERVING. Per-panel `useEntity` does the same for its
  panel-scoped bootstrap.
- frontend-handles-api-503-indicator: While retrying, the affected
  panel's `connected` stays `false` so its header surface reflects the
  not-ready state. No modal/error UI appears.
- .implemented-by: useEntity, Workspace
- .tested-by: test_frontend_handles_api_503

## frontend-api-client-dataflow: Client REST dataflow (send)

1. api-client-send: User submits input → POST
   `MessageRequest { sender_id, body }` to
   `/api/campaigns/{campaignId}/scenes/{sceneId}/messages`. The Scene
   panel does NOT optimistically append the result; the server's
   resulting `entity_changed` triggers a slice fetch that appends.
   - .implements: cuj-hello-send

## frontend-state: Client state

State is split between the workspace shell and per-panel hooks. Nothing
is global; in particular, `connected`, `messages`, `entityCache`, and
`playerCharacterIds` are NO LONGER workspace-level — each entity panel
owns its own.

- frontend-state-campaign-id: Workspace state. `campaignId: string | null`
  — set from the first entry of `GET /api/campaigns` (today there is
  exactly one); used as `{cid}` path param on every campaign-scoped
  route. Cleared on workspace re-bootstrap.
- frontend-state-default-scene-id: Workspace state.
  `defaultSceneId: EntityId | null` — populated from
  `CampaignResponse.default_scene_id`; used only to initialise
  `mainEntityId` when no URL fragment is present.
- frontend-state-main-entity-id: Workspace state.
  `mainEntityId: EntityId | null` — the entity bound to the right slot.
  Initialised per `frontend-workspace-initial-main`; mutated by
  `frontend-workspace-open-entity`.
- frontend-state-panel-entity: Per-panel state owned by `useEntity`.
  `entity: EntityResponse | null` — the fetched typed entity. Dispatch
  source for the panel renderer.
- frontend-state-panel-dependents: Per-panel state.
  `entityCache: Map<EntityId, CharacterModel>` for Scene panels —
  populated from `sse-client-dependents`. Used to resolve message
  senders. Cleared on reconnect.
- frontend-state-panel-player-ids: Per-panel state.
  `playerCharacterIds: EntityId[]` — populated from
  `SceneResponse.player_character_ids`. Used by the panel's
  `MessageInput` to address messages.
- frontend-state-panel-messages: Per-panel state.
  `messages: ChatMessage[]` where
  `ChatMessage = { scene_id: EntityId; index: number; sender: CharacterModel; body: string }` —
  append-only; retained across reconnects. `(scene_id, index)` is the
  composite wire identity and the pagination cursor.
- frontend-state-panel-connected: Per-panel state.
  `connected: boolean` — reflects the panel's own SSE state; disables
  its input when false.

## frontend-components: Component specs

### frontend-app: App

Root component. Renders `Workspace`.

- frontend-app-renders: Renders `<Workspace />` and nothing else.

### frontend-workspace-component: Workspace

Owns campaign bootstrap and the two-slot layout described in
`frontend-workspace`.

- frontend-workspace-component-bootstrap: On mount, runs
  `frontend-workspace-bootstrap`. Stores `campaignId`,
  `defaultSceneId`, and the initial `mainEntityId`.
- frontend-workspace-component-layout: Renders `<EntitySelector
  campaignId={campaignId} onOpenEntity={handler} />` in the left slot
  and `<EntityPanel campaignId={campaignId} entityId={mainEntityId} />`
  in the right slot (or a placeholder if `mainEntityId` is null).
- frontend-workspace-component-testid: The shell carries
  `data-testid="workspace"`; the right slot carries
  `data-testid="main-slot"`.

### frontend-entityselector: EntitySelector

`campaignId: string | null` `onOpenEntity: (id: EntityId) => void`

A workspace panel listing Scene entities (default filter today; the
filter is hardcoded — generalised filtering is future work).

- frontend-entityselector-fetch: On mount (and when `campaignId`
  changes), fetches
  `GET /api/campaigns/{campaignId}/scenes` → renders one `SceneBubble`
  per entry. Snapshot-only: no live subscription.
- frontend-entityselector-double-click: Double-clicking a bubble calls
  `onOpenEntity(bubble.id)`.
- frontend-entityselector-testid: The list container carries
  `data-testid="entity-selector"`.

### frontend-scenebubble: SceneBubble

`scene: SceneResponse` `onOpen: () => void`

- frontend-scenebubble-renders: Renders `scene.name` (today; later may
  include compact metadata like character count).
- frontend-scenebubble-double-click: Double-click fires `onOpen()`. The
  bubble is the gesture surface; it does not know about the workspace.
- frontend-scenebubble-data: Carries `data-testid="scene-bubble"` and
  `data-entity-id={scene.id}`.

### frontend-entitypanel: EntityPanel

`campaignId: string | null` `entityId: EntityId | null`

Dispatcher. Fetches the entity via `useEntity` and renders the matching
entity-typed panel.

- frontend-entitypanel-uses-useentity: Calls `useEntity({ campaignId,
  entityId })` to bootstrap and subscribe.
- frontend-entitypanel-dispatch: When the fetched `entity.type === 'scene'`,
  renders `<SceneEntityPanel … />`. Other types render
  `<UnknownEntityPanel type={entity.type} />`.
- frontend-entitypanel-fallback: `UnknownEntityPanel` shows a
  "no panel registered for type <type>" placeholder. Bubbles for the
  unregistered type are allowed; the placeholder explicitly names which
  type lacks a renderer.

### frontend-sceneentitypanel: SceneEntityPanel

`campaignId: string` `entity: SceneResponse` `entityCache: Map<EntityId,
CharacterModel>` `playerCharacterIds: EntityId[]` `messages: ChatMessage[]`
`connected: boolean`

Renders the Scene panel: scene header on top, chat (messages + input)
beneath. `SceneEntityPanel` is the only place ChatMessage / MessageList /
MessageInput compose; the previous standalone `ChatView` is absorbed.

- frontend-sceneentitypanel-header: Renders an in-panel header with
  `entity.name` and a connection indicator (green/red dot reflecting
  `connected`). `entity.body` (the scene description) renders beneath
  the header when non-empty.
- frontend-sceneentitypanel-list: Renders `<MessageList messages={messages}
  playerCharacterIds={playerCharacterIds} />`.
- frontend-sceneentitypanel-input: Renders `<MessageInput connected=…
  onSend=… />`. `onSend` is bound via `useSendMessage(campaignId, entity.id,
  playerCharacterIds[0] ?? null)`.
- frontend-sceneentitypanel-testid: The shell carries
  `data-testid="scene-panel"` and `data-entity-id={entity.id}` for stable
  selectors.

### frontend-messagelist: MessageList

`messages` `playerCharacterIds`

(Internal to Scene panels.)

- frontend-messagelist-scroll: Scrolls to the bottom whenever `messages` grows.
- frontend-messagelist-items: Renders one `MessageItem` per message; keyed
  by `(message.scene_id, message.index)` so React reconciliation stays
  stable when slices arrive out of order.
  - .tested-by: cuj-hello-browser
- frontend-messagelist-testid: The `<ul>` carries `data-testid="message-list"`.
  - .tested-by: cuj-hello-browser

### frontend-messageitem: MessageItem

`message: ChatMessage` `isOwn: boolean`

(Internal to Scene panels.)

- frontend-messageitem-own: `isOwn` is true when `message.sender.id ∈ playerCharacterIds`; right-aligned with distinct Tailwind classes.
- frontend-messageitem-other: Non-own messages are left-aligned.
- frontend-messageitem-sender: Displays `message.sender.name` above the message body.
- frontend-messageitem-data: Carries `data-testid="message-item"`,
  `data-scene-id={message.scene_id}`, `data-index={message.index}`, and
  `data-sender-id={message.sender.id}` for stable selectors.
  - .tested-by: cuj-hello-browser

### frontend-messageinput: MessageInput

`connected: boolean` `onSend: (body: string) => void`

(Internal to Scene panels.)

- frontend-input-disabled: Input and button are disabled when `connected` is false.
- frontend-input-submit-button: Clicking the send button calls `onSend(body)` and clears the input.
  - .tested-by: cuj-hello-browser
- frontend-input-submit-enter: Pressing Enter (without Shift) also calls `onSend(body)`.
- frontend-input-testid: Textarea carries `data-testid="message-input"`;
  Send button carries `data-testid="send-button"`.
  - .tested-by: cuj-hello-browser

### frontend-useentity: useEntity({ campaignId, entityId, deps })

Per-panel bootstrap-and-subscribe hook. Replaces the previous monolithic
`useSSE`. Each entity panel instance calls `useEntity` exactly once.

- frontend-useentity-bootstraps: On mount (and when `entityId` changes),
  runs `sse-client-entity`, `sse-client-dependents`, and
  `sse-client-history` in order.
- frontend-useentity-subscribes: After bootstrap, opens
  `EventSource('/api/campaigns/{campaignId}/entities/{entityId}/events')`.
- frontend-useentity-dispatches: Handles `entity_changed` events per
  `sse-client-event`. Slice fetches are serialized per
  `sse-client-event-serialized`.
- frontend-useentity-reconnects: On SSE close, schedules reconnect per
  `sse-client-reconnect` and re-bootstraps from `sse-client-entity`.
- frontend-useentity-returns: Returns `{ entity, entityCache,
  playerCharacterIds, messages, connected }`.
- frontend-useentity-deps: Accepts `{ fetcher?, eventSourceFactory? }` as
  an injection seam for unit tests (mirrors `frontend-usesse-deps` in
  the previous architecture).

### frontend-usesendmessage: useSendMessage(campaignId, sceneId, senderId)

- frontend-send-hook-posts: POSTs `MessageRequest` to `/api/campaigns/{campaignId}/scenes/{sceneId}/messages`.
- frontend-send-hook-returns: Returns a `send(body: string) => Promise<MessageAccepted | null>` callback. The `MessageAccepted` carries `{scene_id, index}` — the composite identity assigned by the server; null on error.

Note: There is no client-side optimistic append. The SSE `entity_changed` for the user's own POST already triggers a slice fetch, so an optimistic append would cause double rendering.
