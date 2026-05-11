// frontend-types-entityid: branded EntityId override.
// frontend-types-discriminated: discriminated server-event union.
//
// All app code imports from this module, NEVER from `./types` directly.

import type {
  CampaignResponse as _CampaignResponse,
  CharacterModel as _CharacterModel,
  EntityModel as _EntityModel,
  EntityType,
  MessageAccepted,
  MessageRequest as _MessageRequest,
  MessageModel as _MessageModel,
  SceneResponse as _SceneResponse,
  SceneUpdatedEvent,
} from './types';

// frontend-types-entityid: brand the opaque id types so they cannot be
// confused with arbitrary strings at the type level.
export type EntityId = string & { readonly _brand: 'EntityId' };
export type MessageId = string & { readonly _brand: 'MessageId' };

export type { EntityType, MessageAccepted, SceneUpdatedEvent };

export interface EntityModel extends Omit<_EntityModel, 'id'> {
  id: EntityId;
}

export interface CharacterModel extends Omit<_CharacterModel, 'id'> {
  id: EntityId;
}

export interface SceneResponse extends Omit<_SceneResponse, 'id' | 'character_ids' | 'player_character_ids'> {
  id: EntityId;
  character_ids: EntityId[];
  player_character_ids: EntityId[];
}

export interface CampaignResponse extends Omit<_CampaignResponse, 'default_scene_id'> {
  default_scene_id: EntityId | null;
}

export interface MessageModel extends Omit<_MessageModel, 'id' | 'sender_id'> {
  id: MessageId;
  sender_id: EntityId;
}

export interface MessageRequest extends Omit<_MessageRequest, 'sender_id'> {
  sender_id: EntityId;
}

// Helpers to coerce raw strings into branded ids at the trust boundary
// (i.e. when reading from the wire). After this, the type system enforces
// the brand throughout the app.
export const asEntityId = (s: string): EntityId => s as EntityId;
export const asMessageId = (s: string): MessageId => s as MessageId;

// frontend-types-discriminated: ServerEvent union for SSE event payloads.
// Today only one variant exists; the union is exhaustive on `type`.
export type ServerEvent = SceneUpdatedEvent & { type: 'scene_updated' };
