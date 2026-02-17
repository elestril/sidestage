diff --git a/frontend/src/__mocks__/MockWebSocket.test.ts b/frontend/src/__mocks__/MockWebSocket.test.ts
new file mode 100644
index 0000000..a633e94
--- /dev/null
+++ b/frontend/src/__mocks__/MockWebSocket.test.ts
@@ -0,0 +1,65 @@
+import { MockWebSocket } from './MockWebSocket';
+
+describe('MockWebSocket', () => {
+  it('constructor stores URL and protocol', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws', 'test-protocol');
+    expect(ws.url).toBe('ws://localhost/v1/ws');
+    expect(ws.protocol).toBe('test-protocol');
+  });
+
+  it('send() records sent messages', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    ws.send('hello');
+    ws.send('world');
+    expect(ws.sentMessages).toEqual(['hello', 'world']);
+  });
+
+  it('close() sets readyState to CLOSED', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    ws.close();
+    expect(ws.readyState).toBe(WebSocket.CLOSED);
+  });
+
+  it('simulateOpen() calls onopen handler and sets readyState to OPEN', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    const onopen = vi.fn();
+    ws.onopen = onopen;
+    ws.simulateOpen();
+    expect(ws.readyState).toBe(WebSocket.OPEN);
+    expect(onopen).toHaveBeenCalled();
+  });
+
+  it('simulateMessage(data) calls onmessage with MessageEvent containing data', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    const onmessage = vi.fn();
+    ws.onmessage = onmessage;
+    ws.simulateOpen();
+    ws.simulateMessage({ type: 'entities_updated' });
+    expect(onmessage).toHaveBeenCalledWith(
+      expect.objectContaining({
+        data: JSON.stringify({ type: 'entities_updated' }),
+      })
+    );
+  });
+
+  it('simulateClose() calls onclose handler', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    const onclose = vi.fn();
+    ws.onclose = onclose;
+    ws.simulateOpen();
+    ws.simulateClose();
+    expect(onclose).toHaveBeenCalled();
+  });
+
+  it('multiple listeners via addEventListener work', () => {
+    const ws = new MockWebSocket('ws://localhost/v1/ws');
+    const listener1 = vi.fn();
+    const listener2 = vi.fn();
+    ws.addEventListener('message', listener1);
+    ws.addEventListener('message', listener2);
+    ws.simulateOpen();
+    ws.simulateMessage({ test: true });
+    expect(listener1).toHaveBeenCalled();
+    expect(listener2).toHaveBeenCalled();
+  });
+});
diff --git a/frontend/src/__mocks__/MockWebSocket.ts b/frontend/src/__mocks__/MockWebSocket.ts
new file mode 100644
index 0000000..299be82
--- /dev/null
+++ b/frontend/src/__mocks__/MockWebSocket.ts
@@ -0,0 +1,91 @@
+export class MockWebSocket {
+  static CONNECTING = 0;
+  static OPEN = 1;
+  static CLOSING = 2;
+  static CLOSED = 3;
+
+  static instances: MockWebSocket[] = [];
+  static lastInstance: MockWebSocket | undefined;
+
+  url: string;
+  protocol: string;
+  readyState: number = MockWebSocket.CONNECTING;
+  sentMessages: string[] = [];
+
+  onopen: ((ev: Event) => void) | null = null;
+  onmessage: ((ev: MessageEvent) => void) | null = null;
+  onclose: ((ev: CloseEvent) => void) | null = null;
+  onerror: ((ev: Event) => void) | null = null;
+
+  private _listeners: Map<string, Set<EventListenerOrEventListenerObject>> = new Map();
+
+  constructor(url: string, protocol?: string) {
+    this.url = url;
+    this.protocol = protocol ?? '';
+    MockWebSocket.instances.push(this);
+    MockWebSocket.lastInstance = this;
+  }
+
+  send(data: string): void {
+    this.sentMessages.push(data);
+  }
+
+  close(_code?: number, _reason?: string): void {
+    this.readyState = MockWebSocket.CLOSED;
+  }
+
+  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
+    if (!this._listeners.has(type)) {
+      this._listeners.set(type, new Set());
+    }
+    this._listeners.get(type)!.add(listener);
+  }
+
+  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
+    this._listeners.get(type)?.delete(listener);
+  }
+
+  dispatchEvent(_event: Event): boolean {
+    return true;
+  }
+
+  // Test helpers
+
+  simulateOpen(): void {
+    this.readyState = MockWebSocket.OPEN;
+    const event = new Event('open');
+    if (this.onopen) this.onopen(event);
+    this._dispatch('open', event);
+  }
+
+  simulateMessage(data: unknown): void {
+    const event = new MessageEvent('message', { data: JSON.stringify(data) });
+    if (this.onmessage) this.onmessage(event);
+    this._dispatch('message', event);
+  }
+
+  simulateClose(code?: number, reason?: string): void {
+    this.readyState = MockWebSocket.CLOSED;
+    const event = new CloseEvent('close', { code: code ?? 1000, reason: reason ?? '' });
+    if (this.onclose) this.onclose(event);
+    this._dispatch('close', event);
+  }
+
+  private _dispatch(type: string, event: Event): void {
+    const listeners = this._listeners.get(type);
+    if (listeners) {
+      for (const listener of listeners) {
+        if (typeof listener === 'function') {
+          listener(event);
+        } else {
+          listener.handleEvent(event);
+        }
+      }
+    }
+  }
+
+  static reset(): void {
+    MockWebSocket.instances = [];
+    MockWebSocket.lastInstance = undefined;
+  }
+}
diff --git a/frontend/src/test-helpers.test.tsx b/frontend/src/test-helpers.test.tsx
new file mode 100644
index 0000000..6201cec
--- /dev/null
+++ b/frontend/src/test-helpers.test.tsx
@@ -0,0 +1,67 @@
+import { screen, waitFor } from '@testing-library/react';
+import { renderWithContext, mockFetchResponses } from './test-helpers';
+import { MockWebSocket } from './__mocks__/MockWebSocket';
+
+describe('mockFetchResponses', () => {
+  it('fetch mock intercepts calls and returns configured responses', async () => {
+    mockFetchResponses({
+      '/v1/entities': { body: [{ id: 'e1', name: 'Test' }] },
+    });
+    const res = await fetch('/v1/entities');
+    const data = await res.json();
+    expect(data).toEqual([{ id: 'e1', name: 'Test' }]);
+  });
+
+  it('fetch mock can match by URL path', async () => {
+    mockFetchResponses({
+      '/v1/scenes': { body: [{ id: 's1', name: 'Scene 1' }] },
+      '/v1/entities': { body: [] },
+    });
+    const scenesRes = await fetch('/v1/scenes');
+    const scenes = await scenesRes.json();
+    expect(scenes).toHaveLength(1);
+
+    const entitiesRes = await fetch('/v1/entities');
+    const entities = await entitiesRes.json();
+    expect(entities).toHaveLength(0);
+  });
+
+  it('unmocked fetch calls return a clear error response', async () => {
+    mockFetchResponses({});
+    const res = await fetch('/v1/unknown');
+    expect(res.ok).toBe(false);
+    expect(res.status).toBe(404);
+  });
+});
+
+describe('renderWithContext', () => {
+  it('wraps component in AppProvider', () => {
+    renderWithContext(<div data-testid="child">Hello</div>);
+    expect(screen.getByTestId('child')).toBeInTheDocument();
+  });
+
+  it('pre-mocks mount-time fetches (/v1/scenes, /v1/entities, /v1/tracing/status)', async () => {
+    renderWithContext(<div>Test</div>);
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalled();
+    });
+  });
+
+  it('creates MockWebSocket and auto-opens it', async () => {
+    renderWithContext(<div>Test</div>);
+    const instance = MockWebSocket.lastInstance;
+    expect(instance).toBeDefined();
+    expect(instance!.readyState).toBe(WebSocket.OPEN);
+  });
+
+  it('custom mock data can be passed to override defaults', async () => {
+    renderWithContext(<div>Test</div>, {
+      fetchOverrides: {
+        '/v1/scenes': { body: [{ id: 'custom', name: 'Custom Scene' }] },
+      },
+    });
+    await waitFor(() => {
+      expect(globalThis.fetch).toHaveBeenCalled();
+    });
+  });
+});
diff --git a/frontend/src/test-helpers.tsx b/frontend/src/test-helpers.tsx
new file mode 100644
index 0000000..731ada7
--- /dev/null
+++ b/frontend/src/test-helpers.tsx
@@ -0,0 +1,96 @@
+import React from 'react';
+import { render, act, type RenderResult } from '@testing-library/react';
+import { AppProvider } from './AppContext';
+import { MockWebSocket } from './__mocks__/MockWebSocket';
+
+export interface MockRoute {
+  body?: unknown;
+  status?: number;
+  ok?: boolean;
+  headers?: Record<string, string>;
+}
+
+export function mockFetchResponses(routes: Record<string, MockRoute>): void {
+  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
+    let pathname: string;
+    if (typeof input === 'string') {
+      // Handle relative paths (e.g., '/v1/entities') and full URLs
+      try {
+        pathname = new URL(input, 'http://localhost').pathname;
+      } catch {
+        pathname = input;
+      }
+    } else if (input instanceof URL) {
+      pathname = input.pathname;
+    } else {
+      // Request object
+      pathname = new URL(input.url, 'http://localhost').pathname;
+    }
+
+    // Try exact match first, then prefix match
+    let route = routes[pathname];
+    if (!route) {
+      for (const [key, value] of Object.entries(routes)) {
+        if (key !== '*' && pathname.startsWith(key)) {
+          route = value;
+          break;
+        }
+      }
+    }
+    // Fallback to wildcard
+    if (!route && routes['*']) {
+      route = routes['*'];
+    }
+
+    if (route) {
+      return {
+        ok: route.ok ?? true,
+        status: route.status ?? 200,
+        json: async () => route!.body,
+        text: async () => JSON.stringify(route!.body),
+        headers: new Headers(route.headers),
+      } as Response;
+    }
+
+    return {
+      ok: false,
+      status: 404,
+      json: async () => ({ error: 'Not mocked' }),
+      text: async () => 'Not mocked',
+      headers: new Headers(),
+    } as Response;
+  });
+}
+
+const DEFAULT_FETCH_MOCKS: Record<string, MockRoute> = {
+  '/v1/scenes': { body: [] },
+  '/v1/entities': { body: [] },
+  '/v1/tracing/status': { body: {} },
+  '/v1/scenes/campaign_planning/messages': { body: [] },
+  '*': { body: {} },
+};
+
+export function renderWithContext(
+  ui: React.ReactElement,
+  options?: {
+    fetchOverrides?: Record<string, MockRoute>;
+  }
+): RenderResult & { mockWebSocket: MockWebSocket } {
+  const mergedRoutes = { ...DEFAULT_FETCH_MOCKS, ...options?.fetchOverrides };
+  mockFetchResponses(mergedRoutes);
+
+  let result: RenderResult;
+  act(() => {
+    result = render(<AppProvider>{ui}</AppProvider>);
+  });
+
+  // Auto-open the WebSocket created by AppProvider
+  const wsInstance = MockWebSocket.lastInstance;
+  if (wsInstance) {
+    act(() => {
+      wsInstance.simulateOpen();
+    });
+  }
+
+  return { ...result!, mockWebSocket: wsInstance! };
+}
diff --git a/frontend/src/test-setup.ts b/frontend/src/test-setup.ts
index 39d09ea..9fa13e0 100644
--- a/frontend/src/test-setup.ts
+++ b/frontend/src/test-setup.ts
@@ -3,12 +3,35 @@ import '@testing-library/jest-dom/vitest'
 
 // Cleanup rendered components after each test to prevent cross-test DOM pollution.
 import { cleanup } from '@testing-library/react'
+import { MockWebSocket } from './__mocks__/MockWebSocket'
+
+// Replace globalThis.WebSocket with MockWebSocket
+globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
+
+// Mock marked to avoid pulling in the full library in tests
+vi.mock('marked', () => ({
+  marked: {
+    parse: (content: string) => `<p>${content}</p>`,
+    use: vi.fn(),
+  },
+}))
+
+// Set up a default no-op fetch mock that returns empty responses
+beforeEach(() => {
+  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
+    ok: true,
+    status: 200,
+    json: async () => ({}),
+    text: async () => '{}',
+  } as Response))
+})
 
 afterEach(() => {
   cleanup()
 })
 
-// Restore all mocks after each test to prevent cross-test mock pollution.
+// Restore all mocks and reset WebSocket state after each test
 afterEach(() => {
   vi.restoreAllMocks()
+  MockWebSocket.reset()
 })
