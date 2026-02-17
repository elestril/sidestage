# Code Review: Section 02 - Frontend Mocks

**Date:** 2026-02-16

## Auto-fixes

### Prefix matching order in mockFetchResponses
Sort prefix-match candidates by descending key length so the most specific prefix wins, not whichever appears first in insertion order.

### Consolidate afterEach hooks in test-setup.ts
Merge the two separate afterEach blocks into one to ensure cleanup runs before restoreAllMocks.

## Let Go

- renderWithContext using synchronous act() — async wrapper would change API for all downstream tests. Act warnings are cosmetic.
- result! non-null assertion — act() callback is synchronous so assignment always happens.
- close() not firing onclose — simulateClose() exists for tests; close() is for teardown where we don't want side effects.
- Missing test coverage for reset(), instances, removeEventListener — cosmetic gaps, don't affect correctness.
- dispatchEvent no-op, mockFetchResponses ignoring RequestInit, WebSocket.OPEN vs MockWebSocket.OPEN — acceptable simplifications.
