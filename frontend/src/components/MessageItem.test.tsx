/**
 * Sanity-tier tests for MessageItem.
 *
 * .tests: frontend-messageitem-own, frontend-messageitem-other,
 *         frontend-messageitem-sender, frontend-messageitem-data
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import {
  asEntityId,
  type ChatMessage,
  type CharacterResponse,
  type EntityId,
} from '../types_ext';
import { MessageItem } from './MessageItem';

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
): ChatMessage => ({ scene_id: sceneId, index, sender, body });

describe('MessageItem', () => {
  const sceneId = asEntityId('parlor');
  const alice = character('alice', 'Alice');

  test('frontend-messageitem-own', () => {
    render(<MessageItem message={message(sceneId, 0, alice, 'Hi')} isOwn={true} />);
    const node = screen.getByTestId('message-item');
    expect(
      node.className,
      'frontend-messageitem-own: isOwn=true must right-align (justify-end) ' +
        `with distinct classes; got className="${node.className}"`,
    ).toContain('justify-end');
  });

  test('frontend-messageitem-other', () => {
    render(<MessageItem message={message(sceneId, 0, alice, 'Hi')} isOwn={false} />);
    const node = screen.getByTestId('message-item');
    expect(
      node.className,
      'frontend-messageitem-other: isOwn=false must left-align (justify-start); ' +
        `got className="${node.className}"`,
    ).toContain('justify-start');
  });

  test('frontend-messageitem-sender', () => {
    render(<MessageItem message={message(sceneId, 0, alice, 'Hi')} isOwn={false} />);
    expect(
      screen.queryByText('Alice'),
      'frontend-messageitem-sender: sender.name must render above the body',
    ).toBeInTheDocument();
  });

  test('frontend-messageitem-data', () => {
    render(<MessageItem message={message(sceneId, 7, alice, 'Hi')} isOwn={false} />);
    const node = screen.getByTestId('message-item');
    expect(
      node.getAttribute('data-scene-id'),
      'frontend-messageitem-data: data-scene-id must equal message.scene_id',
    ).toBe('parlor');
    expect(
      node.getAttribute('data-index'),
      'frontend-messageitem-data: data-index must equal message.index ' +
        '(serialized as string in the DOM)',
    ).toBe('7');
    expect(
      node.getAttribute('data-sender-id'),
      'frontend-messageitem-data: data-sender-id must equal message.sender.id',
    ).toBe('alice');
  });
});
