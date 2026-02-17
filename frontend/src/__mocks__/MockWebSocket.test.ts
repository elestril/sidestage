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
