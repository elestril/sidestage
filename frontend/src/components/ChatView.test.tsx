/**
 * Sanity-tier test for the ChatView component.
 *
 * Proves the scaffold (vitest + jsdom + testing-library + jest-dom matchers)
 * is wired correctly and shows the spec-label-in-failure-message pattern
 * (per `testing-failure-message`). Real coverage of individual component
 * invariants lands as those specs get labels.
 *
 * .tests: frontend-chatview-list, frontend-chatview-input
 */
import { render, screen } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';

import type { CharacterModel, EntityId } from '../types_ext';
import { ChatView } from './ChatView';

const character = (id: string, name: string): CharacterModel =>
  ({
    id: id as unknown as EntityId,
    name,
    type: 'character',
    body: '',
    owner: 'user',
  } as CharacterModel);

describe('ChatView', () => {
  test('frontend-chatview-list', () => {
    const alice = character('alice', 'Alice');
    const bob = character('bob', 'Bob');
    const sceneId = 'parlor' as unknown as EntityId;
    const messages = [
      { scene_id: sceneId, index: 0, sender: alice, body: 'Hi' },
      { scene_id: sceneId, index: 1, sender: bob, body: '*nods quietly*' },
    ];
    render(
      <ChatView
        messages={messages}
        playerCharacterIds={[alice.id]}
        connected={true}
        onSend={vi.fn()}
      />,
    );

    expect(
      screen.queryByText('Hi'),
      'frontend-chatview-list: every message body must render inside the ' +
        'MessageList; alice\'s "Hi" was not found in the DOM',
    ).toBeInTheDocument();
    expect(
      screen.queryByText('*nods quietly*'),
      'frontend-chatview-list: every message body must render inside the ' +
        'MessageList; bob\'s reply was not found in the DOM',
    ).toBeInTheDocument();
  });

  test('frontend-chatview-input', () => {
    const alice = character('alice', 'Alice');
    render(
      <ChatView
        messages={[]}
        playerCharacterIds={[alice.id]}
        connected={false}
        onSend={vi.fn()}
      />,
    );

    expect(
      screen.queryByLabelText('disconnected'),
      'frontend-chatview-input: the connected/disconnected indicator must ' +
        'reflect the `connected` prop; expected an element with ' +
        'aria-label="disconnected" when prop is false',
    ).toBeInTheDocument();
  });
});
