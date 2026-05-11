/**
 * Unit tests for `useEntity` invariants the browser test can't reliably
 * reproduce: 503 handling during LOADING, full-refetch on reconnect, and
 * slice-fetch serialization under concurrent `entity_changed` events.
 *
 * .tests: frontend-handles-api-503, frontend-be-consistency-on-reconnect,
 *         sse-client-event-serialized
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { asEntityId, type EntityId } from '../types_ext';
import { useEntity } from './useEntity';

interface FakeEventSource {
  url: string;
  listeners: Record<string, ((ev: unknown) => void)[]>;
  closed: boolean;
  addEventListener(name: string, fn: (ev: unknown) => void): void;
  close(): void;
  dispatch(name: string, data: string): void;
  fireOpen(): void;
  fireError(): void;
}

function makeFakeEventSourceFactory(): {
  factory: (url: string) => EventSource;
  sources: FakeEventSource[];
} {
  const sources: FakeEventSource[] = [];
  const factory = (url: string): EventSource => {
    const src: FakeEventSource = {
      url,
      listeners: {},
      closed: false,
      addEventListener(name, fn) {
        (this.listeners[name] ??= []).push(fn);
      },
      close() {
        this.closed = true;
      },
      dispatch(name, data) {
        for (const fn of this.listeners[name] ?? []) fn({ data });
      },
      fireOpen() {
        for (const fn of this.listeners['open'] ?? []) fn({});
      },
      fireError() {
        for (const fn of this.listeners['error'] ?? []) fn({});
      },
    };
    sources.push(src);
    return src as unknown as EventSource;
  };
  return { factory, sources };
}

interface JsonResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): JsonResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const CID = 'Test Campaign';
const SCENE_ID = 'parlor';
const sceneId = asEntityId(SCENE_ID);

const alice = {
  id: 'alice',
  name: 'Alice',
  type: 'character',
  body: '',
  owner: 'user',
};
const bob = {
  id: 'bob',
  name: 'Bob',
  type: 'character',
  body: '*nods quietly*',
  owner: 'stub',
};

const sceneResponse = {
  type: 'scene',
  id: SCENE_ID,
  name: 'Parlor',
  body: '',
  character_ids: ['alice', 'bob'],
  player_character_ids: ['alice'],
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useEntity', () => {
  test('frontend-handles-api-503', async () => {
    // While App.state == LOADING, /entities/{eid} returns 503. useEntity
    // must not crash; must keep `connected` false; must schedule a reconnect.
    const fetcher = vi.fn(async () =>
      jsonResponse({ detail: 'server loading' }, 503),
    );
    const { factory, sources } = makeFakeEventSourceFactory();

    const { result } = renderHook(() =>
      useEntity({
        campaignId: CID,
        entityId: sceneId,
        deps: {
          fetcher: fetcher as unknown as typeof fetch,
          eventSourceFactory: factory,
        },
      }),
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.connected, (
      'frontend-handles-api-503-indicator: connected stays false while ' +
        'bootstrap is retrying against a LOADING backend; ' +
        `got connected=${result.current.connected}`
    )).toBe(false);
    expect(sources.length, (
      'frontend-handles-api-503-no-crash: a 503 from /entities/{eid} ' +
        'must not open an SSE stream (bootstrap fails before subscribe); ' +
        `got sources=${sources.length}`
    )).toBe(0);

    const initialCalls = fetcher.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(fetcher.mock.calls.length, (
      'frontend-handles-api-503-retry: useEntity retries bootstrap after ' +
        'the initial 1s backoff; ' +
        `got call count ${fetcher.mock.calls.length} (was ${initialCalls})`
    )).toBeGreaterThan(initialCalls);

    const errorMock = vi.mocked(console.error);
    expect(errorMock.mock.calls.length, (
      'frontend-handles-api-503-no-crash: bootstrap failures MUST surface ' +
        'as console.error (not uncaught); ' +
        `got ${errorMock.mock.calls.length} error log(s)`
    )).toBeGreaterThan(0);
    expect(errorMock.mock.calls[0][0]).toBe('useEntity bootstrap failed');
    errorMock.mockClear();
  });

  test('frontend-be-consistency-on-reconnect', async () => {
    // On SSE drop + reconnect (backend restart with diverged state),
    // the bootstrap's full history fetch MUST overwrite `messages`
    // outright. Per-panel application of frontend-be-consistency-*:
    // a backend that lost runtime state must produce an empty UI.
    const historyResponses: unknown[] = [
      [{ scene_id: SCENE_ID, index: 0, sender_id: 'alice', body: 'Hi' }],
      [], // post-restart: backend lost runtime messages
    ];
    let historyIdx = 0;

    const fetcher = vi.fn(async (input: unknown) => {
      const url = typeof input === 'string' ? input : String(input);
      if (url.endsWith(`/entities/${SCENE_ID}`)) return jsonResponse(sceneResponse);
      if (url.endsWith('/entities/alice')) return jsonResponse(alice);
      if (url.endsWith('/entities/bob')) return jsonResponse(bob);
      if (url.includes(`/scenes/${SCENE_ID}/messages`) && !url.includes('from=')) {
        const r = historyResponses[historyIdx] ?? [];
        historyIdx += 1;
        return jsonResponse(r);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { factory, sources } = makeFakeEventSourceFactory();
    const { result } = renderHook(() =>
      useEntity({
        campaignId: CID,
        entityId: sceneId,
        deps: {
          fetcher: fetcher as unknown as typeof fetch,
          eventSourceFactory: factory,
        },
      }),
    );

    await act(async () => {
      for (let i = 0; i < 20; i += 1) await Promise.resolve();
    });
    expect(result.current.messages.length, (
      'frontend-be-consistency-messages-overwritten: first bootstrap MUST ' +
        'populate messages from the initial history fetch; ' +
        `got ${result.current.messages.length}`
    )).toBe(1);
    expect(sources.length).toBe(1);

    // Backend dies → SSE error → reconnect timer.
    act(() => {
      sources[0].fireError();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
      for (let i = 0; i < 20; i += 1) await Promise.resolve();
    });

    expect(sources.length, 'reconnect must open a new SSE source').toBe(2);
    expect(result.current.messages.length, (
      'frontend-be-consistency-event-loss: after reconnect against a ' +
        'backend that lost runtime state, the FULL history re-fetch MUST ' +
        'replace `messages` with the (empty) authoritative state; got ' +
        `${result.current.messages.length}: ${JSON.stringify(
          result.current.messages.map((m) => m.body),
        )}`
    )).toBe(0);
  });

  test('sse-client-event-serialized', async () => {
    // Two concurrent entity_changed events MUST NOT both fetch from the
    // same `from=N` and double-append. The promise chain serializes them.
    const sliceReplies: JsonResponse[] = [
      jsonResponse([
        { scene_id: SCENE_ID, index: 0, sender_id: 'alice', body: 'Hi' },
      ]),
      jsonResponse([
        { scene_id: SCENE_ID, index: 1, sender_id: 'bob', body: '*nods quietly*' },
      ]),
    ];
    let sliceIdx = 0;

    const fetcher = vi.fn(async (input: unknown) => {
      const url = typeof input === 'string' ? input : String(input);
      if (url.endsWith(`/entities/${SCENE_ID}`)) return jsonResponse(sceneResponse);
      if (url.endsWith('/entities/alice')) return jsonResponse(alice);
      if (url.endsWith('/entities/bob')) return jsonResponse(bob);
      if (url.includes(`/scenes/${SCENE_ID}/messages`) && !url.includes('from=')) {
        return jsonResponse([]);
      }
      if (url.includes(`/scenes/${SCENE_ID}/messages?from=`)) {
        const r = sliceReplies[sliceIdx];
        sliceIdx += 1;
        return r ?? jsonResponse([]);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { factory, sources } = makeFakeEventSourceFactory();
    const { result } = renderHook(() =>
      useEntity({
        campaignId: CID,
        entityId: sceneId,
        deps: {
          fetcher: fetcher as unknown as typeof fetch,
          eventSourceFactory: factory,
        },
      }),
    );

    await act(async () => {
      for (let i = 0; i < 20; i += 1) await Promise.resolve();
    });
    expect(sources.length, 'bootstrap must open exactly one SSE source').toBe(1);
    const src = sources[0];
    act(() => src.fireOpen());

    act(() => {
      src.dispatch(
        'entity_changed',
        JSON.stringify({ entity_id: SCENE_ID, attributes: ['messages'] }),
      );
      src.dispatch(
        'entity_changed',
        JSON.stringify({ entity_id: SCENE_ID, attributes: ['messages'] }),
      );
    });

    await act(async () => {
      for (let i = 0; i < 30; i += 1) await Promise.resolve();
    });

    const messages = result.current.messages;
    expect(messages.length, (
      'sse-client-event-serialized: two concurrent entity_changed events ' +
        'with overlapping slice ranges must result in deduped state — ' +
        'alice once at (parlor, 0), bob once at (parlor, 1); ' +
        `got ${messages.length} messages: ${JSON.stringify(
          messages.map((m) => ({ scene_id: m.scene_id, index: m.index })),
        )}`
    )).toBe(2);
    expect(messages[0].body).toBe('Hi');
    expect(messages[1].body).toBe('*nods quietly*');
  });
});

// Suppress the "no unused" lint warning for type imports kept for
// documentation only.
export type _Unused = EntityId;
