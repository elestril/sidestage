Now I have all the context needed. Let me generate the section content.

# Section 02: Frontend Mocks

## Overview

This section creates the testing utilities that all frontend component tests depend on: the `MockWebSocket` class, fetch mock helpers, the `renderWithContext` test helper, and the `marked` mock setup. These are the shared building blocks registered in the Vitest setup file and imported by test files.

**Depends on:** Section 01 (Vitest Infrastructure) -- assumes Vitest is configured with `globals: true`, `environment: 'jsdom'`, `setupFiles: './src/test-setup.ts'`, and that `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, and `jsdom` are installed as devDependencies.

**Blocks:** Section 03 (Component Tests) -- all component tests import the utilities defined here.

## Files to Create

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/frontend/src/__mocks__/MockWebSocket.ts` | Mock WebSocket class with test helpers |
| `/home/harald/src/sidestage/frontend/src/test-helpers.tsx` | `renderWithContext` helper and fetch mock utilities |

## File to Modify

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/frontend/src/test-setup.ts` | Register global mocks (WebSocket, fetch, marked), cleanup hooks |

---

## Tests First

All tests go in `/home/harald/src/sidestage/frontend/src/__mocks__/MockWebSocket.test.ts` and `/home/harald/src/sidestage/frontend/src/test-helpers.test.tsx`.

### MockWebSocket Tests

Create `/home/harald/src/sidestage/frontend/src/__mocks__/MockWebSocket.test.ts`:

```typescript
import { MockWebSocket } from './MockWebSocket';

describe('MockWebSocket', () => {
  it('constructor stores URL and protocol', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws', 'test-protocol');
    expect(ws.url).toBe('ws://localhost/v1/ws');
    expect(ws.protocol).toBe('test-protocol');
  });

  it('send() records sent messages', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    ws.send('hello');
    ws.send('world');
    expect(ws.sentMessages).toEqual(['hello', 'world']);
  });

  it('close() sets readyState to CLOSED', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    ws.close();
    expect(ws.readyState).toBe(WebSocket.CLOSED);
  });

  it('simulateOpen() calls onopen handler and sets readyState to OPEN', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    const onopen = vi.fn();
    ws.onopen = onopen;
    ws.simulateOpen();
    expect(ws.readyState).toBe(WebSocket.OPEN);
    expect(onopen).toHaveBeenCalled();
  });

  it('simulateMessage(data) calls onmessage with MessageEvent containing data', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    const onmessage = vi.fn();
    ws.onmessage = onmessage;
    ws.simulateOpen();
    ws.simulateMessage({ type: 'entities_updated' });
    expect(onmessage).toHaveBeenCalledWith(
      expect.objectContaining({
        data: JSON.stringify({ type: 'entities_updated' }),
      })
    );
  });

  it('simulateClose() calls onclose handler', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    const onclose = vi.fn();
    ws.onclose = onclose;
    ws.simulateOpen();
    ws.simulateClose();
    expect(onclose).toHaveBeenCalled();
  });

  it('multiple listeners via addEventListener work', () => {
    const ws = new MockWebSocket('ws://localhost/v1/ws');
    const listener1 = vi.fn();
    const listener2 = vi.fn();
    ws.addEventListener('message', listener1);
    ws.addEventListener('message', listener2);
    ws.simulateOpen();
    ws.simulateMessage({ test: true });
    expect(listener1).toHaveBeenCalled();
    expect(listener2).toHaveBeenCalled();
  });
});
```

### renderWithContext and Fetch Mock Tests

Create `/home/harald/src/sidestage/frontend/src/test-helpers.test.tsx`:

```typescript
import { screen, waitFor } from '@testing-library/react';
import { renderWithContext, mockFetchResponses } from './test-helpers';
import { MockWebSocket } from './__mocks__/MockWebSocket';

describe('mockFetchResponses', () => {
  it('fetch mock intercepts calls and returns configured responses', async () => {
    mockFetchResponses({
      '/v1/entities': { body: [{ id: 'e1', name: 'Test' }] },
    });
    const res = await fetch('/v1/entities');
    const data = await res.json();
    expect(data).toEqual([{ id: 'e1', name: 'Test' }]);
  });

  it('fetch mock can match by URL path', async () => {
    mockFetchResponses({
      '/v1/scenes': { body: [{ id: 's1', name: 'Scene 1' }] },
      '/v1/entities': { body: [] },
    });
    const scenesRes = await fetch('/v1/scenes');
    const scenes = await scenesRes.json();
    expect(scenes).toHaveLength(1);

    const entitiesRes = await fetch('/v1/entities');
    const entities = await entitiesRes.json();
    expect(entities).toHaveLength(0);
  });

  it('unmocked fetch calls return a clear error response', async () => {
    mockFetchResponses({});
    const res = await fetch('/v1/unknown');
    expect(res.ok).toBe(false);
    expect(res.status).toBe(404);
  });
});

describe('renderWithContext', () => {
  it('wraps component in AppProvider', () => {
    renderWithContext(<div data-testid="child">Hello</div>);
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('pre-mocks mount-time fetches (/v1/scenes, /v1/entities, /v1/tracing/status)', async () => {
    // renderWithContext sets up default mocks for all three endpoints plus messages
    renderWithContext(<div>Test</div>);
    // If mount-time fetches were not mocked, AppProvider would throw or console.error
    await waitFor(() => {
      // Verify fetch was called for mount-time endpoints
      expect(globalThis.fetch).toHaveBeenCalled();
    });
  });

  it('creates MockWebSocket and auto-opens it', async () => {
    renderWithContext(<div>Test</div>);
    // The last MockWebSocket instance should have been opened
    const instance = MockWebSocket.lastInstance;
    expect(instance).toBeDefined();
    expect(instance!.readyState).toBe(WebSocket.OPEN);
  });

  it('custom mock data can be passed to override defaults', async () => {
    // Override the default scenes response
    renderWithContext(<div>Test</div>, {
      fetchOverrides: {
        '/v1/scenes': { body: [{ id: 'custom', name: 'Custom Scene' }] },
      },
    });
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });
  });
});
```

---

## Implementation Details

### 1. MockWebSocket Class

Create `/home/harald/src/sidestage/frontend/src/__mocks__/MockWebSocket.ts`.

This class mimics the browser `WebSocket` API surface used by `AppContext.tsx`. The AppContext code uses:
- `new WebSocket(url)` -- constructor
- `s.onopen`, `s.onmessage`, `s.onclose` -- event handler properties
- `socket.readyState === WebSocket.OPEN` -- readyState check
- `socket.send(JSON.stringify(data))` -- sending messages
- `s.close()` -- cleanup on unmount

The mock must support all of these, plus test helpers for simulating server-side events.

Key design points:

- **Static `lastInstance`** property: After construction, store `this` on `MockWebSocket.lastInstance`. This allows `renderWithContext` and tests to access the most recently created WebSocket instance to call `simulateOpen()`, `simulateMessage()`, etc.
- **Static `instances`** array: Track all created instances (useful for tests that verify WebSocket creation count or need to access specific instances).
- **`sentMessages`** array: Records all data passed to `send()` for assertion.
- **`readyState`**: Starts as `WebSocket.CONNECTING` (0), set to `OPEN` (1) on `simulateOpen()`, set to `CLOSED` (3) on `close()` or `simulateClose()`.
- **Event handler properties**: `onopen`, `onmessage`, `onclose`, `onerror` -- nullable function properties, exactly like the real WebSocket.
- **`addEventListener` / `removeEventListener`**: Support for `addEventListener('message', fn)` style listeners in addition to `onmessage = fn` style. Use an internal `Map<string, Set<Function>>` for listener storage.

Test helper methods:

- **`simulateOpen()`**: Set `readyState = WebSocket.OPEN`, call `onopen` handler, dispatch to `'open'` addEventListener listeners.
- **`simulateMessage(data: unknown)`**: JSON-stringify `data`, create a `MessageEvent` (or a plain object with `data` property if `MessageEvent` constructor is problematic in jsdom), call `onmessage`, dispatch to `'message'` listeners.
- **`simulateClose(code?: number, reason?: string)`**: Set `readyState = WebSocket.CLOSED`, call `onclose`, dispatch to `'close'` listeners.

Static reset method:

- **`static reset()`**: Clear `instances` array and `lastInstance`. Called in `afterEach` (via test-setup.ts) to prevent cross-test pollution.

The class should also define the standard WebSocket constants: `CONNECTING = 0`, `OPEN = 1`, `CLOSING = 2`, `CLOSED = 3`.

### 2. Fetch Mock Helpers

Create the `mockFetchResponses` utility in `/home/harald/src/sidestage/frontend/src/test-helpers.tsx`.

The frontend code uses bare path fetches like `fetch('/v1/entities')`. In jsdom, these resolve to `http://localhost/v1/entities`. The mock must match against URL paths.

**`mockFetchResponses(routes: Record<string, MockRoute>)`** function:

```typescript
interface MockRoute {
  body?: unknown;
  status?: number;
  ok?: boolean;
  headers?: Record<string, string>;
}
```

This function calls `vi.spyOn(globalThis, 'fetch')` and sets up a `mockImplementation` that:

1. Extracts the pathname from the URL argument (handles both string URLs and `Request` objects).
2. Checks each key in `routes` to see if the pathname starts with or matches the key. Use `pathname.startsWith(key)` or exact match -- try exact match first, then prefix match, to allow both `/v1/entities` (exact) and `/v1/entities/` (prefix for `/v1/entities/{id}/markdown`).
3. If a match is found, return a `Response`-like object: `{ ok: route.ok ?? true, status: route.status ?? 200, json: async () => route.body, text: async () => JSON.stringify(route.body) }`.
4. If no match, return `{ ok: false, status: 404, json: async () => ({ error: 'Not mocked' }), text: async () => 'Not mocked' }`.

The function should also support a wildcard/catch-all mechanism -- a special key `'*'` that matches any unmatched path. This is useful for the default setup.

### 3. renderWithContext Helper

Also in `/home/harald/src/sidestage/frontend/src/test-helpers.tsx`.

**Purpose:** Wrap a component in `<AppProvider>` with all mount-time side effects properly mocked, so individual component tests do not need to repeat this boilerplate.

**Signature:**
```typescript
function renderWithContext(
  ui: React.ReactElement,
  options?: {
    fetchOverrides?: Record<string, MockRoute>;
  }
): RenderResult & { mockWebSocket: MockWebSocket }
```

**Behavior:**

1. Set up default fetch mocks for all mount-time calls:
   - `/v1/scenes` -> `[]` (empty scenes array)
   - `/v1/entities` -> `[]` (empty entities array)
   - `/v1/tracing/status` -> `{}` (no tracing error)
   - `/v1/scenes/campaign_planning/messages` -> `[]` (empty messages for default scene)
   - Any other `/v1/` path -> `{}` (catch-all for safety)

2. Merge in any `fetchOverrides` from options (override keys replace defaults).

3. Call `mockFetchResponses(mergedRoutes)`.

4. Call `render(<AppProvider>{ui}</AppProvider>)` using `@testing-library/react`'s `render`.

5. After render, get the `MockWebSocket.lastInstance` and call `simulateOpen()` on it. This triggers the `onopen` handler in `AppContext.tsx` which sets `socket` state, enabling WebSocket-dependent functionality.

6. Return the render result plus a `mockWebSocket` property pointing to the `MockWebSocket.lastInstance`.

**Important notes:**

- The `AppProvider` component is defined in `/home/harald/src/sidestage/frontend/src/AppContext.tsx`. It triggers side effects immediately on mount (the `useEffect` at line 127-134 calls `loadScenes()`, `loadEntities()`, and fetches tracing status). These must be mocked BEFORE `render()` is called.
- The WebSocket connection is created in a separate `useEffect` (line 140-194) that depends on `currentSceneId`. The default scene ID is `'campaign_planning'`.
- `renderWithContext` does NOT wrap in a Router. Tests for routed components (App.test.tsx, Layout.test.tsx) need to add their own `MemoryRouter` wrapper -- that is handled in Section 03.

### 4. test-setup.ts Updates

Modify `/home/harald/src/sidestage/frontend/src/test-setup.ts` (created in Section 01 with basic jest-dom matchers and cleanup).

Add the following to the setup file:

**Global WebSocket mock:**
```typescript
import { MockWebSocket } from './__mocks__/MockWebSocket';
// Replace globalThis.WebSocket with MockWebSocket
globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
```

This is done at the module level so that every test file has `WebSocket` pointing to `MockWebSocket` before any component code runs.

**Global fetch mock:**
```typescript
// Set up a default no-op fetch mock that returns empty responses
// Individual tests and renderWithContext will override this
beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => '{}',
  } as Response));
});
```

This prevents unmocked fetches from hitting the network. Tests that need specific responses use `mockFetchResponses()` or direct `vi.spyOn` calls.

**Mock cleanup:**
```typescript
afterEach(() => {
  vi.restoreAllMocks();
  MockWebSocket.reset();
});
```

This ensures fetch mocks and WebSocket state do not leak between tests.

**marked configuration:**
The `marked` library (v17) is used in `ChatWidget.tsx` and `App.tsx` via `marked.parse(content) as string`. In jsdom tests, `marked.parse()` may return a `Promise` depending on configuration. Add a mock to ensure synchronous behavior:

```typescript
vi.mock('marked', () => ({
  marked: {
    parse: (content: string) => `<p>${content}</p>`,
    use: vi.fn(),
  },
}));
```

This simple mock avoids pulling in the full marked library in tests. It wraps content in `<p>` tags to simulate basic HTML output (enough for assertions like "content is rendered as HTML, not raw markdown"). Tests that need more realistic markdown rendering can override this mock in their specific test file.

---

## Interaction Between Components

The relationship between these utilities:

1. **test-setup.ts** runs before every test file. It globally replaces `WebSocket` with `MockWebSocket`, sets up a default fetch mock, mocks `marked`, and registers cleanup hooks.

2. **mockFetchResponses()** is called either directly by tests that need fine-grained control, or indirectly through `renderWithContext()`.

3. **renderWithContext()** is the primary entry point for component tests. It handles the complex setup needed to render any component that uses `useAppContext()` (which is almost every component in the app).

4. **MockWebSocket** instances are created by the `AppContext.tsx` code during render (via `new WebSocket(...)` in useEffect). The test helper finds the instance via `MockWebSocket.lastInstance` and opens it to complete the connection handshake.

## WebSocket Message Types Reference

For writing tests that simulate server messages, here are the WebSocket message types used by `AppContext.tsx` (from `/home/harald/src/sidestage/frontend/src/types.ts`):

- `{ type: 'entities_updated' }` -- triggers `loadEntities()` re-fetch
- `{ type: 'event', event: EventModel, scene_id: string }` -- adds message to chat if scene matches
- `{ type: 'actor_status', character_id: string, scene_id: string, status: 'thinking' | 'idle' }` -- updates thinking indicators
- `{ type: 'scene_updated' }` -- triggers `loadScenes()` re-fetch
- `{ type: 'entity_content_sync', entity_id: string, body: string }` -- notifies sync listeners

These types are important context for Section 03 (Component Tests) but are documented here because the `MockWebSocket.simulateMessage()` method is what makes testing them possible.