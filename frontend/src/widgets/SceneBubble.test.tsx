/**
 * Sanity-tier tests for SceneBubble.
 *
 * .tests: frontend-scenebubble-renders, frontend-scenebubble-double-click,
 *         frontend-scenebubble-data
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import { asEntityId, type EntityId, type SceneResponse } from '../types_ext';
import { SceneBubble } from './SceneBubble';

const scene = (id: EntityId, name: string): SceneResponse => ({
  type: 'scene',
  id,
  name,
  body: '',
  character_ids: [],
  player_character_ids: [],
});

describe('SceneBubble', () => {
  test('frontend-scenebubble-renders', () => {
    const id = asEntityId('parlor');
    render(<SceneBubble scene={scene(id, 'Parlor')} onOpen={() => {}} />);
    expect(
      screen.queryByText('Parlor'),
      'frontend-scenebubble-renders: scene.name must be rendered as visible text',
    ).toBeInTheDocument();
  });

  test('frontend-scenebubble-double-click', () => {
    const onOpen = vi.fn();
    const id = asEntityId('parlor');
    render(<SceneBubble scene={scene(id, 'Parlor')} onOpen={onOpen} />);
    fireEvent.doubleClick(screen.getByTestId('scene-bubble'));
    expect(
      onOpen.mock.calls.length,
      'frontend-scenebubble-double-click: double-click must fire onOpen() ' +
        `exactly once; got ${onOpen.mock.calls.length} call(s)`,
    ).toBe(1);
  });

  test('frontend-scenebubble-double-click-single-click-noop', () => {
    const onOpen = vi.fn();
    const id = asEntityId('parlor');
    render(<SceneBubble scene={scene(id, 'Parlor')} onOpen={onOpen} />);
    fireEvent.click(screen.getByTestId('scene-bubble'));
    expect(
      onOpen.mock.calls.length,
      'frontend-scenebubble-double-click: single-click MUST NOT fire onOpen — ' +
        'only double-click is bound per spec',
    ).toBe(0);
  });

  test('frontend-scenebubble-data', () => {
    const id = asEntityId('parlor');
    render(<SceneBubble scene={scene(id, 'Parlor')} onOpen={() => {}} />);
    const node = screen.getByTestId('scene-bubble');
    expect(
      node.getAttribute('data-entity-id'),
      'frontend-scenebubble-data: bubble must carry data-entity-id=scene.id',
    ).toBe('parlor');
  });
});
