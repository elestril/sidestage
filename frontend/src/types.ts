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
  messages: ChatMessage[];
}

export interface ChatMessage {
  id: string;
  actor_id: string;
  character_id: string;
  message: string;
  scene_id: string;
  gametime: number;
  walltime: string;
  widget?: any;
}

export interface ChatMessageBroadcast {
  type: 'chat_message';
  message: ChatMessage;
  scene_id: string;
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

export interface TraceStartedBroadcast {
  type: 'trace_started';
  trace_id: string;
  scene_id: string | null;
  event_type: string | null;
  start_time_ms: number;
}

export type SpanCompletedBroadcast = { type: 'span_completed' } & TraceSpan;

export interface TraceCompletedBroadcast {
  type: 'trace_completed';
  trace_id: string;
  scene_id: string | null;
  duration_ms: number;
}

export type TraceWebSocketMessage = TraceStartedBroadcast | SpanCompletedBroadcast | TraceCompletedBroadcast;

export type WebSocketMessage = ChatMessageBroadcast | EntitiesUpdatedBroadcast | SceneUpdatedBroadcast | EntityContentSyncBroadcast | TraceStartedBroadcast | SpanCompletedBroadcast | TraceCompletedBroadcast;

// --- Tracing types ---

export interface SpanEvent {
  name: string;
  timestamp_ms: number;
  attributes: Record<string, string | number | boolean>;
}

export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  start_time_ms: number;
  end_time_ms: number;
  duration_ms: number;
  status: { code: string; description?: string | null };
  attributes: Record<string, string | number | boolean>;
  events: SpanEvent[];
  scene_id?: string | null;
  event_id?: string | null;
}

export interface TraceSummary {
  trace_id: string;
  scene_id: string | null;
  event_id: string | null;
  event_type: string | null;
  start_time_ms: number;
  end_time_ms: number;
  duration_ms: number;
  span_count: number;
  root_span_name: string | null;
}

export interface TracingStatus {
  enabled: boolean;
  config: {
    capture_prompts: boolean;
    capture_tool_args: boolean;
    capture_memory_content: boolean;
  };
  trace_count: number;
}
