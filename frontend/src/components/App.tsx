import { useSSE } from '../hooks/useSSE';
import { useSendMessage } from '../hooks/useSendMessage';
import { ChatView } from './ChatView';

/**
 * frontend-app: root component.
 *
 * SPEC NOTE: spec line 122 (`frontend-app-mount: Calls useWebSocket('/ws')`)
 * is stale — the current architecture is REST + SSE per
 * `frontend-sse-client-dataflow`. We use `useSSE` here.
 */
export function App() {
  const { messages, playerCharacterIds, campaignId, sceneId, connected } = useSSE();

  // Today the user sends as the first player character in the scene.
  const senderId = playerCharacterIds[0] ?? null;
  const { send } = useSendMessage({ campaignId, sceneId, senderId });

  const onSend = async (body: string) => {
    try {
      await send(body);
    } catch (err) {
      console.error('Send failed', err);
    }
  };

  return (
    <ChatView
      messages={messages}
      playerCharacterIds={playerCharacterIds}
      connected={connected}
      onSend={onSend}
    />
  );
}
