// frontend-entity-registry tests: ref-counting, WS hydration, delta
// application, entity_action ack/error round-trip.
//
// Drives `EntityRegistry` with an injected WS factory so the tests
// exercise the registry's behaviour without a real socket. Phase 2b:
// hydration is fully WS-driven (the `subscribed` reply carries each
// entity's initial state); there are no REST fetches to mock.

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

interface Harness {
  registry: EntityRegistry;
  sockets: FakeWebSocket[];
}

function makeHarness(): Harness {
  const sockets: FakeWebSocket[] = [];
  const wsFactory = (url: string): WebSocket => {
    const ws = new FakeWebSocket(url);
    sockets.push(ws);
    return ws as unknown as WebSocket;
  };
  const registry = new EntityRegistry('Test Campaign', { wsFactory });
  return { registry, sockets };
}

// Drive microtasks until the predicate is true or `tries` is exhausted.
async function waitFor(pred: () => boolean, tries = 50): Promise<void> {
  for (let i = 0; i < tries; i += 1) {
    if (pred()) return;
    await Promise.resolve();
  }
  if (!pred()) throw new Error('waitFor: predicate never became true');
}

// Helper: parse the last subscribe frame's request_id off a fake socket.
function lastSubscribeRequestId(ws: FakeWebSocket): string {
  const frames = ws.sent
    .map((s) => JSON.parse(s) as { op: string; request_id?: string })
    .filter((f) => f.op === 'subscribe');
  const last = frames[frames.length - 1];
  if (!last?.request_id) throw new Error('no subscribe frame on socket');
  return last.request_id;
}

describe('EntityRegistry', () => {
  it('hydrates a scene from the `subscribed` reply and sends a subscribe frame', async () => {
    const { registry, sockets } = makeHarness();

    const eid = asEntityId('parlor');
    expect(registry.peek(eid)).toBeNull();

    const notified = vi.fn();
    const release = registry.observe(eid, notified);
    sockets[0].fireOpen();

    // ws-dataflow-subscribe: subscribe frame went out with entity_ids + request_id.
    const subscribeFrames = sockets[0].sent
      .map((s) => JSON.parse(s) as { op: string })
      .filter((f) => f.op === 'subscribe');
    expect(subscribeFrames).toHaveLength(1);
    const request_id = lastSubscribeRequestId(sockets[0]);
    expect(JSON.parse(sockets[0].sent[0])).toEqual({
      op: 'subscribe',
      entity_ids: ['parlor'],
      request_id,
    });

    // Server replies with the initial state inline (no REST roundtrip).
    sockets[0].fireMessage({
      op: 'subscribed',
      request_id,
      states: [
        {
          entity_id: 'parlor',
          model: {
            type: 'scene',
            id: 'parlor',
            name: 'Parlor',
            body: '',
            character_ids: ['alice'],
            messages: [{ sender_id: 'alice', body: 'hi' }],
          },
        },
      ],
    });

    await waitFor(() => registry.peek(eid) !== null);
    expect(notified).toHaveBeenCalled();

    const snapshot = registry.peek(eid);
    if (!snapshot || snapshot.type !== 'scene') throw new Error('expected scene');
    expect(snapshot.messages).toHaveLength(1);
    expect(snapshot.messages[0]).toMatchObject({
      sender_id: 'alice',
      body: 'hi',
      // Synthesised positionally — wire shape carries neither.
      scene_id: 'parlor',
      index: 0,
    });
    // Phase-1 player_character_ids stub: first character_id.
    expect(snapshot.player_character_ids).toEqual(['alice']);

    release();
    registry.close();
  });

  it('applies a ListDelta append (-1) on entity_changed[messages]', async () => {
    const { registry, sockets } = makeHarness();

    const eid = asEntityId('parlor');
    const release = registry.observe(eid, () => {});
    sockets[0].fireOpen();
    const request_id = lastSubscribeRequestId(sockets[0]);
    sockets[0].fireMessage({
      op: 'subscribed',
      request_id,
      states: [
        {
          entity_id: 'parlor',
          model: {
            type: 'scene',
            id: 'parlor',
            name: 'Parlor',
            body: '',
            character_ids: [],
            messages: [{ sender_id: 'alice', body: 'hi' }],
          },
        },
      ],
    });
    await waitFor(() => {
      const s = registry.peek(eid);
      return !!s && s.type === 'scene' && s.messages.length === 1;
    });

    // Append-at-end: start === -1.
    sockets[0].fireMessage({
      op: 'entity_changed',
      entity_id: 'parlor',
      attributes: ['messages'],
      deltas: {
        messages: {
          start: -1,
          len: 0,
          items: [{ sender_id: 'bob', body: 'reply' }],
        },
      },
    });
    await waitFor(() => {
      const s = registry.peek(eid);
      return !!s && s.type === 'scene' && s.messages.length === 2;
    });
    const snapshot = registry.peek(eid);
    if (!snapshot || snapshot.type !== 'scene') throw new Error('expected scene');
    expect(snapshot.messages.map((m) => m.body)).toEqual(['hi', 'reply']);
    expect(snapshot.messages.map((m) => m.index)).toEqual([0, 1]);
    expect(snapshot.messages[1].scene_id).toBe(eid);

    release();
    registry.close();
  });

  it('applies a ListDelta replace mid-list on entity_changed[messages]', async () => {
    const { registry, sockets } = makeHarness();

    const eid = asEntityId('parlor');
    const release = registry.observe(eid, () => {});
    sockets[0].fireOpen();
    const request_id = lastSubscribeRequestId(sockets[0]);
    sockets[0].fireMessage({
      op: 'subscribed',
      request_id,
      states: [
        {
          entity_id: 'parlor',
          model: {
            type: 'scene',
            id: 'parlor',
            name: 'Parlor',
            body: '',
            character_ids: [],
            messages: [
              { sender_id: 'alice', body: 'one' },
              { sender_id: 'alice', body: 'two' },
              { sender_id: 'alice', body: 'three' },
            ],
          },
        },
      ],
    });
    await waitFor(() => {
      const s = registry.peek(eid);
      return !!s && s.type === 'scene' && s.messages.length === 3;
    });

    // Replace the middle item: splice(1, 1, [...]).
    sockets[0].fireMessage({
      op: 'entity_changed',
      entity_id: 'parlor',
      attributes: ['messages'],
      deltas: {
        messages: {
          start: 1,
          len: 1,
          items: [{ sender_id: 'bob', body: 'TWO-PRIME' }],
        },
      },
    });
    await waitFor(() => {
      const s = registry.peek(eid);
      return (
        !!s && s.type === 'scene' && s.messages[1]?.body === 'TWO-PRIME'
      );
    });
    const snapshot = registry.peek(eid);
    if (!snapshot || snapshot.type !== 'scene') throw new Error('expected scene');
    expect(snapshot.messages.map((m) => m.body)).toEqual([
      'one',
      'TWO-PRIME',
      'three',
    ]);
    // Indexes re-stamped after the splice so positional keys stay monotonic.
    expect(snapshot.messages.map((m) => m.index)).toEqual([0, 1, 2]);

    release();
    registry.close();
  });

  it('ref-counts observers and sends unsubscribe on last release', async () => {
    const { registry, sockets } = makeHarness();

    const eid = asEntityId('alice');
    const release1 = registry.observe(eid, () => {});
    const release2 = registry.observe(eid, () => {});
    sockets[0].fireOpen();
    const request_id = lastSubscribeRequestId(sockets[0]);
    sockets[0].fireMessage({
      op: 'subscribed',
      request_id,
      states: [
        {
          entity_id: 'alice',
          model: {
            type: 'character',
            id: 'alice',
            name: 'Alice',
            body: '',
            owner: 'user',
          },
        },
      ],
    });
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
      entity_ids: ['alice'],
    });

    registry.close();
  });

  it('entityAction resolves on matching ack', async () => {
    const { registry, sockets } = makeHarness();
    sockets[0].fireOpen();

    const eid = asEntityId('alice');
    const result = registry.entityAction(eid, 'say', {
      scene_id: 'parlor',
      body: 'Hi',
    });

    // The most recent frame is the entity_action; pick the request_id back off.
    const sent = sockets[0].sent
      .map((s) => JSON.parse(s) as { op: string; request_id?: string })
      .filter((f) => f.op === 'entity_action');
    expect(sent).toHaveLength(1);
    const request_id = sent[0].request_id!;
    expect(JSON.parse(sockets[0].sent[sockets[0].sent.length - 1])).toEqual({
      op: 'entity_action',
      entity_id: 'alice',
      action: 'say',
      kwargs: { scene_id: 'parlor', body: 'Hi' },
      request_id,
    });

    sockets[0].fireMessage({ op: 'ack', request_id });
    await expect(result).resolves.toBeUndefined();

    registry.close();
  });

  it('entityAction rejects on matching error frame', async () => {
    const { registry, sockets } = makeHarness();
    sockets[0].fireOpen();

    const eid = asEntityId('alice');
    const result = registry.entityAction(eid, 'say', {
      scene_id: 'parlor',
      body: 'Hi',
    });

    const sent = sockets[0].sent
      .map((s) => JSON.parse(s) as { op: string; request_id?: string })
      .filter((f) => f.op === 'entity_action');
    const request_id = sent[0].request_id!;
    sockets[0].fireMessage({
      op: 'error',
      request_id,
      code: 'action_failed',
      message: 'boom',
    });
    await expect(result).rejects.toThrow(/action_failed.*boom/);

    registry.close();
  });

  it('entityAction rejects when the socket is not open', async () => {
    const { registry, sockets } = makeHarness();
    // Do NOT open the socket — the ready state stays at 0.

    const eid = asEntityId('alice');
    await expect(
      registry.entityAction(eid, 'say', { scene_id: 'parlor', body: 'Hi' }),
    ).rejects.toThrow(/socket not open/);
    // Nothing was queued onto the socket either.
    expect(sockets[0].sent.find((s) => s.includes('entity_action'))).toBeUndefined();

    registry.close();
  });
});
