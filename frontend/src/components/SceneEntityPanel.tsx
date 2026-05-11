import type { ChatMessage } from '../hooks/useEntity';
import { useSendMessage } from '../hooks/useSendMessage';
import type { CharacterResponse, EntityId, SceneResponse } from '../types_ext';
import { MessageInput } from './MessageInput';
import { MessageList } from './MessageList';

export interface SceneEntityPanelProps {
  campaignId: string;
  entity: SceneResponse;
  entityCache: Map<EntityId, CharacterResponse>;
  playerCharacterIds: EntityId[];
  messages: ChatMessage[];
  connected: boolean;
}

/**
 * frontend-sceneentitypanel: scene header + chat below.
 *
 * - frontend-sceneentitypanel-header: name + connection indicator;
 *   body (when present) beneath the header.
 * - frontend-sceneentitypanel-list: MessageList with `messages` +
 *   `playerCharacterIds`.
 * - frontend-sceneentitypanel-input: MessageInput wired via
 *   useSendMessage(campaignId, entity.id, playerCharacterIds[0]).
 */
export function SceneEntityPanel({
  campaignId,
  entity,
  playerCharacterIds,
  messages,
  connected,
}: SceneEntityPanelProps) {
  const senderId = playerCharacterIds[0] ?? null;
  const { send } = useSendMessage({
    campaignId,
    sceneId: entity.id,
    senderId,
  });

  const onSend = async (body: string) => {
    try {
      await send(body);
    } catch (err) {
      console.error('Send failed', err);
    }
  };

  return (
    <div
      data-testid="scene-panel"
      data-entity-id={entity.id}
      className="flex h-full flex-col bg-slate-50"
    >
      <header className="border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center text-sm font-medium text-slate-700">
          {entity.name}
          <span
            className={`ml-2 inline-block h-2 w-2 rounded-full ${
              connected ? 'bg-green-500' : 'bg-red-500'
            }`}
            aria-label={connected ? 'connected' : 'disconnected'}
          />
        </div>
        {entity.body ? (
          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-500">
            {entity.body}
          </p>
        ) : null}
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
