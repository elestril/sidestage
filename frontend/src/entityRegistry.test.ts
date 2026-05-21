// frontend-entity-registry tests: ref-counting, hydration, slice fetch.
//
// Drives `EntityRegistry` with injected fetch + WS factories so the
// tests exercise the registry's behaviour without a real socket.

import { describe, expect, it, vi } from 'vitest';
import { EntityRegistry } from './entityRegistry';
import { asEntityId } from './types_ext';

interface FakeWsListeners {
  open: Array<() => void>;
  message: Array<(ev: MessageEvent<string>) => void>;
  close: Array<() => void>;
  error: Array<() => void>;
}

class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 0;
  sent: string[] = [];
  url: string;
  private listeners: FakeWsListeners = {
    open: [],
    message: [],
    close: [],
    error: [],
  };

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: keyof FakeWsListeners, listener: any): void {
    this.listeners[type].push(listener);
  }

  send(text: string): void {
    this.sent.push(text);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    for (const l of this.listeners.close) l();
  }

  // Test helpers.
  fireOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    for (const l of this.listeners.open) l();
  }
  fireMessage(data: object | string): void {
    const text = typeof data === 'string' ? data : JSON.stringify(data);
    const ev = { data: text } as MessageEvent<string>;
    for (const l of this.listeners.message) l(ev);
  }
  fireClose(): void {
    this.readyState = FakeWebSocket.CLOSED;
    for (const l of this.listeners.close) l();
  }
}

(globalThis as any).WebSocket ??= FakeWebSocket;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

interface Harness {
  registry: EntityRegistry;
  fetchMock: ReturnType<typeof vi.fn>;
  sockets: FakeWebSocket[];
}

function makeHarness(): Harness {
  const fetchMock = vi.fn();
  const sockets: FakeWebSocket[] = [];
  const wsFactory = (url: string): WebSocket => {
    const ws = new FakeWebSocket(url);
    sockets.push(ws);
    return ws as unknown as WebSocket;
  };
  const registry = new EntityRegistry('Test Campaign', {
    fetcher: fetchMock as unknown as typeof fetch,
    wsFactory,
  });
  return { registry, fetchMock, sockets };
}

// Drive microtasks until the predicate is true or `tries` is exhausted.
async function waitFor(pred: () => boolean, tries = 50): Promise<void> {
  for (let i = 0; i < tries; i += 1) {
    if (pred()) return;
    await Promise.resolve();
  }
  if (!pred()) throw new Error('waitFor: predicate never became true');
}

describe('EntityRegistry', () => {
  it('hydrates a scene + history and sends a subscribe frame', async () => {
    const { registry, fetchMock, sockets } = makeHarness();
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/entities/parlor')) {
        return jsonResponse({
          type: 'scene',
          id: 'parlor',
          name: 'Parlor',
          body: '',
          character_ids: ['alice'],
          player_character_ids: ['alice'],
        });
      }
      if (url.includes('/scenes/parlor/messages')) {
        return jsonResponse([
          { scene_id: 'parlor', index: 0, sender_id: 'alice', body: 'hi' },
        ]);
      }
      if (url.endsWith('/entities/alice')) {
        return jsonResponse({
          type: 'character',
          id: 'alice',
          name: 'Alice',
          body: '',
          owner: 'user',
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    const eid = asEntityId('parlor');
    let snapshot = registry.peek(eid);
    expect(snapshot).toBeNull();

    const notified = vi.fn();
    const release = registry.observe(eid, notified);
    sockets[0].fireOpen();

    await waitFor(() => registry.peek(eid) !== null);

    // ws-dataflow-subscribe: subscribe frame went out.
    const subscribeFrames = sockets[0].sent.filter((s) =>
      s.includes('"subscribe"'),
    );
    expect(subscribeFrames.length).toBeGreaterThanOrEqual(1);
    expect(JSON.parse(subscribeFrames[0])).toEqual({
      op: 'subscribe',
      entity_id: 'parlor',
    });

    // Listener fired on hydration.
    expect(notified).toHaveBeenCalled();

    snapshot = registry.peek(eid);
    expect(snapshot).not.toBeNull();
    if (!snapshot || snapshot.type !== 'scene') throw new Error('expected scene');
    expect(snapshot.messages).toHaveLength(1);
    expect(snapshot.messages[0].body).toBe('hi');

    release();
    registry.close();
  });

  it('merges slice fetched on entity_changed[messages]', async () => {
    const { registry, fetchMock, sockets } = makeHarness();
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/entities/parlor')) {
        return jsonResponse({
          type: 'scene',
          id: 'parlor',
          name: 'Parlor',
          body: '',
          character_ids: [],
          player_character_ids: [],
        });
      }
      if (url.includes('/scenes/parlor/messages')) {
        if (url.includes('?from=')) {
          return jsonResponse([
            { scene_id: 'parlor', index: 1, sender_id: 'bob', body: 'reply' },
          ]);
        }
        return jsonResponse([
          { scene_id: 'parlor', index: 0, sender_id: 'alice', body: 'hi' },
        ]);
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    const eid = asEntityId('parlor');
    const release = registry.observe(eid, () => {});
    sockets[0].fireOpen();
    await waitFor(() => {
      const s = registry.peek(eid);
      return !!s && s.type === 'scene' && s.messages.length === 1;
    });

    sockets[0].fireMessage({
      op: 'entity_changed',
      entity_id: 'parlor',
      attributes: ['messages'],
    });
    await waitFor(() => {
      const s = registry.peek(eid);
      return !!s && s.type === 'scene' && s.messages.length === 2;
    });
    const snapshot = registry.peek(eid);
    if (!snapshot || snapshot.type !== 'scene') throw new Error('expected scene');
    expect(snapshot.messages.map((m) => m.body)).toEqual(['hi', 'reply']);

    release();
    registry.close();
  });

  it('ref-counts observers and sends unsubscribe on last release', async () => {
    const { registry, fetchMock, sockets } = makeHarness();
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/entities/alice')) {
        return jsonResponse({
          type: 'character',
          id: 'alice',
          name: 'Alice',
          body: '',
          owner: 'user',
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    const eid = asEntityId('alice');
    const release1 = registry.observe(eid, () => {});
    const release2 = registry.observe(eid, () => {});
    sockets[0].fireOpen();
    await waitFor(() => registry.peek(eid) !== null);

    // Only one subscribe frame even though two observers exist.
    const subscribeFrames = sockets[0].sent.filter((s) =>
      s.includes('"subscribe"'),
    );
    expect(subscribeFrames).toHaveLength(1);

    release1();
    expect(sockets[0].sent.find((s) => s.includes('"unsubscribe"'))).toBeUndefined();

    release2();
    const unsubFrame = sockets[0].sent.find((s) => s.includes('"unsubscribe"'));
    expect(unsubFrame).toBeTruthy();
    expect(JSON.parse(unsubFrame!)).toEqual({
      op: 'unsubscribe',
      entity_id: 'alice',
    });

    registry.close();
  });
});
