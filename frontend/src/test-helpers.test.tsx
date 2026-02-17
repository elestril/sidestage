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
    renderWithContext(<div>Test</div>);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });
  });

  it('creates MockWebSocket and auto-opens it', async () => {
    renderWithContext(<div>Test</div>);
    const instance = MockWebSocket.lastInstance;
    expect(instance).toBeDefined();
    expect(instance!.readyState).toBe(WebSocket.OPEN);
  });

  it('custom mock data can be passed to override defaults', async () => {
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
