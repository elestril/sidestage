import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../hooks/useSSE';
import type { EntityId } from '../types_ext';
import { MessageItem } from './MessageItem';

export interface MessageListProps {
  messages: ChatMessage[];
  playerCharacterIds: EntityId[];
}

/**
 * frontend-messagelist:
 * - frontend-messagelist-scroll: scrolls to the bottom whenever `messages` grows.
 * - frontend-messagelist-items: renders one MessageItem per message.
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
      <ul className="flex flex-col gap-2">
        {messages.map((m, i) => (
          <MessageItem
            key={i}
            message={m}
            isOwn={ownIds.has(m.sender.id as unknown as string)}
          />
        ))}
      </ul>
    </div>
  );
}
