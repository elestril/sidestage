// frontend-entity-registry: EntityRegistry singleton.
//
// One instance per browser tab, constructed by `Workspace` once the
// campaign id is known. Owns the lone multiplexed WebSocket at
// `/api/campaigns/{cid}/ws` and a shared cache of hydrated entities.
//
// Per `specs/frontend.md#frontend-entity-registry` and
// `specs/events.md#events-subscription`. Phase 2b: the WS `subscribed`
// reply carries each entity's full `Entity.Model` payload (the initial
// state), and subsequent `entity_changed` frames carry typed deltas
// the registry applies in place — no REST fallback for hydration.

import {
  asEntityId,
  type AttributeDelta,
  type CharacterResponse,
  type EntityActionFrame,
  type EntityId,
  type ListDelta,
  type MessageModel,
  type SceneResponse,
  type ScalarDelta,
  type ServerEvent,
} from './types_ext';

// frontend-state-registry-cache: cached entity for a scene carries a
// synced `messages` array alongside its wire fields. Character entities
// have nothing extra.
export type CachedScene = SceneResponse & { messages: MessageModel[] };
export type CachedEntity = CachedScene | CharacterResponse;

export interface EntityRegistryDeps {
  // Phase 2b: hydration is fully WS-driven, so the registry no longer
  // issues REST fetches. The `fetcher` slot is kept on the deps
  // interface to preserve the Workspace's injection seam (and let
  // tests that still construct a registry with a fetcher mock keep
  // working) — the registry simply ignores it.
  fetcher?: typeof fetch;
  wsFactory?: (url: string) => WebSocket;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const EVICTION_GRACE_MS = 5_000;

interface PendingRequest {
  resolve: () => void;
  reject: (err: Error) => void;
}

// Disambiguate `ListDelta` vs `ScalarDelta` by the presence of `start`
// (collection deltas always carry it; scalar deltas always carry
// `value`). Per `specs/events.md#events-attribute-deltas`.
function isListDelta(delta: AttributeDelta): delta is ListDelta {
  return (
    typeof (delta as { start?: unknown }).start === 'number' &&
    Array.isArray((delta as { items?: unknown }).items)
  );
}

function isScalarDelta(delta: AttributeDelta): delta is ScalarDelta {
  return 'value' in delta;
}

function brandSceneModel(raw: unknown, scene_id: EntityId): CachedScene {
  const r = raw as {
    type: 'scene';
    id: string;
    name: string;
    body: string;
    characters: string[];
    messages?: Array<{ sender_id: string; body: string }>;
  };
  const characters = r.characters.map(asEntityId);
  const rawMessages = r.messages ?? [];
  const messages: MessageModel[] = rawMessages.map((m, idx) => ({
    // Wire shape is positional ({sender_id, body}); synthesise the
    // composite `(scene_id, index)` the FE uses for stable React keys
    // and own/other classification.
    scene_id,
    index: idx,
    sender_id: asEntityId(m.sender_id),
    body: m.body,
  }));
  return {
    type: 'scene',
    id: asEntityId(r.id),
    name: r.name,
    body: r.body,
    characters,
    // Phase-1 stub: SimpleScene puts the user character first, so the
    // first id is the player. Phase 2b: compute properly by looking up
    // each Character's owner via the registry.
    player_character_ids: characters.length > 0 ? [characters[0]] : [],
    messages,
  };
}

function brandCharacterModel(raw: unknown): CharacterResponse {
  const r = raw as {
    type: 'character';
    id: string;
    name: string;
    body: string;
    owner: 'user' | 'stub' | 'npc';
  };
  return {
    type: 'character',
    id: asEntityId(r.id),
    name: r.name,
    body: r.body,
    owner: r.owner,
  };
}

function brandEntityModel(raw: unknown, entity_id: EntityId): CachedEntity {
  const r = raw as { type: string };
  if (r.type === 'scene') return brandSceneModel(raw, entity_id);
  if (r.type === 'character') return brandCharacterModel(raw);
  throw new Error(`Unknown entity type: ${r.type}`);
}

// Generate an opaque client-side request id. uuid is preferred per
// `events-subscription-entity-action`; `crypto.randomUUID` is a browser
// built-in and works in jsdom. Falls back to a Math.random-based token
// for environments without `crypto.randomUUID`.
function newRequestId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `req-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export class EntityRegistry {
  readonly campaignId: string;

  private readonly wsFactory: (url: string) => WebSocket;

  private cache = new Map<EntityId, CachedEntity>();
  private refCount = new Map<EntityId, number>();
  private listeners = new Map<EntityId, Set<() => void>>();
  private evictTimers = new Map<EntityId, ReturnType<typeof setTimeout>>();

  // Pending subscribe requests: resolved when the matching `subscribed`
  // reply arrives. The promise resolves to the requested entity id so
  // callers can await initial-state availability if needed.
  private pendingSubscribes = new Map<string, EntityId[]>();
  // In-flight `entity_action` calls; resolved on `ack`, rejected on
  // `error`. Keyed by request_id (per frontend-campaign-action-dispatch).
  private pendingActions = new Map<string, PendingRequest>();

  private connectedListeners = new Set<() => void>();
  private _connected = false;

  private ws: WebSocket | null = null;
  private wsBackoff = INITIAL_BACKOFF_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(campaignId: string, deps: EntityRegistryDeps = {}) {
    this.campaignId = campaignId;
    this.wsFactory =
      deps.wsFactory ?? ((url: string): WebSocket => new WebSocket(url));
    this.openWebSocket();
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  // frontend-entity-registry-observe: register a listener as an observer
  // of an entity. The returned function unregisters that listener AND
  // decrements the observer refcount. Matching `useSyncExternalStore`'s
  // contract (one subscribe call ↔ one unsubscribe call) keeps the
  // refcount in lockstep with the live observer set and behaves
  // correctly under React StrictMode's mount→cleanup→mount cycle.
  observe(entityId: EntityId, listener: () => void): () => void {
    const prev = this.refCount.get(entityId) ?? 0;
    this.refCount.set(entityId, prev + 1);
    const evict = this.evictTimers.get(entityId);
    if (evict !== undefined) {
      clearTimeout(evict);
      this.evictTimers.delete(entityId);
    }
    if (prev === 0) {
      this.sendSubscribe([entityId]);
    }
    let set = this.listeners.get(entityId);
    if (!set) {
      set = new Set();
      this.listeners.set(entityId, set);
    }
    set.add(listener);

    return () => {
      set!.delete(listener);
      const n = this.refCount.get(entityId) ?? 0;
      if (n <= 1) {
        this.refCount.delete(entityId);
        this.sendUnsubscribe([entityId]);
        this.scheduleEviction(entityId);
      } else {
        this.refCount.set(entityId, n - 1);
      }
    };
  }

  // Synchronous read of the cached entity (no observer side effects).
  // useSyncExternalStore calls this every render; observation lifetime
  // is managed by `observe()`.
  peek(entityId: EntityId): CachedEntity | null {
    return this.cache.get(entityId) ?? null;
  }

  // frontend-entity-registry-connected: global connection state for
  // widgets that gate UI on socket health.
  isConnected(): boolean {
    return this._connected;
  }

  subscribeConnected(listener: () => void): () => void {
    this.connectedListeners.add(listener);
    return () => {
      this.connectedListeners.delete(listener);
    };
  }

  // frontend-campaign-action-dispatch: send an `entity_action` frame
  // and return a Promise that resolves on the matching `ack` (or
  // rejects on `error`). The Promise resolution is the only completion
  // signal — projection state only updates when the BE-emitted
  // `EntityChanged` arrives.
  entityAction(
    entityId: EntityId,
    action: string,
    kwargs: Record<string, unknown>,
  ): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const ws = this.ws;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error('entity_action: socket not open'));
        return;
      }
      const request_id = newRequestId();
      this.pendingActions.set(request_id, { resolve, reject });
      const frame: EntityActionFrame = {
        op: 'entity_action',
        entity_id: entityId,
        action,
        kwargs,
        request_id,
      };
      try {
        ws.send(JSON.stringify(frame));
      } catch (err) {
        this.pendingActions.delete(request_id);
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });
  }

  // Lifecycle hook for tab teardown; tests use it to release sockets.
  close(): void {
    this.closed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    for (const t of this.evictTimers.values()) clearTimeout(t);
    this.evictTimers.clear();
    // Reject any in-flight action promises so callers don't hang.
    for (const [, p] of this.pendingActions) {
      p.reject(new Error('registry closed'));
    }
    this.pendingActions.clear();
    this.pendingSubscribes.clear();
  }

  // ------------------------------------------------------------------
  // Cache mutation + listener notification
  // ------------------------------------------------------------------

  private setCache(entityId: EntityId, entity: CachedEntity): void {
    this.cache.set(entityId, entity);
    const set = this.listeners.get(entityId);
    if (set) for (const l of set) l();
  }

  private notifyListeners(entityId: EntityId): void {
    const set = this.listeners.get(entityId);
    if (set) for (const l of set) l();
  }

  private scheduleEviction(entityId: EntityId): void {
    // Grace period absorbs panel-switch churn (mount/unmount/mount).
    const t = setTimeout(() => {
      this.evictTimers.delete(entityId);
      if ((this.refCount.get(entityId) ?? 0) > 0) return;
      this.cache.delete(entityId);
      this.listeners.delete(entityId);
    }, EVICTION_GRACE_MS);
    this.evictTimers.set(entityId, t);
  }

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  private openWebSocket(): void {
    if (this.closed) return;
    const url = `/api/campaigns/${encodeURIComponent(this.campaignId)}/ws`;
    // Relative URLs are accepted by the WebSocket constructor in the
    // browser; the test harness can override via `wsFactory`. Resolve
    // against window.location for absolute URLs in the browser path.
    const absoluteUrl = this.resolveWsUrl(url);
    const ws = this.wsFactory(absoluteUrl);
    this.ws = ws;
    ws.addEventListener('open', () => {
      if (this.ws !== ws) return;
      this.wsBackoff = INITIAL_BACKOFF_MS;
      this.setConnected(true);
      // ws-client-reconnect: replay observe set on every (re)connect so
      // the server has the same subscription set as the client. The
      // freshly-arriving `subscribed` reply carries authoritative state.
      const ids = Array.from(this.refCount.keys());
      if (ids.length > 0) this.sendSubscribe(ids);
    });
    ws.addEventListener('message', (ev) => {
      this.onWsMessage(ev as MessageEvent<string>);
    });
    ws.addEventListener('close', () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.setConnected(false);
      this.scheduleReconnect();
    });
    ws.addEventListener('error', () => {
      // The close event will follow; reconnect is scheduled there.
    });
  }

  private resolveWsUrl(path: string): string {
    if (typeof window === 'undefined') return path;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}${path}`;
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    const delay = this.wsBackoff;
    this.wsBackoff = Math.min(this.wsBackoff * 2, MAX_BACKOFF_MS);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openWebSocket();
    }, delay);
  }

  private onWsMessage(ev: MessageEvent<string>): void {
    let frame: ServerEvent;
    try {
      frame = JSON.parse(ev.data) as ServerEvent;
    } catch (err) {
      console.error('ws: invalid JSON frame', err);
      return;
    }
    switch (frame.op) {
      case 'subscribed':
        this.handleSubscribed(frame);
        return;
      case 'entity_changed':
        this.handleEntityChanged(frame);
        return;
      case 'ack':
        this.handleAck(frame.request_id);
        return;
      case 'error':
        this.handleError(frame.request_id, frame.code, frame.message);
        return;
      default:
        // Unknown op — log and ignore; the wire schema is closed but
        // forward-compatible (a future BE may emit ops we don't handle
        // yet, and dropping is the safest stance).
        console.warn('ws: unknown op', frame);
    }
  }

  private handleSubscribed(frame: {
    request_id: string;
    states: Array<{ entity_id: string; model: unknown }>;
  }): void {
    this.pendingSubscribes.delete(frame.request_id);
    for (const state of frame.states) {
      if (state.model == null) continue;
      const eid = asEntityId(state.entity_id);
      try {
        const entity = brandEntityModel(state.model, eid);
        this.setCache(eid, entity);
      } catch (err) {
        console.error('ws: subscribed: bad model', err);
      }
    }
  }

  private handleEntityChanged(frame: {
    entity_id: string;
    attributes: string[];
    deltas?: Record<string, AttributeDelta>;
  }): void {
    const eid = asEntityId(frame.entity_id);
    const cached = this.cache.get(eid);
    if (!cached) return;
    const deltas = frame.deltas ?? {};
    // Mutate a shallow clone so React's reference comparison flips and
    // listeners re-render. Per-attribute mutation lives inside.
    const next: CachedEntity = { ...cached };
    for (const attr of frame.attributes) {
      const delta = deltas[attr];
      if (!delta) continue;
      this.applyDelta(next, eid, attr, delta);
    }
    this.cache.set(eid, next);
    this.notifyListeners(eid);
  }

  // frontend-campaign-collection-delta: apply a typed delta to the
  // cached entity. ListDelta uses splice semantics with `start === -1`
  // short-circuited to push-at-end. ScalarDelta assigns the new value.
  // Per `specs/events.md#events-attribute-deltas`.
  private applyDelta(
    entity: CachedEntity,
    entityId: EntityId,
    attr: string,
    delta: AttributeDelta,
  ): void {
    const target = entity as unknown as Record<string, unknown>;
    if (isListDelta(delta)) {
      const current = (target[attr] as unknown[]) ?? [];
      // Clone so the previous snapshot stays immutable for any
      // observer that captured it.
      const list = [...current];
      // Items inside the delta may need branding (e.g. `messages` carries
      // wire-shape `{sender_id, body}` items the FE materialises with
      // synthetic `scene_id` + `index`).
      const items =
        attr === 'messages' && entity.type === 'scene'
          ? this.materialiseMessageItems(entityId, list.length, delta)
          : delta.items;
      if (delta.start === -1) {
        list.push(...items);
      } else {
        list.splice(delta.start, delta.len, ...items);
      }
      // If the splice happened in the middle of `messages`, re-stamp the
      // `index` of every following item so the FE positional key stays
      // monotonic. Append-at-end (-1) is the common case and skips this.
      if (attr === 'messages' && entity.type === 'scene' && delta.start !== -1) {
        for (let i = delta.start; i < list.length; i += 1) {
          (list[i] as MessageModel).index = i;
        }
      }
      target[attr] = list;
      return;
    }
    if (isScalarDelta(delta)) {
      target[attr] = delta.value;
      return;
    }
    console.warn('ws: unrecognised delta shape', { attr, delta });
  }

  private materialiseMessageItems(
    sceneId: EntityId,
    startIndex: number,
    delta: ListDelta,
  ): MessageModel[] {
    return delta.items.map((raw, i) => {
      const r = raw as { sender_id: string; body: string };
      return {
        scene_id: sceneId,
        index: startIndex + i,
        sender_id: asEntityId(r.sender_id),
        body: r.body,
      };
    });
  }

  private handleAck(request_id: string): void {
    const pending = this.pendingActions.get(request_id);
    if (!pending) return;
    this.pendingActions.delete(request_id);
    pending.resolve();
  }

  private handleError(
    request_id: string,
    code: string,
    message: string,
  ): void {
    const pending = this.pendingActions.get(request_id);
    if (!pending) return;
    this.pendingActions.delete(request_id);
    pending.reject(new Error(`${code}: ${message}`));
  }

  private sendSubscribe(entityIds: EntityId[]): void {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const request_id = newRequestId();
    this.pendingSubscribes.set(request_id, entityIds);
    ws.send(
      JSON.stringify({ op: 'subscribe', entity_ids: entityIds, request_id }),
    );
  }

  private sendUnsubscribe(entityIds: EntityId[]): void {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ op: 'unsubscribe', entity_ids: entityIds }));
  }

  private setConnected(value: boolean): void {
    if (this._connected === value) return;
    this._connected = value;
    for (const l of this.connectedListeners) l();
  }
}
