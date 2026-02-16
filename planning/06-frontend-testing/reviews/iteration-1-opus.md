# Opus Review

**Model:** claude-opus-4
**Generated:** 2026-02-16T22:45:00Z

---

## Overall Assessment

This is a solid plan that correctly identifies the testing gap and proposes reasonable tooling choices. The Vitest + React Testing Library combination is the right call for the frontend, and using pytest-playwright to keep E2E tests within the existing Python infrastructure is a good architectural decision. However, there are several significant issues -- some that could cause real problems during implementation, and some where the plan does not match the actual codebase structure.

---

## Critical Issues

### 1. WebSocket reconnection is broken in AppContext -- tests will mask this

In `AppContext.tsx` at line 190, the `onclose` handler contains a no-op:

```typescript
s.onclose = () => {
  console.log('WebSocket disconnected. Retrying in 2s...');
  setSocket(null);
  setTimeout(() => {}, 2000); // <-- does nothing
};
```

The E2E tests in Section 5.4 (Real-Time Sync) rely on stable WebSocket connections. If a connection drops during a test, it will never reconnect. The plan does not acknowledge this. E2E tests that run after any WebSocket interruption will silently fail with timing-related assertions. You should either fix the reconnection logic first, or document this as a known limitation and add a test that explicitly validates reconnection behavior.

### 2. The WebSocket effect has `currentSceneId` as a dependency, causing reconnection on scene changes

In `AppContext.tsx` at line 194, the WebSocket `useEffect` has `currentSceneId` in its dependency array. This means every scene navigation destroys and recreates the WebSocket connection. The E2E test in Section 5.6 (Scene Navigation) will trigger this, and the tests in Section 5.4 (Real-Time Sync) may be affected if a scene change occurs. The plan should note that the WebSocket lifecycle is scene-dependent, which will affect how tests sequence operations. Combined with the broken reconnect handler above, this is fragile.

### 3. AppProvider mount side effects -- all tests must mock 3 fetches + WebSocket

`AppProvider` immediately triggers on mount:
- A fetch to `/v1/scenes`
- A fetch to `/v1/entities`
- A fetch to `/v1/tracing/status`
- A `new WebSocket(...)` connection attempt

All of these must be mocked before render. The mocking strategy in Section 2.3 mentions this in passing, but the test plan in Section 2.4 does not spell out that every `AppContext.test.tsx` case needs to handle these simultaneous mount-time side effects.

### 4. The Mock Actor integration point analysis is incomplete

Section 4.2 proposes two options and recommends Option A (environment variable). However, the agent is not injected; it is constructed inline by `NPCActor` based on the campaign's LLM config.

Option A says "the orchestrator checks this flag and registers MockActor instead of the real agent" -- but there is no actor registry. The actors are created by `Scene.activate()` which calls `self.campaign.get_character()` for each character, and the resulting `Character` objects have their `NPCActor`s wired up with `_update_prompt()`.

The plan needs to specify the exact injection point. The most pragmatic approach would be to make `NPCActor._update_prompt()` check for the environment variable and swap in a mock agent that implements the same `arun()` interface as `LiteLLMAgent`. The test-only API endpoint also needs to reach into already-activated scenes to update the mock agent's response queue. This wiring is not addressed.

### 5. The `run-dev.sh` script uses `exec uv run sidestage`, not `uvicorn` directly

The E2E fixture needs to pass the `SIDESTAGE_MOCK_AGENT=1` environment variable. The fixture will need to set the env var via `subprocess.Popen(env=...)`. This interaction between the mock agent env var and the subprocess-based server startup is not addressed.

---

## Significant Issues

### 6. Tiptap editor testing is understated

Tiptap uses `contentEditable` divs and ProseMirror under the hood. In jsdom, `contentEditable` support is minimal. The editor will likely not render properly or accept input in a jsdom environment. The plan should either:
- Mark Tiptap integration tests as E2E-only (testing in real browser)
- Document the expected limitations of Tiptap in jsdom
- Consider using a mock for the editor in unit tests

### 7. The `marked` library renders asynchronously in newer versions

`marked` v17 may return a `Promise` from `marked.parse()`. The `ChatWidget.tsx` casts the result with `as string`, but in tests this could surface differently. The plan should note that `marked.parse()` behavior needs to be verified or mocked.

### 8. Base URL patterns in fetch mocking

The frontend code uses bare paths like `/v1/chat`, `/v1/entities`, `/v1/scenes`. In Vitest with jsdom, `fetch('/v1/entities')` will try to fetch from `http://localhost/v1/entities`. The mock needs to handle the absolute path patterns used in the app.

### 9. Frontend build fixture does not handle `npm install`

If someone pulls the repo fresh and runs E2E tests, the build will fail because `npm install` was never run. The fixture should either:
- Run `npm install` before `npm run build`
- Check for `node_modules/` and install if missing
- At minimum, fail with a clear error message

### 10. Session-scoped E2E server conflicts with dev instance on port 8000

If the dev instance is already running on port 8000, the E2E tests will fail to bind. The plan should specify a different port for E2E tests or detect and stop existing servers.

### 11. `EventType` naming mismatch

The TypeScript types define `'ChatMessage'` but the plan's `MockResponse` dataclass uses `event_type: str = "Chat"`. Should be `"ChatMessage"`.

---

## Moderate Issues

### 12. React 19 + React Testing Library compatibility
Pin a minimum RTL version that supports React 19.

### 13. Mock cleanup between tests
The setup file should also clean up mocked `fetch` and `WebSocket` globals to avoid cross-test pollution.

### 14. Missing tests for `debugMode` / `tracingError` state
These exist in AppContext but aren't covered in the test plan.

### 15. `actor_id` field missing from MockResponse
Chat message identification relies on `actor_id === 'user'`. The MockResponse dataclass needs an `actor_id` field.

### 16. Entity widget click chains to EntityModal fetch
Clicking the entity widget in ChatWidget opens EntityModal which fetches `/v1/entities/{id}/markdown`. Tests must mock this.

### 17. Use MemoryRouter in App.test.tsx
BrowserRouter does not work in jsdom. Use `MemoryRouter` instead.

### 18. `fresh_e2e_campaign` fixture does not deactivate existing scenes
After campaign re-import, in-memory `active_scenes` may hold stale references.

---

## Minor Issues

### 19. TypeScript config needs definitive approach for test types
### 20. No CI integration mentioned
### 21. Test-only route registration file not specified
### 22. Default scene ID assumption should be documented
### 23. `@testing-library/user-event` v14+ is async-by-default
### 24. CSS handling in Vitest (Tailwind CSS 4 plugin in jsdom)

---

## Summary of Highest-Priority Items

1. **Fix the mock actor injection point** -- specify exactly where the mock gets swapped in
2. **Fix `MockResponse.event_type`** -- use `"ChatMessage"` not `"Chat"`
3. **Address Tiptap in jsdom** -- scope those tests to E2E or document limitations
4. **Handle AppProvider mount side effects** -- every unit test must mock 3 fetches + WebSocket
5. **Specify the E2E server port** -- avoid conflicts with dev instance on port 8000
6. **Use MemoryRouter in App.test.tsx** -- BrowserRouter will not work in jsdom
7. **Run `npm install` in the build fixture** -- or detect missing `node_modules`
