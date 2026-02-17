import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithContext, type MockRoute } from './test-helpers';
import { MockWebSocket } from './__mocks__/MockWebSocket';
import type { EventModel, Entity, Scene } from './types';

// Mock Tiptap modules (EntityBrowser.tsx imports them at module level)
vi.mock('@tiptap/react', () => ({
  useEditor: () => null,
  EditorContent: () => <div data-testid="mock-editor" />,
}));
vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/extension-placeholder', () => ({
  default: { configure: () => ({}) },
}));

// Must import after vi.mock calls (vitest hoists them)
import { ChatWidget } from './ChatWidget';

const makeMessage = (overrides: Partial<EventModel> = {}): EventModel => ({
  id: 'msg-1',
  event_type: 'ChatMessage',
  scene_id: 'campaign_planning',
  gametime: 0,
  walltime: '2024-01-01T00:00:00Z',
  body: 'Hello world',
  metadata: {},
  visibility: 'public',
  name: '',
  ...overrides,
});

const makeEntity = (overrides: Partial<Entity> = {}): Entity => ({
  id: 'char-1',
  name: 'Aria',
  body: 'A brave warrior',
  type: 'Character',
  ...overrides,
});

const defaultScene: Scene = {
  id: 'campaign_planning',
  name: 'Campaign Planning',
  body: 'Planning session',
  current_gametime: 90061, // Day 1, 01:01:01
  events: [],
};

const renderChat = (options: {
  messages?: EventModel[];
  entities?: Entity[];
  scenes?: Scene[];
  extraFetchOverrides?: Record<string, MockRoute>;
} = {}) => {
  const {
    messages = [],
    entities = [],
    scenes = [defaultScene],
    extraFetchOverrides = {},
  } = options;

  return renderWithContext(<ChatWidget />, {
    fetchOverrides: {
      '/v1/scenes': { body: scenes },
      '/v1/entities': { body: entities },
      '/v1/scenes/campaign_planning/messages': { body: messages },
      ...extraFetchOverrides,
    },
  });
};

describe('ChatWidget', () => {
  it('renders message bubbles for each message in context', async () => {
    renderChat({
      messages: [
        makeMessage({ id: 'msg-1', body: 'First message' }),
        makeMessage({ id: 'msg-2', body: 'Second message' }),
      ],
    });

    await waitFor(() => {
      expect(screen.getByText('First message')).toBeInTheDocument();
      expect(screen.getByText('Second message')).toBeInTheDocument();
    });
  });

  it('user messages (actor_id=user) have right-aligned purple styling', async () => {
    renderChat({
      messages: [makeMessage({ actor_id: 'user', body: 'User says hello' })],
    });

    await waitFor(() => {
      const msgText = screen.getByText('User says hello');
      const bubble = msgText.closest('[class*="bg-[#bb86fc]"]');
      expect(bubble).toBeInTheDocument();
      expect(bubble).toHaveClass('text-black');
    });
  });

  it('NPC messages show character name header', async () => {
    renderChat({
      messages: [makeMessage({ character_id: 'char-1', actor_id: 'npc', body: 'Greetings' })],
      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
    });

    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
      expect(screen.getByText('Greetings')).toBeInTheDocument();
    });
  });

  it('NPC messages for unseen characters show "(Unseen)" badge', async () => {
    renderChat({
      messages: [makeMessage({ character_id: 'char-2', actor_id: 'npc', body: 'Hidden message' })],
      entities: [makeEntity({ id: 'char-2', name: 'Shadow', unseen: true })],
    });

    await waitFor(() => {
      expect(screen.getByText('(Unseen)')).toBeInTheDocument();
      // Unseen messages get dashed teal border
      const bubble = screen.getByText('Hidden message').closest('[class*="border-dashed"]');
      expect(bubble).toBeInTheDocument();
    });
  });

  it('JoinEvent renders as centered system text', async () => {
    renderChat({
      messages: [makeMessage({ event_type: 'JoinEvent', body: 'Aria joined the scene' })],
    });

    await waitFor(() => {
      const el = screen.getByText('Aria joined the scene');
      expect(el).toHaveClass('text-center', 'italic');
    });
  });

  it('LeaveEvent renders as centered system text', async () => {
    renderChat({
      messages: [makeMessage({ event_type: 'LeaveEvent', body: 'Aria left the scene' })],
    });

    await waitFor(() => {
      const el = screen.getByText('Aria left the scene');
      expect(el).toHaveClass('text-center', 'italic');
    });
  });

  it('AdjustGametime renders as centered system text', async () => {
    renderChat({
      messages: [makeMessage({ event_type: 'AdjustGametime', body: 'Time advanced 2 hours' })],
    });

    await waitFor(() => {
      const el = screen.getByText('Time advanced 2 hours');
      expect(el).toHaveClass('text-center', 'italic');
    });
  });

  it('Error event renders with red border and error styling', async () => {
    renderChat({
      messages: [makeMessage({ event_type: 'Error', body: 'Something went wrong' })],
    });

    await waitFor(() => {
      expect(screen.getByText('Error')).toBeInTheDocument();
      const errorContainer = screen.getByText('Error').closest('[class*="border-red-700"]');
      expect(errorContainer).toBeInTheDocument();
    });
  });

  it('message body is rendered through marked (HTML output)', async () => {
    renderChat({
      messages: [makeMessage({ body: 'Hello **bold**' })],
    });

    await waitFor(() => {
      // The marked mock wraps content in <p> tags
      const textEl = screen.getByText('Hello **bold**');
      expect(textEl.tagName).toBe('P');
    });
  });

  it('thinking indicator (bouncing dots) appears for actors in thinkingActors set', async () => {
    const { mockWebSocket } = renderChat({
      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
    });

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'actor_status',
        character_id: 'char-1',
        scene_id: 'campaign_planning',
        status: 'thinking',
      });
    });

    await waitFor(() => {
      const dots = document.querySelectorAll('.animate-bounce');
      expect(dots.length).toBe(3);
    });
  });

  it('thinking indicator shows character name', async () => {
    const { mockWebSocket } = renderChat({
      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
    });

    act(() => {
      mockWebSocket.simulateMessage({
        type: 'actor_status',
        character_id: 'char-1',
        scene_id: 'campaign_planning',
        status: 'thinking',
      });
    });

    await waitFor(() => {
      // The thinking indicator shows the character name above the dots
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });
  });

  it('form submit calls sendMessage with input text', async () => {
    renderChat();
    const user = userEvent.setup();

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Hello there{Enter}');

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/chat', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'Hello there', scene_id: 'campaign_planning' }),
      }));
    });
  });

  it('input clears after successful submit', async () => {
    renderChat();
    const user = userEvent.setup();

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Hello there{Enter}');

    await waitFor(() => {
      expect(input).toHaveValue('');
    });
  });

  it('empty/whitespace-only input does not trigger sendMessage', async () => {
    renderChat();
    const user = userEvent.setup();

    const input = screen.getByPlaceholderText('Type your message...');
    // Type just spaces and hit enter
    await user.type(input, '   {Enter}');

    // The fetch to /v1/chat should NOT have been called
    const chatCalls = vi.mocked(globalThis.fetch).mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('/v1/chat')
    );
    expect(chatCalls).toHaveLength(0);
  });

  it('send button is disabled when input is empty', async () => {
    const { container } = renderChat();
    const submitButton = container.querySelector('form button[type="submit"]');
    expect(submitButton).toBeDisabled();
  });

  it('entity widget renders when metadata.widget.type === entity', async () => {
    renderChat({
      messages: [makeMessage({
        body: 'Found something',
        metadata: {
          widget: { type: 'entity', id: 'char-1', entity_type: 'Character', name: 'Aria', description: 'A warrior' },
        },
      })],
      entities: [makeEntity()],
    });

    await waitFor(() => {
      expect(screen.getByText('A warrior')).toBeInTheDocument();
    });
  });

  it('entity widget shows entity type, name, and description', async () => {
    renderChat({
      messages: [makeMessage({
        body: 'Discovered entity',
        metadata: {
          widget: { type: 'entity', id: 'loc-1', entity_type: 'Location', name: 'Tavern', description: 'A cozy place' },
        },
      })],
    });

    await waitFor(() => {
      expect(screen.getByText('Location')).toBeInTheDocument();
      expect(screen.getByText('Tavern')).toBeInTheDocument();
      expect(screen.getByText('A cozy place')).toBeInTheDocument();
    });
  });

  it('clicking entity widget opens EntityModal (sets selectedEntityId)', async () => {
    renderChat({
      messages: [makeMessage({
        body: 'Found entity',
        metadata: {
          widget: { type: 'entity', id: 'char-1', entity_type: 'Character', name: 'Aria', description: 'A warrior' },
        },
      })],
      entities: [makeEntity({ id: 'char-1', name: 'Aria' })],
      extraFetchOverrides: {
        '/v1/entities/char-1/markdown': { body: { markdown: '# Aria\nA brave warrior' } },
      },
    });

    const user = userEvent.setup();

    // Wait for the widget to appear, then click it
    await waitFor(() => {
      expect(screen.getByText('A warrior')).toBeInTheDocument();
    });

    const widgetCard = screen.getByText('A warrior').closest('[class*="cursor-pointer"]')!;
    await user.click(widgetCard);

    // EntityModal should render with the entity name in an h2
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Aria');
    });
  });

  it('gametime displays as "Day N, HH:MM:SS" format', async () => {
    renderChat({ scenes: [defaultScene] }); // current_gametime = 90061

    await waitFor(() => {
      expect(screen.getByText('Day 1, 01:01:01')).toBeInTheDocument();
    });
  });

  it('null gametime renders empty string', async () => {
    const { container } = renderChat({
      scenes: [{ ...defaultScene, current_gametime: null }],
    });

    await waitFor(() => {
      // The gametime span should exist but have empty content
      const gametimeSpan = container.querySelector('.font-mono.text-xs');
      expect(gametimeSpan).toBeInTheDocument();
      expect(gametimeSpan).toHaveTextContent('');
    });
  });
});
