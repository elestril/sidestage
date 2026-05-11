/**
 * Sanity-tier test for SceneEntityPanel.
 *
 * .tests: frontend-sceneentitypanel-list, frontend-sceneentitypanel-header
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { asEntityId, type CharacterResponse, type EntityId, type SceneResponse } from '../types_ext';
import { SceneEntityPanel } from './SceneEntityPanel';

const character = (id: string, name: string): CharacterResponse =>
  ({
    id: asEntityId(id),
    name,
    type: 'character',
    body: '',
    owner: 'user',
  } as CharacterResponse);

const sceneEntity = (sceneId: EntityId): SceneResponse => ({
  type: 'scene',
  id: sceneId,
  name: 'Parlor',
  body: '',
  character_ids: [asEntityId('alice'), asEntityId('bob')],
  player_character_ids: [asEntityId('alice')],
});

describe('SceneEntityPanel', () => {
  test('frontend-sceneentitypanel-list', () => {
    const alice = character('alice', 'Alice');
    const bob = character('bob', 'Bob');
    const sceneId = asEntityId('parlor');
    const messages = [
      { scene_id: sceneId, index: 0, sender: alice, body: 'Hi' },
      { scene_id: sceneId, index: 1, sender: bob, body: '*nods quietly*' },
    ];
    render(
      <SceneEntityPanel
        campaignId="Test Campaign"
        entity={sceneEntity(sceneId)}
        entityCache={new Map([[alice.id, alice], [bob.id, bob]])}
        playerCharacterIds={[alice.id]}
        messages={messages}
        connected={true}
      />,
    );

    expect(
      screen.queryByText('Hi'),
      'frontend-sceneentitypanel-list: every message body must render ' +
        'inside the MessageList; alice\'s "Hi" was not found',
    ).toBeInTheDocument();
    expect(
      screen.queryByText('*nods quietly*'),
      'frontend-sceneentitypanel-list: every message body must render ' +
        'inside the MessageList; bob\'s reply was not found',
    ).toBeInTheDocument();
  });

  test('frontend-sceneentitypanel-header', () => {
    const alice = character('alice', 'Alice');
    const sceneId = asEntityId('parlor');
    render(
      <SceneEntityPanel
        campaignId="Test Campaign"
        entity={sceneEntity(sceneId)}
        entityCache={new Map([[alice.id, alice]])}
        playerCharacterIds={[alice.id]}
        messages={[]}
        connected={false}
      />,
    );

    expect(
      screen.queryByLabelText('disconnected'),
      'frontend-sceneentitypanel-header: the connection indicator must ' +
        'reflect `connected`; expected aria-label="disconnected" when false',
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Parlor'),
      'frontend-sceneentitypanel-header: the scene name must render in ' +
        'the panel header',
    ).toBeInTheDocument();
  });
});
