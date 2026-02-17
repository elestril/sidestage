export class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];
  static lastInstance: MockWebSocket | undefined;

  url: string;
  protocol: string;
  readyState: number = MockWebSocket.CONNECTING;
  sentMessages: string[] = [];

  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;

  private _listeners: Map<string, Set<EventListenerOrEventListenerObject>> = new Map();

  constructor(url: string, protocol?: string) {
    this.url = url;
    this.protocol = protocol ?? '';
    MockWebSocket.instances.push(this);
    MockWebSocket.lastInstance = this;
  }

  send(data: string): void {
    this.sentMessages.push(data);
  }

  close(_code?: number, _reason?: string): void {
    this.readyState = MockWebSocket.CLOSED;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (!this._listeners.has(type)) {
      this._listeners.set(type, new Set());
    }
    this._listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this._listeners.get(type)?.delete(listener);
  }

  dispatchEvent(_event: Event): boolean {
    return true;
  }

  // Test helpers

  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    const event = new Event('open');
    if (this.onopen) this.onopen(event);
    this._dispatch('open', event);
  }

  simulateMessage(data: unknown): void {
    const event = new MessageEvent('message', { data: JSON.stringify(data) });
    if (this.onmessage) this.onmessage(event);
    this._dispatch('message', event);
  }

  simulateClose(code?: number, reason?: string): void {
    this.readyState = MockWebSocket.CLOSED;
    const event = new CloseEvent('close', { code: code ?? 1000, reason: reason ?? '' });
    if (this.onclose) this.onclose(event);
    this._dispatch('close', event);
  }

  private _dispatch(type: string, event: Event): void {
    const listeners = this._listeners.get(type);
    if (listeners) {
      for (const listener of listeners) {
        if (typeof listener === 'function') {
          listener(event);
        } else {
          listener.handleEvent(event);
        }
      }
    }
  }

  static reset(): void {
    MockWebSocket.instances = [];
    MockWebSocket.lastInstance = undefined;
  }
}
