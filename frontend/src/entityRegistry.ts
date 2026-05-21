// frontend-entity-registry: EntityRegistry singleton.
//
// One instance per browser tab, constructed by `Workspace` once the
// campaign id is known. Owns the lone multiplexed WebSocket at
// `/api/campaigns/{cid}/ws` and a shared cache of hydrated entities.
//
// Per `specs/frontend.md#frontend-entity-registry` and
// `specs/events.md#events-subscription`.

import {
  asEntityId,
  type CharacterResponse,
  type EntityId,
  type EntityResponse,
  type MessageModel,
  type SceneResponse,
} from './types_ext';

// frontend-state-registry-cache: cached entity for a scene carries a
// synced `messages` array alongside its wire fields. Character entities
// have nothing extra.
export type CachedScene = SceneResponse & { messages: MessageModel[] };
export type CachedEntity = CachedScene | CharacterResponse;

export interface EntityRegistryDeps {
  fetcher?: typeof fetch;
  wsFactory?: (url: string) => WebSocket;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const EVICTION_GRACE_MS = 5_000;

function brandSceneResponse(raw: unknown): SceneResponse {
  const r = raw as {
    type: 'scene';
    id: string;
    name: string;
    body: string;
    character_ids: string[];
    player_character_ids: string[];
  };
  return {
    type: 'scene',
    id: asEntityId(r.id),
    name: r.name,
    body: r.body,
    character_ids: r.character_ids.map(asEntityId),
    player_character_ids: r.player_character_ids.map(asEntityId),
  };
}

function brandCharacterResponse(raw: unknown): CharacterResponse {
  const r = raw as {
    type: 'character';
    id: string;
    name: string;
    body: string;
    owner: 'user' | 'stub';
  };
  return {
    type: 'character',
    id: asEntityId(r.id),
    name: r.name,
    body: r.body,
    owner: r.owner,
  };
}

function brandEntityResponse(raw: unknown): EntityResponse {
  const r = raw as { type: string };
  if (r.type === 'scene') return brandSceneResponse(raw);
  if (r.type === 'character') return brandCharacterResponse(raw);
  throw new Error(`Unknown entity type: ${r.type}`);
}

function brandMessage(raw: unknown): MessageModel {
  const r = raw as { scene_id: string; index: number; sender_id: string; body: string };
  return {
    scene_id: asEntityId(r.scene_id),
    index: r.index,
    sender_id: asEntityId(r.sender_id),
    body: r.body,
  };
}

export class EntityRegistry {
  readonly campaignId: string;

  private readonly fetchFn: typeof fetch;
  private readonly wsFactory: (url: string) => WebSocket;

  private cache = new Map<EntityId, CachedEntity>();
  private refCount = new Map<EntityId, number>();
  private listeners = new Map<EntityId, Set<() => void>>();
  private hydrations = new Map<EntityId, Promise<CachedEntity>>();
  private sliceChains = new Map<EntityId, Promise<void>>();
  private evictTimers = new Map<EntityId, ReturnType<typeof setTimeout>>();

  private connectedListeners = new Set<() => void>();
  private _connected = false;

  private ws: WebSocket | null = null;
  private wsBackoff = INITIAL_BACKOFF_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(campaignId: string, deps: EntityRegistryDeps = {}) {
    this.campaignId = campaignId;
    // Always bind globalThis so passing in `fetch` (or `window.fetch`) does
    // not raise "Illegal invocation" when we call it as `this.fetchFn(...)`.
    const f = deps.fetcher ?? fetch;
    this.fetchFn = f.bind(globalThis);
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
      this.hydrations.set(entityId, this.hydrate(entityId));
      this.sendSubscribe(entityId);
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
        this.sendUnsubscribe(entityId);
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
  }

  // ------------------------------------------------------------------
  // Hydration (REST)
  // ------------------------------------------------------------------

  private async hydrate(entityId: EntityId): Promise<CachedEntity> {
    const entityUrl = `/api/campaigns/${encodeURIComponent(this.campaignId)}/entities/${encodeURIComponent(entityId)}`;
    const res = await this.fetchFn(entityUrl);
    if (!res.ok) throw new Error(`GET entity ${entityId} → ${res.status}`);
    const fetched = brandEntityResponse(await res.json());

    if (fetched.type === 'scene') {
      // ws-client-observe: scene panels need history for first paint.
      // The slice-fetch on entity_changed is for incremental updates.
      const histRes = await this.fetchFn(
        `/api/campaigns/${encodeURIComponent(this.campaignId)}/scenes/${encodeURIComponent(fetched.id)}/messages`,
      );
      if (!histRes.ok) throw new Error(`GET history → ${histRes.status}`);
      const histRaw = (await histRes.json()) as unknown[];
      const messages = histRaw.map(brandMessage);
      const cached: CachedScene = { ...fetched, messages };
      this.setCache(entityId, cached);
      // Best-effort pre-cache of character dependents so sender lookups
      // don't flash during first paint. Failures here don't reject the
      // scene hydration — widgets render senders lazily.
      void Promise.allSettled(
        fetched.character_ids.map((cid) => this.prefetchCharacter(cid)),
      );
      return cached;
    }

    this.setCache(entityId, fetched);
    return fetched;
  }

  private async prefetchCharacter(charId: EntityId): Promise<void> {
    if (this.cache.has(charId)) return;
    const url = `/api/campaigns/${encodeURIComponent(this.campaignId)}/entities/${encodeURIComponent(charId)}`;
    const res = await this.fetchFn(url);
    if (!res.ok) return;
    const fetched = brandEntityResponse(await res.json());
    if (fetched.type !== 'character') return;
    this.setCache(charId, fetched);
  }

  // ------------------------------------------------------------------
  // Slice fetch (REST) on entity_changed[messages]
  // ------------------------------------------------------------------

  private scheduleSliceFetch(entityId: EntityId): void {
    // frontend-entity-registry-slice: per-entity serialization so
    // concurrent entity_changed frames don't double-append.
    const chain = (this.sliceChains.get(entityId) ?? Promise.resolve())
      .then(() => this.runSliceFetch(entityId))
      .catch((err) => {
        console.error('slice fetch failed', err);
      });
    this.sliceChains.set(entityId, chain);
  }

  private async runSliceFetch(entityId: EntityId): Promise<void> {
    const cached = this.cache.get(entityId);
    if (!cached || cached.type !== 'scene') return;
    const lastIndex = cached.messages.length
      ? cached.messages[cached.messages.length - 1].index
      : -1;
    const from = lastIndex + 1;
    const sliceRes = await this.fetchFn(
      `/api/campaigns/${encodeURIComponent(this.campaignId)}/scenes/${encodeURIComponent(entityId)}/messages?from=${from}`,
    );
    if (!sliceRes.ok) return;
    const sliceRaw = (await sliceRes.json()) as unknown[];
    if (sliceRaw.length === 0) return;
    const slice = sliceRaw.map(brandMessage);
    const next: CachedScene = {
      ...cached,
      messages: [...cached.messages, ...slice],
    };
    this.setCache(entityId, next);
  }

  // ------------------------------------------------------------------
  // Cache mutation + listener notification
  // ------------------------------------------------------------------

  private setCache(entityId: EntityId, entity: CachedEntity): void {
    this.cache.set(entityId, entity);
    const set = this.listeners.get(entityId);
    if (set) for (const l of set) l();
  }

  private scheduleEviction(entityId: EntityId): void {
    // Grace period absorbs panel-switch churn (mount/unmount/mount).
    const t = setTimeout(() => {
      this.evictTimers.delete(entityId);
      if ((this.refCount.get(entityId) ?? 0) > 0) return;
      this.cache.delete(entityId);
      this.hydrations.delete(entityId);
      this.sliceChains.delete(entityId);
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
      // the server has the same subscription set as the client.
      for (const eid of this.refCount.keys()) {
        // Refresh cache by re-hydrating; the freshly-fetched state
        // overwrites any drift accumulated during the disconnect.
        this.hydrations.set(eid, this.hydrate(eid));
        this.sendSubscribe(eid);
      }
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
    let frame: { op?: string; entity_id?: string; attributes?: string[] };
    try {
      frame = JSON.parse(ev.data);
    } catch (err) {
      console.error('ws: invalid JSON frame', err);
      return;
    }
    if (frame.op === 'entity_changed') {
      const eid = frame.entity_id ? asEntityId(frame.entity_id) : null;
      if (!eid) return;
      if (frame.attributes?.includes('messages')) {
        this.scheduleSliceFetch(eid);
      }
      return;
    }
    // Phase 2 mutation ops (ack/error) land here.
  }

  private sendSubscribe(entityId: EntityId): void {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ op: 'subscribe', entity_id: entityId }));
  }

  private sendUnsubscribe(entityId: EntityId): void {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ op: 'unsubscribe', entity_id: entityId }));
  }

  private setConnected(value: boolean): void {
    if (this._connected === value) return;
    this._connected = value;
    for (const l of this.connectedListeners) l();
  }
}
