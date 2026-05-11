# frontend: React chat UI

The Sidestage frontend is a React + TypeScript + Tailwind single-page
application built with Vite. In development, Vite's dev server proxies `/api`
to FastAPI. In production, FastAPI serves the built static bundle.

## frontend-project: Project layout

```
frontend/
|- package.json
|- vite.config.ts      proxy /api → localhost:8000 in dev
|- tailwind.config.ts
|- index.html
|- src/
   |- main.tsx
   |- types.ts          wire format types + EntityId brand
   |- hooks/
   |  |- useSSE.ts
   |  |- useSendMessage.ts
   |- components/
      |- App.tsx
      |- ChatView.tsx
      |- MessageList.tsx
      |- MessageItem.tsx
      |- MessageInput.tsx
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

`frontend/src/types.ts` is **auto-generated** — never hand-edited. It is
regenerated whenever the server-side wire format changes.

- frontend-types-generated: `frontend/src/types.ts` is produced by running
  `uv run pydantic2ts --module sidestage.server --output frontend/src/types.ts`
  from the repo root. The file is committed to the repository.
- frontend-types-source: The authoritative source is the Pydantic `BaseModel`
  subclasses across `sidestage.scene` (`SceneResponse`), `sidestage.campaign`
  (`CampaignResponse`), `sidestage.message` (`Message.Model`),
  `sidestage.character` (`Character.Model`), and `sidestage.server`
  (`MessageRequest`, `MessageAccepted`). `EntityChangedEvent` (the SSE
  wire shape — see `events-subscription`) is hand-rolled in `types.ts`
  because the in-process `EntityChanged` is a `@dataclass`, not a
  Pydantic model.
- frontend-types-entityid: `EntityId` is generated as `string` (Pydantic's
  `NewType` has no TypeScript equivalent). A branded alias
  `type EntityId = string & { readonly _brand: 'EntityId' }` is added
  manually in a thin `frontend/src/types_ext.ts` that re-exports everything
  from `types.ts` and overrides the `EntityId` definition. All application
  code imports from `types_ext.ts`, never directly from `types.ts`.
- frontend-types-discriminated: `ServerEvent = EntityChangedEvent` is
  defined in `types_ext.ts`. Today there is exactly one event variant;
  the type is a discriminated union scaffold for future variants.

## frontend-sse-client-dataflow: Client SSE dataflow

The SSE connection is a process boundary (server→client only). Bootstrap
runs first, then SSE opens on the resolved scene's per-entity URL.

1. sse-client-list-campaigns: On `App` mount, fetch `GET /api/campaigns` →
   pick the only entry today (in the future, by name from URL or user
   choice). Store its id (`name`) as `campaignId`.
   - .implements: cuj-startup-ready
2. sse-client-campaign: Fetch `GET /api/campaigns/{campaignId}` → read
   `default_scene_id`. Pick which scene to display: the URL fragment if the
   user navigated to a specific scene, otherwise `default_scene_id`.
   - .implements: cuj-startup-ready
3. sse-client-scene: Fetch `GET /api/campaigns/{campaignId}/scenes/{sceneId}`
   for the chosen scene → store `sceneId`, `playerCharacterIds`, and
   `character_ids`.
   - .implements: cuj-startup-ready
4. sse-client-entities: Fetch `GET /api/campaigns/{campaignId}/entities/{id}`
   for each `character_id` in parallel → populate `entityCache`.
   - .implements: cuj-startup-ready
5. sse-client-history: Fetch `GET /api/campaigns/{campaignId}/scenes/{sceneId}/messages`
   → resolve senders from `entityCache` → replace `messages`. Track
   `lastFetchedIndex` from the last entry.
   - .implements: cuj-startup-ready
6. sse-client-connect: Open
   `EventSource('/api/campaigns/{campaignId}/entities/{sceneId}/events')` —
   per-entity stream per `events-subscription`. Opens AFTER bootstrap so
   the URL is well-defined.
   - .implements: cuj-hello-respond
7. sse-client-event: Receive `entity_changed` SSE event with payload
   `{entity_id, attributes}` → if `entity_id` is the displayed `sceneId`
   AND `attributes` contains `"messages"`, fetch the new slice via
   `GET /messages?from={lastFetchedIndex+1}` → resolve senders →
   append to `messages` → update `lastFetchedIndex`.
   - .implements: cuj-hello-respond
8. sse-client-disconnect: On SSE close, set `connected = false`; reconnect
   with exponential backoff (initial 1 s, max 30 s).
9. sse-client-reconnect: On reconnect, clear `entityCache`, `campaignId`,
   `sceneId`, `playerCharacterIds`, and `lastFetchedIndex`; retain
   `messages`. Re-enter at sse-client-list-campaigns.

## frontend-api-client-dataflow: Client REST dataflow

1. api-client-send: User submits input → POST `MessageRequest { sender_id: playerCharacterIds[0], body }` to `/api/campaigns/{campaignId}/scenes/{sceneId}/messages` → append the returned `MessageResponse` optimistically to `messages`.
   - .implements: cuj-hello-send

## frontend-state: Client state

Managed in `useSSE` hook; passed down as props.

- frontend-state-cache: `entityCache: Map<EntityId, CharacterModel>` — populated from `GET /api/campaigns/{cid}/entities/{id}`; cleared on SSE reconnect.
- frontend-state-player-ids: `playerCharacterIds: EntityId[]` — populated from `SceneResponse.player_character_ids`; cleared on SSE reconnect.
- frontend-state-campaign-id: `campaignId: string | null` — set from the first entry of `GET /api/campaigns` (today there is exactly one); used as `{cid}` path param on every campaign-scoped route. Cleared on SSE reconnect.
- frontend-state-scene-id: `sceneId: EntityId | null` — set from URL fragment or `CampaignResponse.default_scene_id`; used as path param for scene-keyed routes.
- frontend-state-default-scene-id: `defaultSceneId: EntityId | null` — populated from `CampaignResponse.default_scene_id`; used only as a navigation hint when the user has no other intent.
- frontend-state-messages: `messages: { sender: CharacterModel; body: string }[]` — append-only; retained across reconnects.
- frontend-state-connected: `connected: boolean` — reflects live SSE state; disables input when false.

## frontend-components: Component specs

### frontend-app: App

Root component. Owns the `useSSE` hook and renders `ChatView` once connected.

- frontend-app-mount: Calls `useSSE()` on mount to subscribe to push notifications and bootstrap the campaign + scene state.
- frontend-app-renders: Renders `ChatView` passing `messages`, `entityCache`, `playerCharacterIds`, `connected`, and `onSend` callback.

### frontend-chatview: ChatView

`messages` `entityCache` `playerCharacterIds` `connected` `onSend`

- frontend-chatview-list: Renders `MessageList` with `messages` and `playerCharacterIds`.
- frontend-chatview-input: Renders `MessageInput` with `connected` and `onSend`.

### frontend-messagelist: MessageList

`messages` `playerCharacterIds`

- frontend-messagelist-scroll: Scrolls to the bottom whenever `messages` grows.
- frontend-messagelist-items: Renders one `MessageItem` per message.

### frontend-messageitem: MessageItem

`message: { sender: CharacterModel; body: string }` `isOwn: boolean`

- frontend-messageitem-own: `isOwn` is true when `message.sender.id ∈ playerCharacterIds`; right-aligned with distinct Tailwind classes.
- frontend-messageitem-other: Non-own messages are left-aligned.
- frontend-messageitem-sender: Displays `message.sender.name` above the message body.

### frontend-messageinput: MessageInput

`connected: boolean` `onSend: (body: string) => void`

- frontend-input-disabled: Input and button are disabled when `connected` is false.
- frontend-input-submit-button: Clicking the send button calls `onSend(body)` and clears the input.
- frontend-input-submit-enter: Pressing Enter (without Shift) also calls `onSend(body)`.

### frontend-usesse: useSSE()

(zero-arg; URLs are derived inside the bootstrap chain)

- frontend-hook-opens: Opens `EventSource(eventsUrl)` on mount; closes on unmount.
- frontend-hook-scene: Immediately after opening SSE, fetches `sceneUrl` and populates `entityCache`, `playerCharacterIds`, and `sceneId`.
- frontend-hook-dispatches: Handles `entity_changed` SSE events per `sse-client-event`.
- frontend-hook-reconnects: On SSE close, schedules reconnect per `sse-client-reconnect`.
- frontend-hook-returns: Returns `{ messages, entityCache, playerCharacterIds, campaignId, sceneId, defaultSceneId, connected }`.

### frontend-usesendmessage: useSendMessage(campaignId, sceneId)

- frontend-send-hook-posts: POSTs `MessageRequest` to `/api/campaigns/{campaignId}/scenes/{sceneId}/messages`.
- frontend-send-hook-returns: Returns a `send(body: string) => Promise<MessageAccepted | null>` callback. The `MessageAccepted` carries `{scene_id, index}` — the composite identity assigned by the server; null on error.

Note: There is no client-side optimistic append. The SSE `entity_changed` for the user's own POST already triggers a slice fetch, so an optimistic append would cause double rendering.
