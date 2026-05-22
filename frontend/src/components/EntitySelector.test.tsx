/**
 * Sanity-tier tests for EntitySelector.
 *
 * .tests: frontend-entityselector-fetch, frontend-entityselector-double-click,
 *         frontend-entityselector-testid
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import { asEntityId } from '../types_ext';
import { EntitySelector } from './EntitySelector';

interface JsonResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): JsonResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const parlor = {
  type: 'scene',
  id: 'parlor',
  name: 'Parlor',
  body: '',
  characters: [],
  player_character_ids: [],
};
const study = {
  type: 'scene',
  id: 'study',
  name: 'Study',
  body: '',
  characters: [],
  player_character_ids: [],
};

describe('EntitySelector', () => {
  test('frontend-entityselector-fetch', async () => {
    const fetcher = vi.fn(async (_url: string) => jsonResponse([parlor, study]));
    render(
      <EntitySelector
        campaignId="Test"
        onOpenEntity={() => {}}
        fetcher={fetcher as unknown as typeof fetch}
      />,
    );
    await waitFor(() => {
      expect(screen.queryByText('Parlor')).toBeInTheDocument();
    });
    expect(
      fetcher.mock.calls[0][0],
      'frontend-entityselector-fetch: must GET /api/campaigns/{cid}/scenes ' +
        'on mount with the URL-encoded campaign id',
    ).toBe('/api/campaigns/Test/scenes');
    expect(
      screen.queryByText('Study'),
      'frontend-entityselector-fetch: every scene returned must render as a bubble',
    ).toBeInTheDocument();
  });

  test('frontend-entityselector-fetch-null-campaign-noop', () => {
    const fetcher = vi.fn();
    render(
      <EntitySelector
        campaignId={null}
        onOpenEntity={() => {}}
        fetcher={fetcher as unknown as typeof fetch}
      />,
    );
    expect(
      fetcher.mock.calls.length,
      'frontend-entityselector-fetch: a null campaignId must NOT issue a fetch ' +
        '(workspace bootstrap hasn\'t resolved yet)',
    ).toBe(0);
  });

  test('frontend-entityselector-double-click', async () => {
    const fetcher = vi.fn(async () => jsonResponse([parlor]));
    const onOpenEntity = vi.fn();
    render(
      <EntitySelector
        campaignId="Test"
        onOpenEntity={onOpenEntity}
        fetcher={fetcher as unknown as typeof fetch}
      />,
    );
    const bubble = await screen.findByTestId('scene-bubble');
    fireEvent.doubleClick(bubble);
    expect(
      onOpenEntity.mock.calls,
      'frontend-entityselector-double-click: double-click must call ' +
        `onOpenEntity(bubble.id); got calls=${JSON.stringify(onOpenEntity.mock.calls)}`,
    ).toEqual([[asEntityId('parlor')]]);
  });

  test('frontend-entityselector-testid', async () => {
    const fetcher = vi.fn(async () => jsonResponse([]));
    render(
      <EntitySelector
        campaignId="Test"
        onOpenEntity={() => {}}
        fetcher={fetcher as unknown as typeof fetch}
      />,
    );
    await waitFor(() => {
      expect(fetcher).toHaveBeenCalled();
    });
    expect(
      screen.queryByTestId('entity-selector'),
      'frontend-entityselector-testid: the <ul> container must carry ' +
        'data-testid="entity-selector"',
    ).toBeInTheDocument();
  });
});
