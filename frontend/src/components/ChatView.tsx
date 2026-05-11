import type { ChatMessage } from '../hooks/useSSE';
import type { EntityId } from '../types_ext';
import { MessageInput } from './MessageInput';
import { MessageList } from './MessageList';

export interface ChatViewProps {
  messages: ChatMessage[];
  playerCharacterIds: EntityId[];
  connected: boolean;
  onSend: (body: string) => void;
}

/**
 * frontend-chatview:
 * - frontend-chatview-list: renders MessageList with messages and playerCharacterIds.
 * - frontend-chatview-input: renders MessageInput with connected and onSend.
 */
export function ChatView({ messages, playerCharacterIds, connected, onSend }: ChatViewProps) {
  return (
    <div className="flex h-full flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700">
        Sidestage
        <span
          className={`ml-2 inline-block h-2 w-2 rounded-full ${
            connected ? 'bg-green-500' : 'bg-red-500'
          }`}
          aria-label={connected ? 'connected' : 'disconnected'}
        />
      </header>
      <main className="flex-1 overflow-hidden">
        <MessageList messages={messages} playerCharacterIds={playerCharacterIds} />
      </main>
      <footer className="border-t border-slate-200 bg-white p-2">
        <MessageInput connected={connected} onSend={onSend} />
      </footer>
    </div>
  );
}
