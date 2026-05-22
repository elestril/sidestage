# frontend-layout: Workspace shell + entity widgets

The HTML/UI layer of the SPA. Sits on top of the data layer specced in
[[frontend]] (Campaign, FE entity proxies, hooks). This file owns how
entities are rendered and arranged on screen; it doesn't describe
transport, hydration, or state — those live in [[frontend]].

The SPA is organised as a **workspace** that hosts entity-typed
**widgets** dispatched on `entity.type` via a small widget registry.

## frontend-widgets: Widget registry + components

```ts
type WidgetEntry<E> = {
  Panel:   ComponentType<{ entity: E }>;
  Bubble?: ComponentType<{ entity: E; onOpen?: () => void }>;
};
const widgets: Partial<{
  scene:     WidgetEntry<Scene>;
  character: WidgetEntry<Character>;
}>;
```

Adding a new entity type is one registry entry plus the matching
components.

- frontend-widget-dispatch: `EntityPanel` reads the entity via
  `useEntity(id)` (per [[frontend]] `frontend-useentity`) and looks
  up `widgets[entity.type]`. Renders
  `<entry.Panel entity={entity} />`. Falls through to
  `<UnknownEntityPanel type={type} />` when no entry exists.
- frontend-widget-pure: Widgets are pure — they receive the proxy as
  a prop and read sub-entities via `useEntity(...)`. No transport,
  no fetch, no sync logic in widget code. Mutations go through the
  proxy's `@action` methods (which relay to BE per [[frontend]]
  `frontend-entities`).
- frontend-widget-scene: `ScenePanel` renders the scene header
  (`scene.name` + `useConnected()` indicator), the `MessageList`,
  and `MessageInput`. The input calls
  `await campaign.get(playerCharacterId).then(c => c.say(sceneId, body))`.
  Sender resolution per-message lives in a child component
  (`MessageRow`) that calls `useEntity(message.sender_id)`.
- frontend-widget-scenebubble: `SceneBubble` is a compact snapshot
  renderer used by `EntitySelector`. Snapshot-only — bubbles don't
  observe today. Live-subscribed bubbles work for free with the
  Campaign but are a UX call, deferred.
- .implemented-by: widgets/registry.tsx, widgets/ScenePanel.tsx,
  widgets/SceneBubble.tsx, components/EntityPanel.tsx,
  components/MessageList.tsx, components/MessageItem.tsx,
  components/MessageInput.tsx

## frontend-workspace: Workspace shell

```ts
// Workspace state (top-level shell only)
{ campaignId: string | null,
  defaultSceneId: EntityId | null,
  mainEntityId: EntityId | null }
```

Static two-slot layout: left selector, right entity panel.
Campaign-scoped — one campaign active at a time; no switcher UI today.

- frontend-workspace-bootstrap: On mount, opens the lone WS and (in
  the single-campaign world) connects to the only loaded campaign;
  no campaign-discovery REST call is needed. Constructs a single
  `Campaign(campaignId)` via `useMemo([campaignId])` and wraps the
  slots in `<CampaignProvider value={campaign}>`. The Campaign's
  initial subscribe targets the campaign-meta entity (or equivalent
  bootstrap entity) to learn `default_scene_id`. `mainEntityId` is
  set from the URL fragment if present, else `defaultSceneId`.
- frontend-workspace-open-entity: The selector emits
  `onOpenEntity(id)` on double-click; the workspace sets
  `mainEntityId = id`. Idempotent.
- frontend-workspace-remount-on-change: `EntityPanel` uses
  `key={mainEntityId}` so it unmounts and remounts on entity switch.
  Per-panel ephemeral UI state (half-typed input, scroll position)
  does not bleed across switches; live entity data lives in the
  Campaign cache.
- frontend-handles-loading: A WS handshake closed with code 1013
  (server `LOADING`) routes through the Campaign's exponential-backoff
  reconnect path. `connected` stays `false` during retry — no modal
  error UI.
- .implements: cuj-startup-ready, cuj-hello-send, cuj-hello-respond
- .implemented-by: Workspace, EntityPanel, EntitySelector,
  CampaignProvider
