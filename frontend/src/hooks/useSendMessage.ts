import { useCallback } from 'react';
import {
  asEntityId,
  type EntityId,
  type MessageAccepted,
  type MessageRequest,
} from '../types_ext';

export interface UseSendMessageArgs {
  campaignId: string | null;
  sceneId: EntityId | null;
  senderId: EntityId | null;
}

export interface UseSendMessageResult {
  send: (body: string) => Promise<MessageAccepted | null>;
}

/**
 * frontend-usesendmessage:
 * - frontend-send-hook-posts: POSTs MessageRequest to
 *   /api/campaigns/{campaignId}/scenes/{sceneId}/messages.
 * - frontend-send-hook-returns: exposes send(body) -> Promise<MessageAccepted|null>.
 *   The `MessageAccepted` carries the composite `(scene_id, index)` identity
 *   assigned by the server.
 *
 * The optimistic append (frontend-send-hook-optimistic) is intentionally
 * NOT done here: the server SSE-broadcasts an `entity_changed` for the
 * user's own POST, and useSSE's slice fetch picks it up. Doing both would
 * double-render. If a future spec change requires optimism for latency
 * reasons, plumb a setMessages callback through.
 */
export function useSendMessage({
  campaignId,
  sceneId,
  senderId,
}: UseSendMessageArgs): UseSendMessageResult {
  const send = useCallback(
    async (body: string): Promise<MessageAccepted | null> => {
      if (!campaignId || !sceneId || !senderId) return null;
      const trimmed = body.trim();
      if (!trimmed) return null;
      const req: MessageRequest = { sender_id: senderId, body: trimmed };
      const res = await fetch(
        `/api/campaigns/${encodeURIComponent(campaignId)}/scenes/${encodeURIComponent(sceneId)}/messages`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(req),
        },
      );
      if (!res.ok) {
        throw new Error(`POST message → ${res.status}`);
      }
      const accepted = (await res.json()) as { scene_id: string; index: number };
      return {
        scene_id: asEntityId(accepted.scene_id),
        index: accepted.index,
      };
    },
    [campaignId, sceneId, senderId],
  );

  return { send };
}
