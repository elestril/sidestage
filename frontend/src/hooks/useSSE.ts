import { useEffect, useRef, useState } from 'react';
import {
  asEntityId,
  asMessageId,
  type CampaignResponse,
  type CharacterModel,
  type EntityId,
  type MessageModel,
  type SceneResponse,
  type SceneUpdatedEvent,
} from '../types_ext';

// frontend-state-messages: { sender, body } pair retained across reconnects.
export interface ChatMessage {
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
  const r = raw as { id: string; sender_id: string; body: string };
  return {
    id: asMessageId(r.id),
    sender_id: asEntityId(r.sender_id),
    body: r.body,
  };
}

/**
 * frontend-usesse: opens an SSE connection and drives the
 * subscribe-then-fetch dataflow described in `frontend-sse-client-dataflow`.
 *
 * - frontend-hook-opens: opens EventSource on mount; closes on unmount.
 * - frontend-hook-scene: after open, fetches campaigns -> campaign -> scene
 *   -> entities and populates state.
 * - frontend-hook-dispatches: handles `scene_updated` events by fetching the
 *   new message slice.
 * - frontend-hook-reconnects: on close, schedules an exponential-backoff
 *   reconnect and clears per-connection state per `sse-client-reconnect`.
 */
export function useSSE(): UseSSEResult {
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
  // re-subscribing on every render.
  const sceneIdRef = useRef<EntityId | null>(null);
  const campaignIdRef = useRef<string | null>(null);
  const entityCacheRef = useRef<Map<EntityId, CharacterModel>>(new Map());
  const lastFetchedIndexRef = useRef<number>(-1);

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
      lastFetchedIndexRef.current = -1;
    };

    const bootstrap = async () => {
      // sse-client-list-campaigns
      const campaignsRes = await fetch('/api/campaigns');
      if (!campaignsRes.ok) throw new Error(`GET /api/campaigns → ${campaignsRes.status}`);
      const campaignsRaw = (await campaignsRes.json()) as Array<{ name: string; default_scene_id: string | null }>;
      if (campaignsRaw.length === 0) throw new Error('No campaigns loaded');
      // The id by which the API addresses a campaign is the campaign name today.
      const cid = campaignsRaw[0].name;
      campaignIdRef.current = cid;
      setCampaignId(cid);

      // sse-client-campaign
      const campaignRes = await fetch(`/api/campaigns/${encodeURIComponent(cid)}`);
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
        return;
      }

      // sse-client-scene
      const sceneRes = await fetch(
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
          const r = await fetch(
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
      const histRes = await fetch(
        `/api/campaigns/${encodeURIComponent(cid)}/scenes/${encodeURIComponent(scene.id)}/messages`,
      );
      if (!histRes.ok) throw new Error(`GET history → ${histRes.status}`);
      const histRaw = (await histRes.json()) as unknown[];
      const history = histRaw.map(brandMessage);
      const resolved: ChatMessage[] = history.flatMap((m) => {
        const sender = cache.get(m.sender_id);
        return sender ? [{ sender, body: m.body }] : [];
      });
      // Replace messages on a fresh bootstrap — `messages` is retained across
      // reconnects but the bootstrap full-fetch is the source of truth at
      // this point in the lifecycle.
      setMessages(resolved);
      lastFetchedIndexRef.current = history.length - 1;
    };

    const handleSceneUpdated = async (raw: SceneUpdatedEvent) => {
      const cid = campaignIdRef.current;
      const sid = sceneIdRef.current;
      if (!cid || !sid) return;
      if (raw.scene_id !== (sid as unknown as string)) return;
      const fromIdx = lastFetchedIndexRef.current + 1;
      const toIdx = raw.latest_message_index + 1;
      if (toIdx <= fromIdx) return;
      const sliceRes = await fetch(
        `/api/campaigns/${encodeURIComponent(cid)}/scenes/${encodeURIComponent(sid)}/messages?from=${fromIdx}&to=${toIdx}`,
      );
      if (!sliceRes.ok) return;
      const sliceRaw = (await sliceRes.json()) as unknown[];
      const slice = sliceRaw.map(brandMessage);
      const cache = entityCacheRef.current;
      const additions: ChatMessage[] = slice.flatMap((m) => {
        const sender = cache.get(m.sender_id);
        return sender ? [{ sender, body: m.body }] : [];
      });
      if (additions.length > 0) {
        setMessages((prev) => [...prev, ...additions]);
      }
      lastFetchedIndexRef.current = raw.latest_message_index;
    };

    const connect = () => {
      if (cancelled) return;
      clearPerConnectionState();
      source = new EventSource('/api/events');

      source.addEventListener('open', () => {
        if (cancelled) return;
        setConnected(true);
        backoff = INITIAL_BACKOFF_MS;
        bootstrap().catch((err) => {
          console.error('SSE bootstrap failed', err);
        });
      });

      source.addEventListener('scene_updated', (ev) => {
        const me = ev as MessageEvent<string>;
        try {
          const payload = JSON.parse(me.data) as SceneUpdatedEvent;
          void handleSceneUpdated(payload);
        } catch (err) {
          console.error('Failed to parse scene_updated event', err);
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
