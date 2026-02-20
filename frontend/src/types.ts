export interface Entity {
  id: string;
  name: string;
  body: string;
  type: string;
  entity_type?: string;
  location_id?: string | null;
  inventory?: string[];
  connected_locations?: string[];
  unseen?: boolean;
}

export interface Scene {
  id: string;
  name: string;
  body: string;
  current_gametime: number | null;
  events: string[];
  character_ids: string[];
}

export type EventType = 'ChatMessage' | 'JoinEvent' | 'LeaveEvent' | 'AdjustGametime' | 'Error';

export interface EventModel {
  id: string;
  event_type: EventType;
  scene_id: string;
  gametime: number;
  walltime: string;
  character_id?: string;
  actor_id?: string;
  body: string;
  metadata: Record<string, any>;
  visibility: 'public' | 'gm_only' | 'private';
  name: string;
}

export interface EventBroadcast {
  type: 'event';
  event: EventModel;
  scene_id: string;
}

export interface ActorStatusMessage {
  type: 'actor_status';
  character_id: string;
  scene_id: string;
  status: 'thinking' | 'idle';
}

export interface EntitiesUpdatedBroadcast {
  type: 'entities_updated';
}

export interface SceneUpdatedBroadcast {
  type: 'scene_updated';
}

export interface EntityContentSyncBroadcast {
  type: 'entity_content_sync';
  entity_id: string;
  body: string;
}

export type WebSocketMessage = EventBroadcast | ActorStatusMessage | EntitiesUpdatedBroadcast | SceneUpdatedBroadcast | EntityContentSyncBroadcast;
