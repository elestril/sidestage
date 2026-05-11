import { useEffect, useState } from 'react';
import { asEntityId, type EntityId, type SceneResponse } from '../types_ext';
import { SceneBubble } from './SceneBubble';

export interface EntitySelectorProps {
  campaignId: string | null;
  onOpenEntity: (id: EntityId) => void;
  fetcher?: typeof fetch;
}

function brandSceneListing(raw: unknown): SceneResponse {
  // Listing endpoint returns SceneResponse[]. We only brand the id-bearing
  // fields; the rest of the wire shape matches the typed response.
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

/**
 * frontend-entityselector: workspace panel listing Scene entities.
 *
 * - frontend-entityselector-fetch: fetches `/api/campaigns/{cid}/scenes`
 *   on mount / `campaignId` change. Snapshot-only (no SSE).
 * - frontend-entityselector-double-click: double-clicking a bubble calls
 *   `onOpenEntity(bubble.id)`.
 * - frontend-entityselector-testid: `data-testid="entity-selector"`.
 */
export function EntitySelector({
  campaignId,
  onOpenEntity,
  fetcher,
}: EntitySelectorProps) {
  const doFetch = fetcher ?? fetch;
  const [scenes, setScenes] = useState<SceneResponse[]>([]);

  useEffect(() => {
    if (!campaignId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await doFetch(`/api/campaigns/${encodeURIComponent(campaignId)}/scenes`);
        if (!res.ok) throw new Error(`GET /scenes → ${res.status}`);
        const raw = (await res.json()) as unknown[];
        if (cancelled) return;
        setScenes(raw.map(brandSceneListing));
      } catch (err) {
        console.error('EntitySelector fetch failed', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaignId, doFetch]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        Scenes
      </div>
      <ul
        data-testid="entity-selector"
        className="flex-1 overflow-y-auto p-2"
      >
        {scenes.map((scene) => (
          <SceneBubble
            key={scene.id}
            scene={scene}
            onOpen={() => onOpenEntity(scene.id)}
          />
        ))}
      </ul>
    </div>
  );
}
