export interface Entity {
  id: string;
  name: string;
  body: string;
  type: string;
  entity_type?: string;
  location_id?: string | null;
  inventory?: string[];
  connected_locations?: string[];
}

export interface Scene {
  id: string;
  name: string;
  body: string;
  current_gametime: number | null;
  events: string[];
  messages: Message[];
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatMessageBroadcast {
  type: 'chat_message';
  text: string;
  sender: 'user' | 'agent';
  scene_id: string;
  widget?: any;
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

export type WebSocketMessage = ChatMessageBroadcast | EntitiesUpdatedBroadcast | SceneUpdatedBroadcast | EntityContentSyncBroadcast;
