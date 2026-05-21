import { useEffect, useRef } from 'react';
import { useEntity } from '../hooks/useEntity';
import type { EntityId, MessageModel } from '../types_ext';
import { MessageItem } from './MessageItem';

export interface MessageListProps {
  messages: MessageModel[];
  playerCharacterIds: EntityId[];
}

interface MessageRowProps {
  message: MessageModel;
  isOwn: boolean;
}

/**
 * frontend-messagelist-row: per-message container.
 *
 * Resolves the sender via `useEntity(message.sender_id)`; refcount lives
 * with this component's lifetime in the registry. When the sender hasn't
 * been hydrated yet the row renders null (skeleton); the next render
 * after hydration fills the slot.
 */
function MessageRow({ message, isOwn }: MessageRowProps) {
  const { entity: sender } = useEntity(message.sender_id);
  if (!sender || sender.type !== 'character') return null;
  return (
    <MessageItem
      message={{
        scene_id: message.scene_id,
        index: message.index,
        sender,
        body: message.body,
      }}
      isOwn={isOwn}
    />
  );
}

/**
 * frontend-messagelist:
 * - frontend-messagelist-scroll: scrolls to the bottom whenever `messages` grows.
 * - frontend-messagelist-items: renders one MessageItem per message; keyed by
 *   the composite `(scene_id, index)` so React reconciliation stays stable
 *   even when slices arrive out of order.
 */
export function MessageList({ messages, playerCharacterIds }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const lastLengthRef = useRef<number>(0);

  useEffect(() => {
    if (messages.length > lastLengthRef.current) {
      const el = scrollRef.current;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }
    lastLengthRef.current = messages.length;
  }, [messages.length]);

  const ownIds = new Set<string>(playerCharacterIds as unknown as string[]);

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-3">
      <ul data-testid="message-list" className="flex flex-col gap-2">
        {messages.map((m) => (
          <MessageRow
            key={`${m.scene_id}:${m.index}`}
            message={m}
            isOwn={ownIds.has(m.sender_id as unknown as string)}
          />
        ))}
      </ul>
    </div>
  );
}
