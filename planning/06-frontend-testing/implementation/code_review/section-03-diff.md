diff --git a/frontend/src/App.test.tsx b/frontend/src/App.test.tsx
new file mode 100644
index 0000000..a2a9f87
--- /dev/null
+++ b/frontend/src/App.test.tsx
@@ -0,0 +1,66 @@
+import { screen, waitFor } from '@testing-library/react';
+import { MemoryRouter } from 'react-router-dom';
+import { renderWithContext } from './test-helpers';
+
+// Mock Tiptap modules (ScenesPage/EntitiesPage render components that import Tiptap)
+vi.mock('@tiptap/react', () => ({
+  useEditor: () => null,
+  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
+}));
+vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
+vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
+vi.mock('@tiptap/extension-placeholder', () => ({
+  default: { configure: () => ({}) },
+}));
+
+import { AppContent } from './App';
+
+const defaultScenes = [
+  { id: 'campaign_planning', name: 'Campaign Planning', body: '', current_gametime: null, events: [] },
+  { id: 'tavern', name: 'Tavern', body: 'A warm place', current_gametime: null, events: [] },
+];
+
+describe('App', () => {
+  it('renders without crashing', () => {
+    renderWithContext(
+      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>
+        <AppContent />
+      </MemoryRouter>,
+      { fetchOverrides: { '/v1/scenes': { body: defaultScenes } } },
+    );
+    expect(screen.getByText('Sidestage')).toBeInTheDocument();
+  });
+
+  it('default route shows main view with ChatWidget', async () => {
+    renderWithContext(
+      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>
+        <AppContent />
+      </MemoryRouter>,
+      { fetchOverrides: { '/v1/scenes': { body: defaultScenes } } },
+    );
+
+    // The "/" route redirects to /scenes/campaign_planning which renders ScenesPage
+    await waitFor(() => {
+      expect(screen.getByPlaceholderText('Describe actions or speak as characters...')).toBeInTheDocument();
+    });
+  });
+
+  it('/sidestage/scenes/:sceneId route triggers load for that scene', async () => {
+    renderWithContext(
+      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/scenes/tavern']}>
+        <AppContent />
+      </MemoryRouter>,
+      {
+        fetchOverrides: {
+          '/v1/scenes': { body: defaultScenes },
+          '/v1/scenes/tavern/messages': { body: [] },
+        },
+      },
+    );
+
+    // ScenesPage sets currentSceneId to 'tavern', triggering message load
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes/tavern/messages');
+    });
+  });
+});
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index 0394fea..bd52bae 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -110,7 +110,7 @@ const EntitiesPage: React.FC = () => {
   );
 };
 
-const AppContent: React.FC = () => {
+export const AppContent: React.FC = () => {
   console.log('AppContent mounting...');
   return (
     <Layout>
diff --git a/frontend/src/AppContext.test.tsx b/frontend/src/AppContext.test.tsx
new file mode 100644
index 0000000..3c4d9b5
--- /dev/null
+++ b/frontend/src/AppContext.test.tsx
@@ -0,0 +1,250 @@
+import { screen, waitFor, act } from '@testing-library/react';
+import userEvent from '@testing-library/user-event';
+import { useState, useEffect } from 'react';
+import { renderWithContext } from './test-helpers';
+import { useAppContext } from './AppContext';
+import { MockWebSocket } from './__mocks__/MockWebSocket';
+
+/**
+ * Test harness that exposes AppContext state and actions via DOM elements.
+ */
+const TestConsumer = () => {
+  const ctx = useAppContext();
+  const [syncData, setSyncData] = useState('');
+
+  useEffect(() => {
+    return ctx.onSync((data: unknown) => setSyncData(JSON.stringify(data)));
+  }, [ctx.onSync]);
+
+  return (
+    <div>
+      <span data-testid="scenes-count">{ctx.scenes.length}</span>
+      <span data-testid="entities-count">{ctx.entities.length}</span>
+      <span data-testid="messages-count">{ctx.messages.length}</span>
+      <span data-testid="current-scene">{ctx.currentSceneId}</span>
+      <span data-testid="tracing-error">{ctx.tracingError ?? ''}</span>
+      <span data-testid="thinking-actors">{JSON.stringify([...ctx.thinkingActors])}</span>
+      <span data-testid="sync-data">{syncData}</span>
+      {ctx.messages.map((m, i) => (
+        <span key={i} data-testid={`msg-${i}`}>{m.body}</span>
+      ))}
+      <button data-testid="btn-send" onClick={() => ctx.sendMessage('test message')}>Send</button>
+      <button data-testid="btn-save-md" onClick={() => ctx.saveEntityMarkdown('char-1', '# Test')}>SaveMD</button>
+      <button data-testid="btn-save-entity" onClick={() => ctx.saveEntity('char-1', { name: 'Updated' })}>SaveEntity</button>
+      <button data-testid="btn-change-scene" onClick={() => ctx.setCurrentSceneId('new_scene')}>ChangeScene</button>
+    </div>
+  );
+};
+
+describe('AppContext', () => {
+  it('mount triggers fetch to /v1/scenes', async () => {
+    renderWithContext(<TestConsumer />);
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes');
+    });
+  });
+
+  it('mount triggers fetch to /v1/entities', async () => {
+    renderWithContext(<TestConsumer />);
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities');
+    });
+  });
+
+  it('mount triggers fetch to /v1/tracing/status', async () => {
+    renderWithContext(<TestConsumer />);
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/tracing/status');
+    });
+  });
+
+  it('mount creates WebSocket connection to ws URL', () => {
+    renderWithContext(<TestConsumer />);
+    const ws = MockWebSocket.lastInstance;
+    expect(ws).toBeDefined();
+    expect(ws!.url).toContain('/v1/ws');
+  });
+
+  it('sendMessage() POSTs to /v1/chat with message and scene_id', async () => {
+    renderWithContext(<TestConsumer />);
+    const user = userEvent.setup();
+    await user.click(screen.getByTestId('btn-send'));
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/chat', expect.objectContaining({
+        method: 'POST',
+        body: JSON.stringify({ message: 'test message', scene_id: 'campaign_planning' }),
+      }));
+    });
+  });
+
+  it('saveEntityMarkdown() POSTs to /v1/entities/{id}/markdown', async () => {
+    renderWithContext(<TestConsumer />);
+    const user = userEvent.setup();
+    await user.click(screen.getByTestId('btn-save-md'));
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities/char-1/markdown', expect.objectContaining({
+        method: 'POST',
+        body: JSON.stringify({ markdown: '# Test' }),
+      }));
+    });
+  });
+
+  it('saveEntity() POSTs to /v1/entities/{id} with data', async () => {
+    renderWithContext(<TestConsumer />);
+    const user = userEvent.setup();
+    await user.click(screen.getByTestId('btn-save-entity'));
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities/char-1', expect.objectContaining({
+        method: 'POST',
+        body: JSON.stringify({ name: 'Updated' }),
+      }));
+    });
+  });
+
+  it('WebSocket entities_updated message triggers loadEntities()', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+    vi.mocked(globalThis.fetch).mockClear();
+
+    act(() => {
+      mockWebSocket.simulateMessage({ type: 'entities_updated' });
+    });
+
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/entities');
+    });
+  });
+
+  it('WebSocket event message for current scene adds to messages state', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'event',
+        scene_id: 'campaign_planning',
+        event: {
+          id: 'ev-1', event_type: 'ChatMessage', scene_id: 'campaign_planning',
+          gametime: 0, walltime: '2024-01-01T00:00:00Z',
+          body: 'Hello from WebSocket', metadata: {}, visibility: 'public', name: '',
+        },
+      });
+    });
+
+    await waitFor(() => {
+      expect(screen.getByTestId('msg-0')).toHaveTextContent('Hello from WebSocket');
+    });
+  });
+
+  it('WebSocket event message for different scene is ignored', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'event',
+        scene_id: 'other_scene',
+        event: {
+          id: 'ev-2', event_type: 'ChatMessage', scene_id: 'other_scene',
+          gametime: 0, walltime: '2024-01-01T00:00:00Z',
+          body: 'Should not appear', metadata: {}, visibility: 'public', name: '',
+        },
+      });
+    });
+
+    // Messages count should remain 0
+    expect(screen.getByTestId('messages-count')).toHaveTextContent('0');
+  });
+
+  it('WebSocket actor_status thinking adds to thinkingActors set', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'actor_status',
+        character_id: 'char-1',
+        scene_id: 'campaign_planning',
+        status: 'thinking',
+      });
+    });
+
+    await waitFor(() => {
+      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('char-1');
+    });
+  });
+
+  it('WebSocket actor_status idle removes from thinkingActors set', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+
+    // Add thinking actor
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'actor_status', character_id: 'char-1',
+        scene_id: 'campaign_planning', status: 'thinking',
+      });
+    });
+    await waitFor(() => {
+      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('char-1');
+    });
+
+    // Remove by setting idle
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'actor_status', character_id: 'char-1',
+        scene_id: 'campaign_planning', status: 'idle',
+      });
+    });
+    await waitFor(() => {
+      expect(screen.getByTestId('thinking-actors')).toHaveTextContent('[]');
+    });
+  });
+
+  it('WebSocket scene_updated triggers loadScenes()', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+    vi.mocked(globalThis.fetch).mockClear();
+
+    act(() => {
+      mockWebSocket.simulateMessage({ type: 'scene_updated' });
+    });
+
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes');
+    });
+  });
+
+  it('WebSocket entity_content_sync notifies registered listeners', async () => {
+    const { mockWebSocket } = renderWithContext(<TestConsumer />);
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'entity_content_sync',
+        entity_id: 'char-1',
+        body: 'Updated body',
+      });
+    });
+
+    await waitFor(() => {
+      expect(screen.getByTestId('sync-data')).toHaveTextContent('entity_content_sync');
+    });
+  });
+
+  it('scene change triggers loadMessages for new scene', async () => {
+    renderWithContext(<TestConsumer />);
+
+    const user = userEvent.setup();
+    await user.click(screen.getByTestId('btn-change-scene'));
+
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes/new_scene/messages');
+    });
+  });
+
+  it('tracingError state set when /v1/tracing/status returns error', async () => {
+    renderWithContext(<TestConsumer />, {
+      fetchOverrides: {
+        '/v1/tracing/status': { body: { error: 'Tracing unavailable' } },
+      },
+    });
+
+    await waitFor(() => {
+      expect(screen.getByTestId('tracing-error')).toHaveTextContent('Tracing unavailable');
+    });
+  });
+});
diff --git a/frontend/src/ChatWidget.test.tsx b/frontend/src/ChatWidget.test.tsx
new file mode 100644
index 0000000..2383832
--- /dev/null
+++ b/frontend/src/ChatWidget.test.tsx
@@ -0,0 +1,355 @@
+import { screen, waitFor, act } from '@testing-library/react';
+import userEvent from '@testing-library/user-event';
+import { renderWithContext, type MockRoute } from './test-helpers';
+import { MockWebSocket } from './__mocks__/MockWebSocket';
+import type { EventModel, Entity, Scene } from './types';
+
+// Mock Tiptap modules (EntityBrowser.tsx imports them at module level)
+vi.mock('@tiptap/react', () => ({
+  useEditor: () => null,
+  EditorContent: () => <div data-testid="mock-editor" />,
+}));
+vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
+vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
+vi.mock('@tiptap/extension-placeholder', () => ({
+  default: { configure: () => ({}) },
+}));
+
+// Must import after vi.mock calls (vitest hoists them)
+import { ChatWidget } from './ChatWidget';
+
+const makeMessage = (overrides: Partial<EventModel> = {}): EventModel => ({
+  id: 'msg-1',
+  event_type: 'ChatMessage',
+  scene_id: 'campaign_planning',
+  gametime: 0,
+  walltime: '2024-01-01T00:00:00Z',
+  body: 'Hello world',
+  metadata: {},
+  visibility: 'public',
+  name: '',
+  ...overrides,
+});
+
+const makeEntity = (overrides: Partial<Entity> = {}): Entity => ({
+  id: 'char-1',
+  name: 'Aria',
+  body: 'A brave warrior',
+  type: 'Character',
+  ...overrides,
+});
+
+const defaultScene: Scene = {
+  id: 'campaign_planning',
+  name: 'Campaign Planning',
+  body: 'Planning session',
+  current_gametime: 90061, // Day 1, 01:01:01
+  events: [],
+};
+
+const renderChat = (options: {
+  messages?: EventModel[];
+  entities?: Entity[];
+  scenes?: Scene[];
+  extraFetchOverrides?: Record<string, MockRoute>;
+} = {}) => {
+  const {
+    messages = [],
+    entities = [],
+    scenes = [defaultScene],
+    extraFetchOverrides = {},
+  } = options;
+
+  return renderWithContext(<ChatWidget />, {
+    fetchOverrides: {
+      '/v1/scenes': { body: scenes },
+      '/v1/entities': { body: entities },
+      '/v1/scenes/campaign_planning/messages': { body: messages },
+      ...extraFetchOverrides,
+    },
+  });
+};
+
+describe('ChatWidget', () => {
+  it('renders message bubbles for each message in context', async () => {
+    renderChat({
+      messages: [
+        makeMessage({ id: 'msg-1', body: 'First message' }),
+        makeMessage({ id: 'msg-2', body: 'Second message' }),
+      ],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('First message')).toBeInTheDocument();
+      expect(screen.getByText('Second message')).toBeInTheDocument();
+    });
+  });
+
+  it('user messages (actor_id=user) have right-aligned purple styling', async () => {
+    renderChat({
+      messages: [makeMessage({ actor_id: 'user', body: 'User says hello' })],
+    });
+
+    await waitFor(() => {
+      const msgText = screen.getByText('User says hello');
+      const bubble = msgText.closest('[class*="bg-[#bb86fc]"]');
+      expect(bubble).toBeInTheDocument();
+      expect(bubble).toHaveClass('text-black');
+    });
+  });
+
+  it('NPC messages show character name header', async () => {
+    renderChat({
+      messages: [makeMessage({ character_id: 'char-1', actor_id: 'npc', body: 'Greetings' })],
+      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+      expect(screen.getByText('Greetings')).toBeInTheDocument();
+    });
+  });
+
+  it('NPC messages for unseen characters show "(Unseen)" badge', async () => {
+    renderChat({
+      messages: [makeMessage({ character_id: 'char-2', actor_id: 'npc', body: 'Hidden message' })],
+      entities: [makeEntity({ id: 'char-2', name: 'Shadow', unseen: true })],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('(Unseen)')).toBeInTheDocument();
+      // Unseen messages get dashed teal border
+      const bubble = screen.getByText('Hidden message').closest('[class*="border-dashed"]');
+      expect(bubble).toBeInTheDocument();
+    });
+  });
+
+  it('JoinEvent renders as centered system text', async () => {
+    renderChat({
+      messages: [makeMessage({ event_type: 'JoinEvent', body: 'Aria joined the scene' })],
+    });
+
+    await waitFor(() => {
+      const el = screen.getByText('Aria joined the scene');
+      expect(el).toHaveClass('text-center', 'italic');
+    });
+  });
+
+  it('LeaveEvent renders as centered system text', async () => {
+    renderChat({
+      messages: [makeMessage({ event_type: 'LeaveEvent', body: 'Aria left the scene' })],
+    });
+
+    await waitFor(() => {
+      const el = screen.getByText('Aria left the scene');
+      expect(el).toHaveClass('text-center', 'italic');
+    });
+  });
+
+  it('AdjustGametime renders as centered system text', async () => {
+    renderChat({
+      messages: [makeMessage({ event_type: 'AdjustGametime', body: 'Time advanced 2 hours' })],
+    });
+
+    await waitFor(() => {
+      const el = screen.getByText('Time advanced 2 hours');
+      expect(el).toHaveClass('text-center', 'italic');
+    });
+  });
+
+  it('Error event renders with red border and error styling', async () => {
+    renderChat({
+      messages: [makeMessage({ event_type: 'Error', body: 'Something went wrong' })],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('Error')).toBeInTheDocument();
+      const errorContainer = screen.getByText('Error').closest('[class*="border-red-700"]');
+      expect(errorContainer).toBeInTheDocument();
+    });
+  });
+
+  it('message body is rendered through marked (HTML output)', async () => {
+    renderChat({
+      messages: [makeMessage({ body: 'Hello **bold**' })],
+    });
+
+    await waitFor(() => {
+      // The marked mock wraps content in <p> tags
+      const textEl = screen.getByText('Hello **bold**');
+      expect(textEl.tagName).toBe('P');
+    });
+  });
+
+  it('thinking indicator (bouncing dots) appears for actors in thinkingActors set', async () => {
+    const { mockWebSocket } = renderChat({
+      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
+    });
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'actor_status',
+        character_id: 'char-1',
+        scene_id: 'campaign_planning',
+        status: 'thinking',
+      });
+    });
+
+    await waitFor(() => {
+      const dots = document.querySelectorAll('.animate-bounce');
+      expect(dots.length).toBe(3);
+    });
+  });
+
+  it('thinking indicator shows character name', async () => {
+    const { mockWebSocket } = renderChat({
+      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
+    });
+
+    act(() => {
+      mockWebSocket.simulateMessage({
+        type: 'actor_status',
+        character_id: 'char-1',
+        scene_id: 'campaign_planning',
+        status: 'thinking',
+      });
+    });
+
+    await waitFor(() => {
+      // The thinking indicator shows the character name above the dots
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+    });
+  });
+
+  it('form submit calls sendMessage with input text', async () => {
+    renderChat();
+    const user = userEvent.setup();
+
+    const input = screen.getByPlaceholderText('Type your message...');
+    await user.type(input, 'Hello there{Enter}');
+
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/chat', expect.objectContaining({
+        method: 'POST',
+        body: JSON.stringify({ message: 'Hello there', scene_id: 'campaign_planning' }),
+      }));
+    });
+  });
+
+  it('input clears after successful submit', async () => {
+    renderChat();
+    const user = userEvent.setup();
+
+    const input = screen.getByPlaceholderText('Type your message...');
+    await user.type(input, 'Hello there{Enter}');
+
+    await waitFor(() => {
+      expect(input).toHaveValue('');
+    });
+  });
+
+  it('empty/whitespace-only input does not trigger sendMessage', async () => {
+    renderChat();
+    const user = userEvent.setup();
+
+    const input = screen.getByPlaceholderText('Type your message...');
+    // Type just spaces and hit enter
+    await user.type(input, '   {Enter}');
+
+    // The fetch to /v1/chat should NOT have been called
+    const chatCalls = vi.mocked(globalThis.fetch).mock.calls.filter(
+      (c) => typeof c[0] === 'string' && c[0].includes('/v1/chat')
+    );
+    expect(chatCalls).toHaveLength(0);
+  });
+
+  it('send button is disabled when input is empty', async () => {
+    const { container } = renderChat();
+    const submitButton = container.querySelector('form button[type="submit"]');
+    expect(submitButton).toBeDisabled();
+  });
+
+  it('entity widget renders when metadata.widget.type === entity', async () => {
+    renderChat({
+      messages: [makeMessage({
+        body: 'Found something',
+        metadata: {
+          widget: { type: 'entity', id: 'char-1', entity_type: 'Character', name: 'Aria', description: 'A warrior' },
+        },
+      })],
+      entities: [makeEntity()],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('A warrior')).toBeInTheDocument();
+    });
+  });
+
+  it('entity widget shows entity type, name, and description', async () => {
+    renderChat({
+      messages: [makeMessage({
+        body: 'Discovered entity',
+        metadata: {
+          widget: { type: 'entity', id: 'loc-1', entity_type: 'Location', name: 'Tavern', description: 'A cozy place' },
+        },
+      })],
+    });
+
+    await waitFor(() => {
+      expect(screen.getByText('Location')).toBeInTheDocument();
+      expect(screen.getByText('Tavern')).toBeInTheDocument();
+      expect(screen.getByText('A cozy place')).toBeInTheDocument();
+    });
+  });
+
+  it('clicking entity widget opens EntityModal (sets selectedEntityId)', async () => {
+    renderChat({
+      messages: [makeMessage({
+        body: 'Found entity',
+        metadata: {
+          widget: { type: 'entity', id: 'char-1', entity_type: 'Character', name: 'Aria', description: 'A warrior' },
+        },
+      })],
+      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
+      extraFetchOverrides: {
+        '/v1/entities/char-1/markdown': { body: { markdown: '# Aria\nA brave warrior' } },
+      },
+    });
+
+    const user = userEvent.setup();
+
+    // Wait for the widget to appear, then click it
+    await waitFor(() => {
+      expect(screen.getByText('A warrior')).toBeInTheDocument();
+    });
+
+    const widgetCard = screen.getByText('A warrior').closest('[class*="cursor-pointer"]')!;
+    await user.click(widgetCard);
+
+    // EntityModal should render with the entity name in an h2
+    await waitFor(() => {
+      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Aria');
+    });
+  });
+
+  it('gametime displays as "Day N, HH:MM:SS" format', async () => {
+    renderChat({ scenes: [defaultScene] }); // current_gametime = 90061
+
+    await waitFor(() => {
+      expect(screen.getByText('Day 1, 01:01:01')).toBeInTheDocument();
+    });
+  });
+
+  it('null gametime renders empty string', async () => {
+    const { container } = renderChat({
+      scenes: [{ ...defaultScene, current_gametime: null }],
+    });
+
+    await waitFor(() => {
+      // The gametime span should exist but have empty content
+      const gametimeSpan = container.querySelector('.font-mono.text-xs');
+      expect(gametimeSpan).toBeInTheDocument();
+      expect(gametimeSpan).toHaveTextContent('');
+    });
+  });
+});
diff --git a/frontend/src/EntityBrowser.test.tsx b/frontend/src/EntityBrowser.test.tsx
new file mode 100644
index 0000000..0f2213d
--- /dev/null
+++ b/frontend/src/EntityBrowser.test.tsx
@@ -0,0 +1,140 @@
+import { screen, waitFor } from '@testing-library/react';
+import userEvent from '@testing-library/user-event';
+import { renderWithContext } from './test-helpers';
+import type { Entity } from './types';
+
+// Mock Tiptap modules that don't work in jsdom
+vi.mock('@tiptap/react', () => ({
+  useEditor: () => null,
+  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
+}));
+vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
+vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
+vi.mock('@tiptap/extension-placeholder', () => ({
+  default: { configure: () => ({}) },
+}));
+
+import { EntityBrowser, EntityModal } from './EntityBrowser';
+
+const makeEntity = (overrides: Partial<Entity> = {}): Entity => ({
+  id: 'char-1',
+  name: 'Aria',
+  body: 'A brave warrior',
+  type: 'Character',
+  ...overrides,
+});
+
+const testEntities: Entity[] = [
+  makeEntity({ id: 'char-1', name: 'Aria', type: 'Character' }),
+  makeEntity({ id: 'loc-1', name: 'Tavern', body: 'A cozy place', type: 'Location' }),
+  makeEntity({ id: 'item-1', name: 'Sword', body: 'A sharp blade', type: 'Item' }),
+];
+
+const renderBrowser = (entities: Entity[] = testEntities, selectedId: string | null = null) => {
+  const onSelect = vi.fn();
+  const result = renderWithContext(
+    <EntityBrowser selectedId={selectedId} onSelect={onSelect} />,
+    { fetchOverrides: { '/v1/entities': { body: entities } } },
+  );
+  return { ...result, onSelect };
+};
+
+describe('EntityBrowser', () => {
+  it('renders entity list from context', async () => {
+    renderBrowser();
+    await waitFor(() => {
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+      expect(screen.getByText('Tavern')).toBeInTheDocument();
+      expect(screen.getByText('Sword')).toBeInTheDocument();
+    });
+  });
+
+  it('entity type filter shows available types', async () => {
+    renderBrowser();
+    await waitFor(() => {
+      expect(screen.getByText('All')).toBeInTheDocument();
+      expect(screen.getByText('Characters')).toBeInTheDocument();
+      expect(screen.getByText('Locations')).toBeInTheDocument();
+      expect(screen.getByText('Items')).toBeInTheDocument();
+      expect(screen.getByText('Scenes')).toBeInTheDocument();
+    });
+  });
+
+  it('selecting a type filter updates displayed entities', async () => {
+    renderBrowser();
+    const user = userEvent.setup();
+
+    // Wait for entities to load
+    await waitFor(() => {
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+    });
+
+    // Click "Characters" filter
+    await user.click(screen.getByText('Characters'));
+
+    // Only Character entities should be visible
+    expect(screen.getByText('Aria')).toBeInTheDocument();
+    expect(screen.queryByText('Tavern')).not.toBeInTheDocument();
+    expect(screen.queryByText('Sword')).not.toBeInTheDocument();
+  });
+
+  it('clicking an entity selects it', async () => {
+    const { onSelect } = renderBrowser();
+    const user = userEvent.setup();
+
+    await waitFor(() => {
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+    });
+
+    await user.click(screen.getByText('Aria'));
+    expect(onSelect).toHaveBeenCalledWith('char-1');
+  });
+
+  it('EntityModal renders when entityId prop is set', async () => {
+    renderWithContext(
+      <EntityModal entityId="char-1" onClose={vi.fn()} />,
+      {
+        fetchOverrides: {
+          '/v1/entities': { body: [makeEntity({ id: 'char-1', name: 'Aria' })] },
+          '/v1/entities/char-1/markdown': { body: { markdown: '# Aria\nA warrior' } },
+        },
+      },
+    );
+
+    await waitFor(() => {
+      expect(screen.getByText('Aria')).toBeInTheDocument();
+    });
+    // Should show the markdown content
+    await waitFor(() => {
+      expect(screen.getByText(/# Aria/)).toBeInTheDocument();
+    });
+  });
+
+  it('EntityModal calls onClose when dismissed', async () => {
+    const onClose = vi.fn();
+    renderWithContext(
+      <EntityModal entityId="char-1" onClose={onClose} />,
+      {
+        fetchOverrides: {
+          '/v1/entities': { body: [makeEntity({ id: 'char-1', name: 'Aria' })] },
+          '/v1/entities/char-1/markdown': { body: { markdown: '# Aria' } },
+        },
+      },
+    );
+
+    const user = userEvent.setup();
+    await waitFor(() => {
+      expect(screen.getByText('Close')).toBeInTheDocument();
+    });
+    await user.click(screen.getByText('Close'));
+    expect(onClose).toHaveBeenCalled();
+  });
+
+  it('EntityModal returns null when entityId is null', () => {
+    const { container } = renderWithContext(
+      <EntityModal entityId={null} onClose={vi.fn()} />,
+    );
+    // No modal overlay should be rendered
+    expect(container.querySelector('.fixed')).toBeNull();
+  });
+});
diff --git a/frontend/src/Layout.test.tsx b/frontend/src/Layout.test.tsx
new file mode 100644
index 0000000..4883f52
--- /dev/null
+++ b/frontend/src/Layout.test.tsx
@@ -0,0 +1,61 @@
+import { screen, waitFor } from '@testing-library/react';
+import { MemoryRouter } from 'react-router-dom';
+import { renderWithContext } from './test-helpers';
+import { Layout } from './Layout';
+import type { Scene } from './types';
+
+const defaultScenes: Scene[] = [
+  { id: 'campaign_planning', name: 'Campaign Planning', body: '', current_gametime: null, events: [] },
+  { id: 'tavern', name: 'Tavern Scene', body: '', current_gametime: null, events: [] },
+];
+
+const renderLayout = (
+  initialPath = '/scenes/campaign_planning',
+  scenes: Scene[] = defaultScenes,
+) => {
+  return renderWithContext(
+    <MemoryRouter initialEntries={[initialPath]}>
+      <Layout><div data-testid="child-content">Page Content</div></Layout>
+    </MemoryRouter>,
+    { fetchOverrides: { '/v1/scenes': { body: scenes } } },
+  );
+};
+
+describe('Layout', () => {
+  it('header renders "Sidestage" title and nav links', async () => {
+    renderLayout();
+    expect(screen.getByText('Sidestage')).toBeInTheDocument();
+    // "Scenes" appears both as nav link and sidebar heading, so use role queries
+    expect(screen.getByRole('link', { name: /Scenes/ })).toBeInTheDocument();
+    expect(screen.getByRole('link', { name: /Entities/ })).toBeInTheDocument();
+  });
+
+  it('sidebar renders scene list from context', async () => {
+    renderLayout();
+    await waitFor(() => {
+      expect(screen.getByText('Campaign Planning')).toBeInTheDocument();
+      expect(screen.getByText('Tavern Scene')).toBeInTheDocument();
+    });
+  });
+
+  it('scene links navigate to correct URLs', async () => {
+    renderLayout();
+    await waitFor(() => {
+      expect(screen.getByText('Tavern Scene')).toBeInTheDocument();
+    });
+    const tavLink = screen.getByText('Tavern Scene').closest('a');
+    expect(tavLink).toHaveAttribute('href', '/scenes/tavern');
+  });
+
+  it('active scene is visually highlighted', async () => {
+    renderLayout('/scenes/campaign_planning');
+    await waitFor(() => {
+      expect(screen.getByText('Campaign Planning')).toBeInTheDocument();
+    });
+    const activeLink = screen.getByText('Campaign Planning').closest('a');
+    expect(activeLink).toHaveClass('bg-[#1e1e1e]');
+
+    const inactiveLink = screen.getByText('Tavern Scene').closest('a');
+    expect(inactiveLink).not.toHaveClass('bg-[#1e1e1e]');
+  });
+});
diff --git a/frontend/src/test-setup.ts b/frontend/src/test-setup.ts
index 42d54f8..c9d4933 100644
--- a/frontend/src/test-setup.ts
+++ b/frontend/src/test-setup.ts
@@ -8,6 +8,9 @@ import { MockWebSocket } from './__mocks__/MockWebSocket'
 // Replace globalThis.WebSocket with MockWebSocket
 globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
 
+// jsdom doesn't implement scrollIntoView
+Element.prototype.scrollIntoView = vi.fn()
+
 // Mock marked to avoid pulling in the full library in tests
 vi.mock('marked', () => ({
   marked: {
