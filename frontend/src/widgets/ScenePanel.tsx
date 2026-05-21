// frontend-sceneentitypanel: ScenePanel widget (entity panel for `scene`).
//
// Reads its own data via the EntityRegistry. Does NOT receive
// `entityCache` / `playerCharacterIds` / `messages` / `connected` as
// props — those come from the cached entity and from `useConnected()`.

import { useConnected, useEntityRegistry } from '../hooks/useEntity';
import { useSendMessage } from '../hooks/useSendMessage';
import type { CachedScene } from '../entityRegistry';
import { MessageInput } from '../components/MessageInput';
import { MessageList } from '../components/MessageList';

export interface ScenePanelProps {
  entity: CachedScene;
}

export function ScenePanel({ entity }: ScenePanelProps) {
  const registry = useEntityRegistry();
  const connected = useConnected();
  const senderId = entity.player_character_ids[0] ?? null;
  const { send } = useSendMessage({
    campaignId: registry.campaignId,
    sceneId: entity.id,
    senderId,
  });

  const onSend = async (body: string): Promise<void> => {
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
        <MessageList
          messages={entity.messages}
          playerCharacterIds={entity.player_character_ids}
        />
      </main>
      <footer className="border-t border-slate-200 bg-white p-2">
        <MessageInput connected={connected} onSend={onSend} />
      </footer>
    </div>
  );
}
