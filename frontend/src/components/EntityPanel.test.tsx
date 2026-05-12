/**
 * Sanity-tier tests for the EntityPanel dispatcher.
 *
 * .tests: frontend-entitypanel-dispatch, frontend-entitypanel-fallback
 *
 * EntityPanel now dispatches via the widget registry
 * (`../widgets/registry`). The dispatch test stubs the registry so it
 * confirms the chosen branch without rendering real panels (which
 * pull in their own hook dependencies).
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import type { CharacterResponse, EntityId, SceneResponse } from '../types_ext';
import { asEntityId } from '../types_ext';

const useEntityMock = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useEntity', () => ({ useEntity: useEntityMock }));

// Replace the widget table with stubs: only `scene` is registered, so
// `character` exercises the unknown-type fallback (matches production
// shape — `widgets.character` is intentionally absent until Phase 2).
vi.mock('../widgets/registry', () => ({
  widgets: {
    scene: {
      Panel: ({ entity }: { entity: SceneResponse }) => (
        <div data-testid="scene-panel-stub" data-entity-id={entity.id}>
          stub
        </div>
      ),
    },
  },
}));

import { EntityPanel } from './EntityPanel';

const sceneEntity = (id: EntityId): SceneResponse => ({
  type: 'scene',
  id,
  name: 'Parlor',
  body: '',
  character_ids: [],
  player_character_ids: [],
});

const characterEntity = (id: EntityId): CharacterResponse => ({
  type: 'character',
  id,
  name: 'Alice',
  body: '',
  owner: 'user',
});

describe('EntityPanel', () => {
  test('frontend-entitypanel-dispatch scene', () => {
    const id = asEntityId('parlor');
    useEntityMock.mockReturnValue({ entity: sceneEntity(id), status: 'ready' });
    render(<EntityPanel entityId={id} />);
    expect(
      screen.queryByTestId('scene-panel-stub'),
      'frontend-entitypanel-dispatch: entity.type === "scene" must render ' +
        'the registered Scene panel',
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('unknown-entity-panel'),
      'frontend-entitypanel-dispatch: scene branch must NOT also render the ' +
        'unknown-type fallback',
    ).not.toBeInTheDocument();
  });

  test('frontend-entitypanel-fallback character', () => {
    const id = asEntityId('alice');
    useEntityMock.mockReturnValue({
      entity: characterEntity(id),
      status: 'ready',
    });
    render(<EntityPanel entityId={id} />);
    const fallback = screen.queryByTestId('unknown-entity-panel');
    expect(
      fallback,
      'frontend-entitypanel-fallback: unregistered entity types must render ' +
        'the UnknownEntityPanel placeholder',
    ).toBeInTheDocument();
    expect(
      fallback!.textContent,
      'frontend-entitypanel-fallback: the placeholder must NAME the missing ' +
        'type so debugging is possible; expected "character" in the message',
    ).toContain('character');
  });

  test('frontend-entitypanel-loading-state', () => {
    const id = asEntityId('parlor');
    useEntityMock.mockReturnValue({ entity: null, status: 'loading' });
    render(<EntityPanel entityId={id} />);
    // Pre-hydration (entity === null) the panel shows a placeholder, not
    // the dispatch branches. This is the precondition that makes the
    // type-dispatch tests above meaningful.
    expect(screen.queryByTestId('scene-panel-stub')).not.toBeInTheDocument();
    expect(screen.queryByTestId('unknown-entity-panel')).not.toBeInTheDocument();
  });
});
