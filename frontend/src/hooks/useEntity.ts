import { useEffect, useRef, useState } from 'react';
import {
  asEntityId,
  type CharacterResponse,
  type EntityChangedEvent,
  type EntityId,
  type EntityResponse,
  type MessageModel,
  type SceneResponse,
} from '../types_ext';

// A message resolved for rendering: composite (scene_id, index) wire
// identity + resolved sender + body. Retained across reconnects within
// the panel for UX continuity; the bootstrap history fetch is the
// source of truth.
export interface ChatMessage {
  scene_id: EntityId;
  index: number;
  sender: CharacterResponse;
  body: string;
}

export interface UseEntityArgs {
  campaignId: string;
  entityId: EntityId;
  deps?: UseEntityDeps;
}

export interface UseEntityResult {
  entity: EntityResponse | null;
  entityCache: Map<EntityId, CharacterResponse>;
  playerCharacterIds: EntityId[];
  messages: ChatMessage[];
  connected: boolean;
}

// frontend-useentity-deps: injection seam for unit tests. Production
// callers pass nothing; defaults route to the real globals.
export interface UseEntityDeps {
  fetcher?: typeof fetch;
  eventSourceFactory?: (url: string) => EventSource;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

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

/**
 * frontend-useentity: per-panel bootstrap-and-subscribe hook.
 *
 * - frontend-useentity-bootstraps: fetches the entity (and, for Scene,
 *   character dependents + message history), then opens SSE.
 * - frontend-useentity-subscribes: opens
 *   `EventSource('/api/campaigns/{cid}/entities/{eid}/events')` per
 *   `events-subscription`.
 * - frontend-useentity-dispatches: handles `entity_changed` events by
 *   serialised slice fetches (`sse-client-event-serialized`).
 * - frontend-useentity-reconnects: on transport error, exponential
 *   backoff reconnect; full state refetch per
 *   `frontend-be-consistency-event-loss`.
 */
export function useEntity({ campaignId, entityId, deps = {} }: UseEntityArgs): UseEntityResult {
  const doFetch = deps.fetcher ?? fetch;
  const makeEventSource =
    deps.eventSourceFactory ?? ((url: string) => new EventSource(url));

  const [entity, setEntity] = useState<EntityResponse | null>(null);
  const [entityCache, setEntityCache] = useState<Map<EntityId, CharacterResponse>>(
    () => new Map(),
  );
  const [playerCharacterIds, setPlayerCharacterIds] = useState<EntityId[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connected, setConnected] = useState<boolean>(false);

  // Refs so the SSE event handler can read the current cache / messages
  // without re-subscribing on every render.
  const entityCacheRef = useRef<Map<EntityId, CharacterResponse>>(new Map());
  const messagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    let backoff = INITIAL_BACKOFF_MS;
    let cancelled = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearPerConnectionState = () => {
      // sse-client-reconnect: clear cache, playerCharacterIds; retain
      // `messages` for UX continuity (bootstrap full-refetch replaces).
      setEntityCache(new Map());
      setPlayerCharacterIds([]);
      setEntity(null);
      entityCacheRef.current = new Map();
    };

    const lastIndexFor = (sid: EntityId): number => {
      const arr = messagesRef.current;
      for (let i = arr.length - 1; i >= 0; i -= 1) {
        if (arr[i].scene_id === sid) return arr[i].index;
      }
      return -1;
    };

    const setMessagesTracked = (next: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
      setMessages((prev) => {
        const resolved = typeof next === 'function' ? next(prev) : next;
        messagesRef.current = resolved;
        return resolved;
      });
    };

    // Slice fetches MUST be serialized per `sse-client-event-serialized`.
    let sliceChain: Promise<void> = Promise.resolve();

    const runSliceFetch = async (sid: EntityId) => {
      const fromIdx = lastIndexFor(sid) + 1;
      const sliceRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(campaignId)}/scenes/${encodeURIComponent(sid)}/messages?from=${fromIdx}`,
      );
      if (!sliceRes.ok) return;
      const sliceRaw = (await sliceRes.json()) as unknown[];
      const slice = sliceRaw.map(brandMessage);
      if (slice.length === 0) return;
      const cache = entityCacheRef.current;
      const additions: ChatMessage[] = slice.flatMap((m) => {
        const sender = cache.get(m.sender_id);
        return sender
          ? [{ scene_id: m.scene_id, index: m.index, sender, body: m.body }]
          : [];
      });
      if (additions.length > 0) {
        setMessagesTracked((prev) => [...prev, ...additions]);
      }
    };

    const handleEntityChanged = (event: EntityChangedEvent): void => {
      if (event.entity_id !== entityId) return;
      if (!event.attributes.includes('messages')) return;
      sliceChain = sliceChain
        .then(() => runSliceFetch(entityId))
        .catch((err) => {
          console.error('slice fetch failed', err);
        });
    };

    const subscribe = () => {
      source = makeEventSource(
        `/api/campaigns/${encodeURIComponent(campaignId)}/entities/${encodeURIComponent(entityId)}/events`,
      );

      source.addEventListener('open', () => {
        if (cancelled) return;
        setConnected(true);
        backoff = INITIAL_BACKOFF_MS;
      });

      source.addEventListener('entity_changed', (ev) => {
        const me = ev as MessageEvent<string>;
        try {
          const raw = JSON.parse(me.data) as { entity_id: string; attributes: string[] };
          handleEntityChanged({
            entity_id: asEntityId(raw.entity_id),
            attributes: raw.attributes,
          });
        } catch (err) {
          console.error('Failed to parse entity_changed event', err);
        }
      });

      source.addEventListener('error', () => {
        if (cancelled) return;
        setConnected(false);
        if (source) {
          source.close();
          source = null;
        }
        const delay = backoff;
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
        reconnectTimer = setTimeout(connect, delay);
      });
    };

    const bootstrap = async (): Promise<void> => {
      // sse-client-entity
      const entityRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(campaignId)}/entities/${encodeURIComponent(entityId)}`,
      );
      if (!entityRes.ok) throw new Error(`GET entity ${entityId} → ${entityRes.status}`);
      const fetched = brandEntityResponse(await entityRes.json());
      setEntity(fetched);

      if (fetched.type !== 'scene') {
        // Non-Scene entity panels don't need dependents or history;
        // the dispatcher renders an unknown-type placeholder.
        return;
      }

      const scene = fetched;
      setPlayerCharacterIds(scene.player_character_ids);

      // sse-client-dependents — fetch character entities in parallel.
      const entityResults = await Promise.all(
        scene.character_ids.map(async (eid) => {
          const r = await doFetch(
            `/api/campaigns/${encodeURIComponent(campaignId)}/entities/${encodeURIComponent(eid)}`,
          );
          if (!r.ok) throw new Error(`GET dependent entity ${eid} → ${r.status}`);
          return brandCharacterResponse(await r.json());
        }),
      );
      const cache = new Map<EntityId, CharacterResponse>();
      for (const c of entityResults) cache.set(c.id, c);
      entityCacheRef.current = cache;
      setEntityCache(cache);

      // sse-client-history — full slice, replaces messages.
      const histRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(campaignId)}/scenes/${encodeURIComponent(scene.id)}/messages`,
      );
      if (!histRes.ok) throw new Error(`GET history → ${histRes.status}`);
      const histRaw = (await histRes.json()) as unknown[];
      const history = histRaw.map(brandMessage);
      const resolved: ChatMessage[] = history.flatMap((m) => {
        const sender = cache.get(m.sender_id);
        return sender
          ? [{ scene_id: m.scene_id, index: m.index, sender, body: m.body }]
          : [];
      });
      setMessagesTracked(resolved);
    };

    const connect = () => {
      if (cancelled) return;
      clearPerConnectionState();
      bootstrap()
        .then(() => {
          if (cancelled) return;
          // frontend-useentity-bootstraps: SSE opens only AFTER bootstrap
          // resolves so the per-entity URL is well-defined.
          subscribe();
        })
        .catch((err) => {
          console.error('useEntity bootstrap failed', err);
          if (cancelled) return;
          const delay = backoff;
          backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
          reconnectTimer = setTimeout(connect, delay);
        });
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (source) source.close();
    };
    // EntityPanel unmounts/remounts on entityId change
    // (`frontend-workspace-remount-on-change`), so this hook captures
    // `campaignId`/`entityId` once at mount. Empty deps are intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    entity,
    entityCache,
    playerCharacterIds,
    messages,
    connected,
  };
}
