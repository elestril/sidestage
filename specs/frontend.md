# frontend: React data layer (Campaign, proxies, hooks)

React + TypeScript + Tailwind SPA built with Vite. This file specs the
**data layer**: a single `Campaign` singleton per browser tab mirrors
the backend Campaign, owning the lone multiplexed WebSocket and the
shared cache of hydrated entities. Components ask the FE Campaign for
an entity and receive a promise; FE entity proxies expose
`@action`-decorated methods that serialise as `EntityAction` frames.

- frontend-no-rest: The FE issues **no HTTP requests to `/api/*`** —
  only the static SPA bundle at `/`. Every Campaign operation
  (resolve, subscribe, mutate) flows through the single WebSocket.
  The REST endpoints documented in [[backend]] `backend-rest-debug`
  exist for human/ops inspection only; a `grep` guard on
  `frontend/src/` enforces zero `/api/` fetches.

The **UI layer** — workspace shell and entity-typed widgets — is
specced separately in [[frontend-layout]].

## frontend-project: Project layout

```
frontend/
├── package.json
├── vite.config.ts              # /api proxy → :8000 (REST + WS)
├── index.html
└── src/
    ├── main.tsx
    ├── types.ts                # generated from Entity.Model subclasses; gitignored
    ├── types_ext.ts            # branded EntityId; discriminated unions
    ├── campaign.ts             # Campaign singleton + WS client
    ├── entities/
    │   ├── Entity.ts           # base proxy class
    │   ├── Character.ts        # Character proxy with @action say
    │   └── Scene.ts            # Scene proxy
    ├── hooks/
    │   └── useEntity.ts        # registry-backed reactive hook
    ├── widgets/
    │   ├── registry.tsx        # per-type widget table
    │   ├── ScenePanel.tsx
    │   └── SceneBubble.tsx
    └── components/
        ├── App.tsx
        ├── Workspace.tsx       # campaign bootstrap + Campaign provider
        ├── EntitySelector.tsx
        ├── EntityPanel.tsx
        ├── MessageList.tsx
        ├── MessageItem.tsx
        └── MessageInput.tsx
```

- frontend-vite-proxy: `vite.config.ts` proxies `/api` to
  `http://localhost:8000` with `changeOrigin: true` AND `ws: true` so
  the WS at `/api/campaigns/{cid}/ws` passes through the same proxy as
  the REST routes.
- frontend-build-output: `build.outDir` is `../src/sidestage/static/`.
  FastAPI serves the bundle in production single-process deploys.
- frontend-types-generated: `frontend/src/types.ts` is auto-generated
  by `just _gen-types` from the `Entity.Model` (and `Campaign.Model`)
  Pydantic classes on every consumer invocation. Branded `EntityId`
  and the wire-event shape (`EntityChangedEvent`) live in
  `types_ext.ts`. All app code imports from `types_ext.ts`, never
  from `types.ts` directly. **No `*Response` types** — the FE
  consumes `Entity.Model` subclasses directly (per [[entity-model]]
  `entity-model-canonical`).

## frontend-campaign: Campaign

```ts
class Campaign {
  readonly campaignId: string;

  constructor(campaignId: string, deps?: {
    wsFactory?: (url: string) => WebSocket;
  });

  // Architectural surface (mirrors BE Campaign). All mutating ops
  // are strict relays — they emit a wire frame to BE and await ack.
  // Local proxy state changes ONLY in response to EntityChanged
  // (per frontend-entities).
  get(entity_id: EntityId): Promise<Entity>;
  add(entity: Entity): Promise<void>;          // FE-issued creates relay to BE
  delete(entity_id: EntityId): Promise<void>;
  subscribe(entity_ids: EntityId[]): void;

  // React-binding helpers (used by useEntity).
  peek(entity_id: EntityId): Entity | null;
  observe(entity_id: EntityId, listener: () => void): () => void;

  // Global connection state.
  isConnected(): boolean;
  subscribeConnected(listener: () => void): () => void;

  close(): void;
}
```

One instance per browser tab, constructed by `Workspace` once
`campaignId` is known and provided via React context. Owns the lone
WebSocket, a `Map<EntityId, Entity>` cache of FE proxy instances,
per-id refcounts, per-id listener sets, per-id slice-fetch chains,
eviction timers, and a `Map<request_id, Promise>` of in-flight
EntityAction acks.

- frontend-campaign-get: Returns a promise that resolves to the FE
  proxy for the entity. First call for an id sends a WS `subscribe`
  frame with that id; the promise resolves when the matching
  `subscribed` reply arrives carrying the entity's initial state.
  Later calls reuse the in-flight hydration promise. The proxy is
  the discriminated union narrowed on `Entity.Model.type` (Scene
  proxy for `'scene'`, Character proxy for `'character'`).
- frontend-campaign-observe: Register a listener as an observer of an
  entity. Returns a single function that both unregisters the
  listener AND decrements the refcount. Matching
  `useSyncExternalStore`'s one-subscribe-↔-one-unsubscribe contract
  keeps the refcount in lockstep with the live observer set under
  React StrictMode's mount→cleanup→mount cycle. On 0→1 transition
  the registry sends a WS `subscribe` frame; on 1→0 it sends
  `unsubscribe` and schedules cache eviction after a short grace
  period.
- frontend-campaign-peek: Synchronous read of the cached proxy (no
  observer side effects). `useSyncExternalStore` calls this every
  render.
- frontend-campaign-subscribed-initial-state: The WS `subscribed`
  reply carries each requested entity's `Entity.Model` payload. The
  Campaign hydrates its proxy cache from this payload — no follow-up
  fetch. For a `Scene.Model` this includes `messages` (the initial
  history). Subsequent `entity_changed` frames carry deltas that the
  Campaign applies in place.
- frontend-campaign-collection-delta: On `entity_changed` carrying
  a `ListDelta`, the Campaign applies the delta directly to the
  cached proxy's attribute via the JS splice contract:
  `start === -1 ? list.push(...items) : list.splice(start, len,
  ...items)`. On a `ScalarDelta`, the Campaign assigns
  `proxy[attr] = value`. Same shape regardless of attribute or
  entity type (per [[events]] `events-attribute-deltas`).
  Attribute updates are serialised per-entity via a promise chain
  so concurrent events never reorder.
- frontend-campaign-reconnect: On WS close, sets `connected = false`,
  schedules exponential-backoff reconnect (1 s → 30 s). On open, the
  registry re-issues subscribe frames for every observed id; the
  fresh `subscribed` replies carry the authoritative current state,
  overwriting any stale proxy data. Any event lost during the
  disconnect window is reflected in the post-reconnect snapshot.
- frontend-campaign-action-dispatch: When a proxy's `@action` method
  is called, the Campaign assigns a `request_id`, sends an
  `entity_action` frame, and returns a Promise that resolves on the
  matching `ack` (or rejects on `error`). The Promise resolution is
  the only completion signal — projection state only updates when
  the BE-emitted `EntityChanged` arrives.
- .implemented-by: Campaign

## frontend-entities: FE entity proxies (read-only views + RPC actions)

**Strict relay, no local mutation.** Every FE entity proxy is a
read-only view of the BE-authoritative Entity. Action methods on a
proxy do NOT mutate local state — they serialise an `EntityAction`
frame, await the BE ack, and let the resulting `EntityChanged`
propagate the new state through the normal subscribe path. The proxy's
backing data only changes when the Campaign re-reads it in response
to `EntityChanged`. Holding the line keeps the FE from becoming a
competing source of truth alongside Campaign (per [[architecture]]
`architecture-rejected`).

Each Entity subclass has a matching FE proxy class with the same
`@action` method names as the BE subclass.

```ts
class Entity {                       // base proxy
  readonly id: EntityId;
  readonly type: EntityType;
  readonly name: string;
  readonly body: string;
}

class Character extends Entity {
  readonly owner: 'user' | 'stub' | 'npc';
  say(scene_id: EntityId, body: string): Promise<void>;   // RPC
}

class Scene extends Entity {
  readonly character_ids: EntityId[];
  readonly messages: Message[];         // initial state arrives in `subscribed`;
                                        // ListDelta frames apply in place
}
```

- frontend-entity-proxy-mirrors-be: Every BE Entity subclass has a
  matching FE proxy class with the same `@action` method names.
  Calling e.g. `character.say(scene_id, body)` is encoded as
  `EntityAction(entity_id=character.id, action="say",
  kwargs={scene_id, body})`. The Promise resolves on the matching
  `ack`; its resolution carries no payload (the action's effect is
  observed via `EntityChanged`).
- frontend-entity-proxy-readonly: All proxy fields are read-only.
  Action methods take no shortcut — they always round-trip. The
  Campaign updates the proxy's backing Model in place ONLY when an
  `entity_changed` frame triggers a re-read.
- frontend-entity-proxy-local-echo-future: A future "local echo"
  optimisation could optimistically apply an action's expected
  effect to the local proxy before the ack lands and reconcile on
  `EntityChanged` (or roll back on `error`). This would soften the
  invariant from "projection state mirrors authoritative state
  modulo disconnect windows" to "...modulo disconnect windows AND
  in-flight action windows," but it does NOT change the public
  surface — `character.say(scene_id, body)` and `useEntity(id)` keep their
  current signatures. Opt-in per action if/when latency tolerance
  becomes a UX concern.

## frontend-hooks: React hook surface

```ts
function useCampaign(): Campaign;             // from context
function useEntity(id: EntityId | null): {
  entity: Entity | null;
  status: 'loading' | 'ready' | 'error';
};
function useConnected(): boolean;
```

- frontend-useentity: Calls `useSyncExternalStore` with
  `subscribe = (l) => campaign.observe(id, l)` and
  `getSnapshot = () => campaign.peek(id)`. React owns the
  observation lifecycle: mount → subscribe (one observer registered),
  unmount → unsubscribe.
- frontend-useconnected: Subscribes to the Campaign's global
  connection state. Widgets use this for connection indicators and
  to disable input while offline.
- .implemented-by: hooks/useEntity.ts

There is **no `useSendMessage`** — write paths go through the FE
proxy's `@action` methods.
