import { useEffect, useRef, useState } from 'react';
import {
  asEntityId,
  type CampaignResponse,
  type CharacterModel,
  type EntityChangedEvent,
  type EntityId,
  type MessageModel,
  type SceneResponse,
} from '../types_ext';

// frontend-state-messages: a message carries its composite wire identity
// `(scene_id, index)`, resolved sender, and body. Retained across reconnects.
// `(scene_id, index)` is the React key and the pagination cursor.
export interface ChatMessage {
  scene_id: EntityId;
  index: number;
  sender: CharacterModel;
  body: string;
}

export interface UseSSEResult {
  messages: ChatMessage[];
  entityCache: Map<EntityId, CharacterModel>;
  playerCharacterIds: EntityId[];
  campaignId: string | null;
  sceneId: EntityId | null;
  defaultSceneId: EntityId | null;
  connected: boolean;
}

// frontend-usesse-deps: injection seam for unit tests. Production callers
// pass nothing; defaults route to the real globals.
export interface UseSSEDeps {
  fetcher?: typeof fetch;
  eventSourceFactory?: (url: string) => EventSource;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

// Coerce a raw wire entity into a branded CharacterModel. We trust the server
// to send the correct discriminant; this is the boundary cast.
function brandCharacter(raw: unknown): CharacterModel {
  const r = raw as {
    id: string;
    name: string;
    type: 'character';
    body: string;
    owner: 'user' | 'npc' | 'stub';
  };
  return {
    id: asEntityId(r.id),
    name: r.name,
    type: r.type,
    body: r.body,
    owner: r.owner,
  };
}

function brandSceneResponse(raw: unknown): SceneResponse {
  const r = raw as {
    id: string;
    name: string;
    character_ids: string[];
    player_character_ids: string[];
  };
  return {
    id: asEntityId(r.id),
    name: r.name,
    character_ids: r.character_ids.map(asEntityId),
    player_character_ids: r.player_character_ids.map(asEntityId),
  };
}

function brandCampaignResponse(raw: unknown): CampaignResponse {
  const r = raw as { name: string; default_scene_id: string | null };
  return {
    name: r.name,
    default_scene_id: r.default_scene_id ? asEntityId(r.default_scene_id) : null,
  };
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
 * frontend-usesse: drives the bootstrap-then-subscribe SSE dataflow
 * described in `frontend-sse-client-dataflow`.
 *
 * - frontend-hook-bootstraps-first: on mount, fetches campaigns -> campaign
 *   -> scene -> entities -> history, populating state. THEN opens the SSE
 *   stream on the resolved scene's per-entity URL.
 * - frontend-hook-subscribes-per-entity: opens
 *   `EventSource('/api/campaigns/{cid}/entities/{sceneId}/events')` —
 *   per-entity stream, per `events-subscription`.
 * - frontend-hook-dispatches: handles `entity_changed` events by fetching
 *   the message slice from `lastFetchedIndex + 1` when the event names the
 *   current scene and `attributes` contains `"messages"`.
 * - frontend-hook-reconnects: on transport error, schedules an exponential
 *   backoff reconnect and clears per-connection state per `sse-client-reconnect`.
 */
export function useSSE(deps: UseSSEDeps = {}): UseSSEResult {
  const doFetch = deps.fetcher ?? fetch;
  const makeEventSource =
    deps.eventSourceFactory ?? ((url: string) => new EventSource(url));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [entityCache, setEntityCache] = useState<Map<EntityId, CharacterModel>>(
    () => new Map(),
  );
  const [playerCharacterIds, setPlayerCharacterIds] = useState<EntityId[]>([]);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [sceneId, setSceneId] = useState<EntityId | null>(null);
  const [defaultSceneId, setDefaultSceneId] = useState<EntityId | null>(null);
  const [connected, setConnected] = useState<boolean>(false);

  // Refs so the SSE event handler can read the current scene/cache without
  // re-subscribing on every render. `messagesRef` mirrors `messages` so the
  // slice handler can read the latest index without a stale closure.
  const sceneIdRef = useRef<EntityId | null>(null);
  const campaignIdRef = useRef<string | null>(null);
  const entityCacheRef = useRef<Map<EntityId, CharacterModel>>(new Map());
  const messagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    let backoff = INITIAL_BACKOFF_MS;
    let cancelled = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearPerConnectionState = () => {
      // sse-client-reconnect: clear cache, campaignId, playerCharacterIds;
      // retain `messages`.
      setEntityCache(new Map());
      setPlayerCharacterIds([]);
      setCampaignId(null);
      setSceneId(null);
      setDefaultSceneId(null);
      sceneIdRef.current = null;
      campaignIdRef.current = null;
      entityCacheRef.current = new Map();
    };

    const lastIndexFor = (sid: EntityId): number => {
      // Find the highest index in `messagesRef` for this scene; -1 if empty.
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

    const handleEntityChanged = async (event: EntityChangedEvent) => {
      const cid = campaignIdRef.current;
      const sid = sceneIdRef.current;
      if (!cid || !sid) return;
      if (event.entity_id !== sid) return;
      if (!event.attributes.includes('messages')) return;
      const fromIdx = lastIndexFor(sid) + 1;
      const sliceRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(cid)}/scenes/${encodeURIComponent(sid)}/messages?from=${fromIdx}`,
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

    const subscribe = (cid: string, sid: EntityId) => {
      // frontend-hook-subscribes-per-entity: open per-entity SSE stream.
      source = makeEventSource(
        `/api/campaigns/${encodeURIComponent(cid)}/entities/${encodeURIComponent(sid)}/events`,
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
          void handleEntityChanged({
            entity_id: asEntityId(raw.entity_id),
            attributes: raw.attributes,
          });
        } catch (err) {
          console.error('Failed to parse entity_changed event', err);
        }
      });

      source.addEventListener('error', () => {
        // EventSource auto-reconnects on transient errors but we want
        // explicit control of state and backoff per the spec.
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

    const bootstrap = async (): Promise<{ cid: string; sceneId: EntityId } | null> => {
      // sse-client-list-campaigns
      const campaignsRes = await doFetch('/api/campaigns');
      if (!campaignsRes.ok) throw new Error(`GET /api/campaigns → ${campaignsRes.status}`);
      const campaignsRaw = (await campaignsRes.json()) as Array<{ name: string; default_scene_id: string | null }>;
      if (campaignsRaw.length === 0) throw new Error('No campaigns loaded');
      // The id by which the API addresses a campaign is the campaign name today.
      const cid = campaignsRaw[0].name;
      campaignIdRef.current = cid;
      setCampaignId(cid);

      // sse-client-campaign
      const campaignRes = await doFetch(`/api/campaigns/${encodeURIComponent(cid)}`);
      if (!campaignRes.ok) throw new Error(`GET /api/campaigns/${cid} → ${campaignRes.status}`);
      const campaign = brandCampaignResponse(await campaignRes.json());
      setDefaultSceneId(campaign.default_scene_id);

      // Pick the scene to display — URL fragment if present, else default.
      const fragment = window.location.hash.replace(/^#/, '');
      const chosenSceneId: EntityId | null = fragment
        ? asEntityId(fragment)
        : campaign.default_scene_id;
      if (!chosenSceneId) {
        // No scene to display; bootstrap stops here. The client could surface
        // a scene-picker UI in the future.
        return null;
      }

      // sse-client-scene
      const sceneRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(cid)}/scenes/${encodeURIComponent(chosenSceneId)}`,
      );
      if (!sceneRes.ok) throw new Error(`GET scene ${chosenSceneId} → ${sceneRes.status}`);
      const scene = brandSceneResponse(await sceneRes.json());
      sceneIdRef.current = scene.id;
      setSceneId(scene.id);
      setPlayerCharacterIds(scene.player_character_ids);

      // sse-client-entities — fetch all character entities in parallel.
      const entityResults = await Promise.all(
        scene.character_ids.map(async (eid) => {
          const r = await doFetch(
            `/api/campaigns/${encodeURIComponent(cid)}/entities/${encodeURIComponent(eid)}`,
          );
          if (!r.ok) throw new Error(`GET entity ${eid} → ${r.status}`);
          return brandCharacter(await r.json());
        }),
      );
      const cache = new Map<EntityId, CharacterModel>();
      for (const c of entityResults) cache.set(c.id, c);
      entityCacheRef.current = cache;
      setEntityCache(cache);

      // Initial history fetch — full slice. Append any messages so a
      // refresh shows existing history.
      const histRes = await doFetch(
        `/api/campaigns/${encodeURIComponent(cid)}/scenes/${encodeURIComponent(scene.id)}/messages`,
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
      // Replace messages on a fresh bootstrap — `messages` is retained across
      // reconnects but the bootstrap full-fetch is the source of truth at
      // this point in the lifecycle.
      setMessagesTracked(resolved);

      return { cid, sceneId: scene.id };
    };

    const connect = () => {
      if (cancelled) return;
      clearPerConnectionState();
      bootstrap()
        .then((result) => {
          if (cancelled || !result) return;
          // frontend-hook-bootstraps-first: SSE opens only AFTER bootstrap
          // resolves the scene, so the per-entity URL is well-defined.
          subscribe(result.cid, result.sceneId);
        })
        .catch((err) => {
          console.error('SSE bootstrap failed', err);
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
    // Only run on mount/unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    messages,
    entityCache,
    playerCharacterIds,
    campaignId,
    sceneId,
    defaultSceneId,
    connected,
  };
}
