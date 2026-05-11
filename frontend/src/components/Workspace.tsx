import { useEffect, useState } from 'react';
import { asEntityId, type CampaignResponse, type EntityId } from '../types_ext';
import { EntityPanel } from './EntityPanel';
import { EntitySelector } from './EntitySelector';

// frontend-workspace-deps: injection seam for unit tests. Production
// callers pass nothing; defaults route to the real globals.
export interface WorkspaceDeps {
  fetcher?: typeof fetch;
}

export interface WorkspaceProps {
  deps?: WorkspaceDeps;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

function brandCampaignResponse(raw: unknown): CampaignResponse {
  const r = raw as { name: string; default_scene_id: string | null };
  return {
    name: r.name,
    default_scene_id: r.default_scene_id ? asEntityId(r.default_scene_id) : null,
  };
}

/**
 * frontend-workspace-component: top-level shell.
 *
 * - frontend-workspace-component-bootstrap: fetches campaigns → campaign
 *   on mount and stores `campaignId`, `defaultSceneId`, initial `mainEntityId`.
 * - frontend-workspace-component-layout: renders the static two-slot grid
 *   (selector left, main right).
 */
export function Workspace({ deps = {} }: WorkspaceProps = {}) {
  const doFetch = deps.fetcher ?? fetch;

  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [, setDefaultSceneId] = useState<EntityId | null>(null);
  const [mainEntityId, setMainEntityId] = useState<EntityId | null>(null);

  useEffect(() => {
    let backoff = INITIAL_BACKOFF_MS;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const bootstrap = async () => {
      // frontend-workspace-bootstrap, step 1: list campaigns.
      const campaignsRes = await doFetch('/api/campaigns');
      if (!campaignsRes.ok) throw new Error(`GET /api/campaigns → ${campaignsRes.status}`);
      const campaignsRaw = (await campaignsRes.json()) as Array<{ name: string }>;
      if (campaignsRaw.length === 0) throw new Error('No campaigns loaded');
      const cid = campaignsRaw[0].name;

      // step 2: read the campaign to find default_scene_id.
      const campaignRes = await doFetch(`/api/campaigns/${encodeURIComponent(cid)}`);
      if (!campaignRes.ok) throw new Error(`GET /api/campaigns/${cid} → ${campaignRes.status}`);
      const campaign = brandCampaignResponse(await campaignRes.json());

      if (cancelled) return;
      setCampaignId(cid);
      setDefaultSceneId(campaign.default_scene_id);

      // frontend-workspace-initial-main: URL fragment overrides, else default.
      const fragment = window.location.hash.replace(/^#/, '');
      const initialMain: EntityId | null = fragment
        ? asEntityId(fragment)
        : campaign.default_scene_id;
      setMainEntityId(initialMain);
    };

    const connect = () => {
      if (cancelled) return;
      bootstrap().catch((err) => {
        console.error('Workspace bootstrap failed', err);
        if (cancelled) return;
        const delay = backoff;
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
        retryTimer = setTimeout(connect, delay);
      });
    };

    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onOpenEntity = (id: EntityId) => {
    // frontend-workspace-open-entity: idempotent on same id.
    if (id === mainEntityId) return;
    setMainEntityId(id);
  };

  return (
    <div
      data-testid="workspace"
      className="flex h-full w-full bg-slate-50"
    >
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white">
        <EntitySelector
          campaignId={campaignId}
          onOpenEntity={onOpenEntity}
          fetcher={doFetch}
        />
      </aside>
      <main data-testid="main-slot" className="flex-1 overflow-hidden">
        {campaignId && mainEntityId ? (
          <EntityPanel
            key={mainEntityId}
            campaignId={campaignId}
            entityId={mainEntityId}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Select a scene from the left.
          </div>
        )}
      </main>
    </div>
  );
}
