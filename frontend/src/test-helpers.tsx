import React from 'react';
import { render, act, type RenderResult } from '@testing-library/react';
import { AppProvider } from './AppContext';
import { MockWebSocket } from './__mocks__/MockWebSocket';

export interface MockRoute {
  body?: unknown;
  status?: number;
  ok?: boolean;
  headers?: Record<string, string>;
}

export function mockFetchResponses(routes: Record<string, MockRoute>): void {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    let pathname: string;
    if (typeof input === 'string') {
      // Handle relative paths (e.g., '/v1/entities') and full URLs
      try {
        pathname = new URL(input, 'http://localhost').pathname;
      } catch {
        pathname = input;
      }
    } else if (input instanceof URL) {
      pathname = input.pathname;
    } else {
      // Request object
      pathname = new URL(input.url, 'http://localhost').pathname;
    }

    // Try exact match first, then longest-prefix match
    let route = routes[pathname];
    if (!route) {
      const sortedEntries = Object.entries(routes)
        .filter(([k]) => k !== '*')
        .sort(([a], [b]) => b.length - a.length);
      for (const [key, value] of sortedEntries) {
        if (pathname.startsWith(key)) {
          route = value;
          break;
        }
      }
    }
    // Fallback to wildcard
    if (!route && routes['*']) {
      route = routes['*'];
    }

    if (route) {
      return {
        ok: route.ok ?? true,
        status: route.status ?? 200,
        json: async () => route!.body,
        text: async () => JSON.stringify(route!.body),
        headers: new Headers(route.headers),
      } as Response;
    }

    return {
      ok: false,
      status: 404,
      json: async () => ({ error: 'Not mocked' }),
      text: async () => 'Not mocked',
      headers: new Headers(),
    } as Response;
  });
}

const DEFAULT_FETCH_MOCKS: Record<string, MockRoute> = {
  '/v1/scenes': { body: [] },
  '/v1/entities': { body: [] },
  '/v1/tracing/status': { body: {} },
  '/v1/scenes/campaign_planning/messages': { body: [] },
  '*': { body: {} },
};

export function renderWithContext(
  ui: React.ReactElement,
  options?: {
    fetchOverrides?: Record<string, MockRoute>;
  }
): RenderResult & { mockWebSocket: MockWebSocket } {
  const mergedRoutes = { ...DEFAULT_FETCH_MOCKS, ...options?.fetchOverrides };
  mockFetchResponses(mergedRoutes);

  let result: RenderResult;
  act(() => {
    result = render(<AppProvider>{ui}</AppProvider>);
  });

  // Auto-open the WebSocket created by AppProvider
  const wsInstance = MockWebSocket.lastInstance;
  if (wsInstance) {
    act(() => {
      wsInstance.simulateOpen();
    });
  }

  return { ...result!, mockWebSocket: wsInstance! };
}
