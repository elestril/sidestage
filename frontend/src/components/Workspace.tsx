import { useEffect, useMemo, useState } from 'react';
import { EntityRegistry } from '../entityRegistry';
import { EntityRegistryProvider } from '../hooks/useEntity';
import { asEntityId, type CampaignResponse, type EntityId } from '../types_ext';
import { EntityPanel } from './EntityPanel';
import { EntitySelector } from './EntitySelector';

// frontend-workspace-deps: injection seam for unit tests. Production
// callers pass nothing; defaults route to the real globals.
export interface WorkspaceDeps {
  fetcher?: typeof fetch;
  registryFactory?: (
    campaignId: string,
    deps: { fetcher?: typeof fetch },
  ) => EntityRegistry;
  // Hook for the dev-only empty-path self-redirect. Defaults to
  // `window.location.replace`; tests inject a spy because jsdom's
  // `window.location` is non-configurable.
  redirect?: (url: string) => void;
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
 * - frontend-workspace-component-registry: constructs the EntityRegistry
 *   once `campaignId` is known and wraps children in the provider.
 * - frontend-workspace-component-layout: renders the static two-slot grid
 *   (selector left, main right).
 */
export function Workspace({ deps = {} }: WorkspaceProps = {}) {
  const doFetch = deps.fetcher ?? fetch;
  const registryFactory =
    deps.registryFactory ??
    ((cid, d) => new EntityRegistry(cid, { fetcher: d.fetcher }));
  const redirect = deps.redirect ?? ((url: string) => window.location.replace(url));

  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [, setDefaultSceneId] = useState<EntityId | null>(null);
  const [mainEntityId, setMainEntityId] = useState<EntityId | null>(null);
  const [bootstrapError, setBootstrapError] = useState<
    'no-campaigns' | null
  >(null);

  useEffect(() => {
    let backoff = INITIAL_BACKOFF_MS;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const bootstrap = async () => {
      // frontend-workspace-cid-from-url: the campaign id is the first
      // path segment, URL-decoded. In prod the backend 302-redirects
      // `/` → `/<cid>` (per `backend-route-root`); in dev the vite
      // server doesn't, so the SPA self-redirects on empty path by
      // picking the first campaign returned by `/api/campaigns`.
      const segments = window.location.pathname.split('/').filter(Boolean);
      if (segments.length === 0) {
        const listRes = await doFetch('/api/campaigns');
        if (!listRes.ok) {
          throw new Error(`GET /api/campaigns → ${listRes.status}`);
        }
        const campaigns = (await listRes.json()) as Array<{ name: string }>;
        if (cancelled) return;
        if (campaigns.length === 0) {
          // Terminal — no campaigns on the server. Render a clear
          // empty-state instead of looping forever on a retry.
          throw new Error('NO_CAMPAIGNS_LOADED');
        }
        redirect('/' + encodeURIComponent(campaigns[0].name));
        return; // Browser navigates; the new page will re-run bootstrap.
      }
      const cid = decodeURIComponent(segments[0]);

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
        if (cancelled) return;
        // Terminal error — render an empty-state, don't loop.
        if (err instanceof Error && err.message === 'NO_CAMPAIGNS_LOADED') {
          setBootstrapError('no-campaigns');
          return;
        }
        console.error('Workspace bootstrap failed', err);
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

  // frontend-workspace-component-registry: one EntityRegistry per
  // campaignId; reconstructed if the id ever changes (today: never).
  const registry = useMemo(() => {
    if (!campaignId) return null;
    return registryFactory(campaignId, { fetcher: doFetch });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  // Tear down the WS on unmount or campaign switch so we don't leak.
  useEffect(() => {
    return () => {
      registry?.close();
    };
  }, [registry]);

  const onOpenEntity = (id: EntityId) => {
    if (id === mainEntityId) return;
    setMainEntityId(id);
  };

  return (
    <div data-testid="workspace" className="flex h-full w-full bg-slate-50">
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white">
        <EntitySelector
          campaignId={campaignId}
          onOpenEntity={onOpenEntity}
          fetcher={doFetch}
        />
      </aside>
      <main data-testid="main-slot" className="flex-1 overflow-hidden">
        {registry && mainEntityId ? (
          <EntityRegistryProvider value={registry}>
            <EntityPanel key={mainEntityId} entityId={mainEntityId} />
          </EntityRegistryProvider>
        ) : bootstrapError === 'no-campaigns' ? (
          <div
            data-testid="workspace-no-campaigns"
            className="flex h-full items-center justify-center text-sm text-slate-500"
          >
            No campaigns loaded.
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Select a scene from the left.
          </div>
        )}
      </main>
    </div>
  );
}
