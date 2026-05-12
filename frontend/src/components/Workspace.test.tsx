/**
 * Sanity-tier tests for Workspace.
 *
 * .tests: frontend-workspace-component-layout,
 *         frontend-workspace-component-testid,
 *         frontend-workspace-open-entity,
 *         frontend-workspace-remount-on-change
 *
 * Bootstrap is URL-scoped: the campaign id comes from the first path
 * segment, then `/api/campaigns/{cid}` is fetched. The EntityRegistry
 * normally opens a WebSocket on construction, so tests inject a
 * `registryFactory` that returns a no-op stand-in.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import type { EntityRegistry } from '../entityRegistry';

// Stub EntityPanel: real one consumes useEntity off the registry
// context. The stub also tracks per-mount activations so the
// remount-on-change invariant is observable.
const mountLog = vi.hoisted(() => ({ mounts: [] as string[] }));
vi.mock('./EntityPanel', () => ({
  EntityPanel: ({ entityId }: { entityId: string }) => {
    useEffect(() => {
      mountLog.mounts.push(entityId);
    }, [entityId]);
    return (
      <div data-testid="entity-panel-stub" data-entity-id={entityId}>
        stub:{entityId}
      </div>
    );
  },
}));

import { Workspace } from './Workspace';

interface JsonResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): JsonResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const CID = 'Test';
const parlor = {
  type: 'scene',
  id: 'parlor',
  name: 'Parlor',
  body: '',
  character_ids: [],
  player_character_ids: [],
};
const study = {
  type: 'scene',
  id: 'study',
  name: 'Study',
  body: '',
  character_ids: [],
  player_character_ids: [],
};

function happyFetcher() {
  return vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url === `/api/campaigns/${CID}`) {
      return jsonResponse({ name: CID, default_scene_id: 'parlor' });
    }
    if (url === `/api/campaigns/${CID}/scenes`) {
      return jsonResponse([parlor, study]);
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
}

// EntityRegistry's real constructor opens a WebSocket. The stub
// satisfies the registry-context type without any side effects; the
// mocked EntityPanel never reads from it.
function fakeRegistry(): EntityRegistry {
  return { close: () => undefined } as unknown as EntityRegistry;
}

describe('Workspace', () => {
  beforeEach(() => {
    // URL-scoped bootstrap reads the cid off pathname[0].
    window.history.pushState({}, '', `/${CID}`);
    mountLog.mounts = [];
  });
  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  test('frontend-workspace-component-testid', () => {
    // Hanging fetcher — we only need the synchronous shell, not bootstrap.
    const fetcher = vi.fn(() => new Promise(() => {}));
    render(
      <Workspace
        deps={{
          fetcher: fetcher as unknown as typeof fetch,
          registryFactory: fakeRegistry,
        }}
      />,
    );
    expect(
      screen.queryByTestId('workspace'),
      'frontend-workspace-component-testid: shell must carry data-testid="workspace"',
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('main-slot'),
      'frontend-workspace-component-testid: right slot must carry data-testid="main-slot"',
    ).toBeInTheDocument();
  });

  test('frontend-workspace-component-layout placeholder before bootstrap', () => {
    const fetcher = vi.fn(() => new Promise(() => {}));
    render(
      <Workspace
        deps={{
          fetcher: fetcher as unknown as typeof fetch,
          registryFactory: fakeRegistry,
        }}
      />,
    );
    expect(
      screen.getByTestId('main-slot'),
      'frontend-workspace-component-layout: before bootstrap resolves the ' +
        'main slot must show the empty placeholder, not an EntityPanel',
    ).toHaveTextContent(/select a scene/i);
    expect(screen.queryByTestId('entity-panel-stub')).not.toBeInTheDocument();
  });

  test('frontend-workspace-component-layout default-scene after bootstrap', async () => {
    const fetcher = happyFetcher();
    render(
      <Workspace
        deps={{
          fetcher: fetcher as unknown as typeof fetch,
          registryFactory: fakeRegistry,
        }}
      />,
    );
    const panel = await screen.findByTestId('entity-panel-stub');
    expect(
      panel.getAttribute('data-entity-id'),
      'frontend-workspace-initial-main: with no URL fragment, mainEntityId ' +
        'must equal CampaignResponse.default_scene_id ("parlor")',
    ).toBe('parlor');
  });

  test('frontend-workspace-open-entity + remount-on-change', async () => {
    const fetcher = happyFetcher();
    render(
      <Workspace
        deps={{
          fetcher: fetcher as unknown as typeof fetch,
          registryFactory: fakeRegistry,
        }}
      />,
    );
    await screen.findByTestId('entity-panel-stub');
    await waitFor(() => {
      expect(screen.getAllByTestId('scene-bubble').length).toBeGreaterThan(1);
    });
    expect(mountLog.mounts).toEqual(['parlor']);

    // Double-clicking a different bubble swaps mainEntityId, which remounts
    // the right-slot EntityPanel (key={mainEntityId}).
    const studyBubble = screen
      .getAllByTestId('scene-bubble')
      .find((el) => el.getAttribute('data-entity-id') === 'study')!;
    fireEvent.doubleClick(studyBubble);
    await waitFor(() => {
      expect(
        screen.getByTestId('entity-panel-stub').getAttribute('data-entity-id'),
      ).toBe('study');
    });
    expect(
      mountLog.mounts,
      'frontend-workspace-remount-on-change: a new mainEntityId must remount ' +
        'the EntityPanel (key change), not just re-render with new props; ' +
        `got mount log=${JSON.stringify(mountLog.mounts)}`,
    ).toEqual(['parlor', 'study']);

    // Re-double-clicking the currently-open entity is a no-op (idempotent).
    const studyBubble2 = screen
      .getAllByTestId('scene-bubble')
      .find((el) => el.getAttribute('data-entity-id') === 'study')!;
    fireEvent.doubleClick(studyBubble2);
    // Give React a tick to apply any state change that would have happened.
    await new Promise((r) => setTimeout(r, 0));
    expect(
      mountLog.mounts,
      'frontend-workspace-open-entity: opening an already-open entity must ' +
        'be a no-op — no remount; ' +
        `got mount log=${JSON.stringify(mountLog.mounts)}`,
    ).toEqual(['parlor', 'study']);
  });
});
