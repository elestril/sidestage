# Code Review: Section 02 - Frontend Mocks

## High Severity
1. Prefix matching in mockFetchResponses is order-dependent — should sort by descending key length for most-specific-first matching.
2. renderWithContext uses synchronous act() wrapping an async render — causes act() warnings from unflushed async effects.
3. result variable used before definite assignment with non-null assertion.

## Medium Severity
4. Two separate afterEach blocks in test-setup.ts create ordering fragility — restoreAllMocks may run before cleanup.
5. close() does not invoke onclose handlers (unlike simulateClose).
6. MockWebSocket test does not test static reset() method.
7. MockWebSocket test does not test static instances array.

## Low Severity
8. removeEventListener is not tested.
9. dispatchEvent is a no-op stub.
10. mockFetchResponses ignores RequestInit (method, body, headers).
11. renderWithContext test uses WebSocket.OPEN instead of MockWebSocket.OPEN.
