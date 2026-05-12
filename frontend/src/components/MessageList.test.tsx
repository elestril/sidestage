/**
 * Sanity-tier tests for MessageList.
 *
 * .tests: frontend-messagelist-scroll, frontend-messagelist-items,
 *         frontend-messagelist-testid
 *
 * MessageList no longer carries embedded senders — each row resolves
 * its sender via `useEntity(sender_id)` against the registry. These
 * tests mock the hook so the unit-level behaviour (scroll-on-grow,
 * one-row-per-message, testid) can be exercised without standing up
 * a registry + WebSocket.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import {
  asEntityId,
  type CharacterResponse,
  type EntityId,
  type MessageModel,
} from '../types_ext';
import { MessageList } from './MessageList';

const character = (id: string, name: string): CharacterResponse => ({
  type: 'character',
  id: asEntityId(id),
  name,
  body: '',
  owner: 'user',
});

const message = (
  sceneId: EntityId,
  index: number,
  sender: CharacterResponse,
  body: string,
): MessageModel => ({
  scene_id: sceneId,
  index,
  sender_id: sender.id,
  body,
});

const alice = character('alice', 'Alice');
const bob = character('bob', 'Bob');
const senderById = new Map<string, CharacterResponse>([
  [alice.id as unknown as string, alice],
  [bob.id as unknown as string, bob],
]);

vi.mock('../hooks/useEntity', () => ({
  useEntity: (id: EntityId | null) => {
    if (id === null) return { entity: null, status: 'loading' as const };
    const entity = senderById.get(id as unknown as string) ?? null;
    return { entity, status: entity ? ('ready' as const) : ('loading' as const) };
  },
}));

describe('MessageList', () => {
  const sceneId = asEntityId('parlor');

  // jsdom returns 0 for scrollHeight by default; override so the
  // scroll-to-bottom effect has something to compare against.
  let scrollHeightDescriptor: PropertyDescriptor | undefined;
  beforeEach(() => {
    scrollHeightDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      'scrollHeight',
    );
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get() {
        return 1000;
      },
    });
  });
  afterEach(() => {
    if (scrollHeightDescriptor) {
      Object.defineProperty(
        HTMLElement.prototype,
        'scrollHeight',
        scrollHeightDescriptor,
      );
    } else {
      delete (HTMLElement.prototype as unknown as { scrollHeight?: unknown })
        .scrollHeight;
    }
  });

  test('frontend-messagelist-scroll', () => {
    const { rerender } = render(
      <MessageList
        messages={[message(sceneId, 0, alice, 'Hi')]}
        playerCharacterIds={[alice.id]}
      />,
    );
    const container = screen.getByTestId('message-list').parentElement!;
    expect(
      container.scrollTop,
      'frontend-messagelist-scroll: initial render must scroll to bottom ' +
        '(prev=0 < new=1 messages)',
    ).toBe(1000);

    container.scrollTop = 50;
    rerender(
      <MessageList
        messages={[
          message(sceneId, 0, alice, 'Hi'),
          message(sceneId, 1, bob, '*nods*'),
        ]}
        playerCharacterIds={[alice.id]}
      />,
    );
    expect(
      container.scrollTop,
      'frontend-messagelist-scroll: append (1→2 messages) must scroll to ' +
        'bottom again; expected scrollTop=1000 after re-render',
    ).toBe(1000);

    container.scrollTop = 50;
    rerender(
      <MessageList
        messages={[
          message(sceneId, 0, alice, 'Hi'),
          message(sceneId, 1, bob, '*nods*'),
        ]}
        playerCharacterIds={[alice.id]}
      />,
    );
    expect(
      container.scrollTop,
      'frontend-messagelist-scroll: re-render with same length MUST NOT ' +
        'scroll — only `messages.length > lastLength` triggers',
    ).toBe(50);
  });

  test('frontend-messagelist-items', () => {
    render(
      <MessageList
        messages={[
          message(sceneId, 0, alice, 'Hi'),
          message(sceneId, 1, bob, '*nods*'),
        ]}
        playerCharacterIds={[alice.id]}
      />,
    );
    const items = screen.getAllByTestId('message-item');
    expect(
      items.length,
      `frontend-messagelist-items: one MessageItem per message; got ${items.length}`,
    ).toBe(2);
    expect(items[0]).toHaveTextContent('Hi');
    expect(items[1]).toHaveTextContent('*nods*');
  });

  test('frontend-messagelist-testid', () => {
    render(<MessageList messages={[]} playerCharacterIds={[]} />);
    expect(
      screen.queryByTestId('message-list'),
      'frontend-messagelist-testid: the <ul> must carry data-testid="message-list"',
    ).toBeInTheDocument();
  });
});
