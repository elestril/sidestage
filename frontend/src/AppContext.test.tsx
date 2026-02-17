import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState, useEffect } from 'react';
import { renderWithContext } from './test-helpers';
import { useAppContext } from './AppContext';
import { MockWebSocket } from './__mocks__/MockWebSocket';

/**
 * Test harness that exposes AppContext state and actions via DOM elements.
 */
const TestConsumer = () => {
  const ctx = useAppContext();
  const [syncData, setSyncData] = useState('');

  useEffect(() => {
    return ctx.onSync((data: unknown) => setSyncData(JSON.stringify(data)));
  }, [ctx.onSync]);

  return (
    <div>
      <span data-testid="scenes-count">{ctx.scenes.length}</span>
      <span data-testid="entities-count">{ctx.entities.length}</span>
      <span data-testid="messages-count">{ctx.messages.length}</span>
      <span data-testid="current-scene">{ctx.currentSceneId}</span>
      <span data-testid="tracing-error">{ctx.tracingError ?? ''}</span>
      <span data-testid="thinking-actors">{JSON.stringify([...ctx.thinkingActors])}</span>
      <span data-testid="sync-data">{syncData}</span>
      {ctx.messages.map((m, i) => (
        <span key={i} data-testid={`msg-${i}`}>{m.body}</span>
      ))}
      <button data-testid="btn-send" onClick={() => ctx.sendMessage('test message')}>Send</button>
      <button data-testid="btn-save-md" onClick={() => ctx.saveEntityMarkdown('char-1', '# Test')}>SaveMD</button>
      <button data-testid="btn-save-entity" onClick={() => ctx.saveEntity('char-1', { name: 'Updated' })}>SaveEntity</button>
      <button data-testid="btn-change-scene" onClick={() => ctx.setCurrentSceneId('new_scene')}>ChangeScene</button>
    </div>
  );
};

describe('AppContext', () => {
  it('mount triggers fetch to /v1/scenes', async () => {
    renderWithContext(<TestConsumer />);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes');
    });
  });

  it('mount triggers fetch to /v1/entities', async () => {
    renderWithContext(<TestConsumer />);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities');
    });
  });

  it('mount triggers fetch to /v1/tracing/status', async () => {
    renderWithContext(<TestConsumer />);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/tracing/status');
    });
  });

  it('mount creates WebSocket connection to ws URL', () => {
    renderWithContext(<TestConsumer />);
    const ws = MockWebSocket.lastInstance;
    expect(ws).toBeDefined();
    expect(ws!.url).toContain('/v1/ws');
  });

  it('sendMessage() POSTs to /v1/chat with message and scene_id', async () => {
    renderWithContext(<TestConsumer />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('btn-send'));
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/chat', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'test message', scene_id: 'campaign_planning' }),
      }));
    });
  });

  it('saveEntityMarkdown() POSTs to /v1/entities/{id}/markdown', async () => {
    renderWithContext(<TestConsumer />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('btn-save-md'));
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities/char-1/markdown', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ markdown: '# Test' }),
      }));
    });
  });

  it('saveEntity() POSTs to /v1/entities/{id} with data', async () => {
    renderWithContext(<TestConsumer />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('btn-save-entity'));
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities/char-1', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Updated' }),
      }));
    });
  });

  it('WebSocket entities_updated message triggers loadEntities()', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);
    vi.mocked(globalThis.fetch).mockClear();

    act(() => {
      mockWebSocket.simulateMessage({ type: 'entities_updated' });
    });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities');
    });
  });

  it('WebSocket event message for current scene adds to messages state', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'event',
        scene_id: 'campaign_planning',
        event: {
          id: 'ev-1', event_type: 'ChatMessage', scene_id: 'campaign_planning',
          gametime: 0, walltime: '2024-01-01T00:00:00Z',
          body: 'Hello from WebSocket', metadata: {}, visibility: 'public', name: '',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('msg-0')).toHaveTextContent('Hello from WebSocket');
    });
  });

  it('WebSocket event message for different scene is ignored', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'event',
        scene_id: 'other_scene',
        event: {
          id: 'ev-2', event_type: 'ChatMessage', scene_id: 'other_scene',
          gametime: 0, walltime: '2024-01-01T00:00:00Z',
          body: 'Should not appear', metadata: {}, visibility: 'public', name: '',
        },
      });
    });

    // Messages count should remain 0
    expect(screen.getByTestId('messages-count')).toHaveTextContent('0');
  });

  it('WebSocket actor_status thinking adds to thinkingActors set', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'actor_status',
        character_id: 'char-1',
        scene_id: 'campaign_planning',
        status: 'thinking',
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('char-1');
    });
  });

  it('WebSocket actor_status idle removes from thinkingActors set', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);

    // Add thinking actor
    act(() => {
      mockWebSocket.simulateMessage({
        type: 'actor_status', character_id: 'char-1',
        scene_id: 'campaign_planning', status: 'thinking',
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('char-1');
    });

    // Remove by setting idle
    act(() => {
      mockWebSocket.simulateMessage({
        type: 'actor_status', character_id: 'char-1',
        scene_id: 'campaign_planning', status: 'idle',
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('[]');
    });
  });

  it('WebSocket scene_updated triggers loadScenes()', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);
    vi.mocked(globalThis.fetch).mockClear();

    act(() => {
      mockWebSocket.simulateMessage({ type: 'scene_updated' });
    });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes');
    });
  });

  it('WebSocket entity_content_sync notifies registered listeners', async () => {
    const { mockWebSocket } = renderWithContext(<TestConsumer />);

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'entity_content_sync',
        entity_id: 'char-1',
        body: 'Updated body',
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('sync-data')).toHaveTextContent('entity_content_sync');
    });
  });

  it('scene change triggers loadMessages for new scene', async () => {
    renderWithContext(<TestConsumer />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('btn-change-scene'));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes/new_scene/messages');
    });
  });

  it('tracingError state set when /v1/tracing/status returns error', async () => {
    renderWithContext(<TestConsumer />, {
      fetchOverrides: {
        '/v1/tracing/status': { body: { error: 'Tracing unavailable' } },
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId('tracing-error')).toHaveTextContent('Tracing unavailable');
    });
  });
});
