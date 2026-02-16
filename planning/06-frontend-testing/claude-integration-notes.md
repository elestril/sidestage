# Integration Notes: Opus Review Feedback

## Accepted Changes (incorporated into claude-plan.md)

### Critical Fixes

1. **Mock Actor injection point** — Specified exact injection in `NPCActor._update_prompt()`. The mock replaces `LiteLLMAgent` at the agent level, not the actor level. The env var `SIDESTAGE_MOCK_AGENT=1` causes `_update_prompt()` to create a `MockLLMAgent` instead of `LiteLLMAgent`. Test-only API endpoint accesses mock via `orchestrator.active_scenes -> scene -> character.actor.agent`.

2. **MockResponse.event_type** — Changed from `"Chat"` to `"ChatMessage"` to match TypeScript `EventType`.

3. **AppProvider mount side effects** — Added explicit documentation that all unit tests rendering AppProvider must mock: fetch to `/v1/scenes`, `/v1/entities`, `/v1/tracing/status`, and `globalThis.WebSocket`. Added helper wrapper pattern.

4. **E2E server port** — Changed E2E server to use port 8001 to avoid conflicts with dev instance on port 8000. Env var `SIDESTAGE_PORT=8001` passed to subprocess.

5. **MemoryRouter for unit tests** — Added note that `App.test.tsx` must use `MemoryRouter` from react-router-dom instead of `BrowserRouter`.

6. **Frontend build fixture: npm install** — Added step to check for `node_modules/` and run `npm install` if missing before building.

7. **Env var passing to run-dev.sh** — Specified that `subprocess.Popen(env={**os.environ, "SIDESTAGE_MOCK_AGENT": "1", "SIDESTAGE_PORT": "8001"})` is used.

### Significant Fixes

8. **Tiptap in jsdom** — Marked Tiptap editor interaction tests as E2E-only. Unit tests for EntityBrowser will mock the Tiptap editor component. Only test entity list rendering, selection, and save calls in unit tests.

9. **marked async** — Added note to verify `marked.parse()` behavior in v17. If async, use `marked.parseInline()` or configure `marked.use({ async: false })` in test setup.

10. **npm install in build fixture** — Added to the fixture logic.

11. **EventType naming** — Fixed throughout the mock actor section.

### Moderate Fixes

12. **React 19 + RTL compatibility** — Added note to pin `@testing-library/react@^16.0.0` minimum.

13. **Mock cleanup** — Added `vi.restoreAllMocks()` to `afterEach` in test setup.

14. **debugMode/tracingError** — Added to AppContext test plan.

15. **actor_id in MockResponse** — Added field with default `"agent:co_author"`.

16. **EntityModal fetch** — Added note about mocking the fetch chain.

17. **user-event async** — Added note about `await userEvent.click()`.

18. **CSS handling** — Added CSS module mock to Vitest config.

## Deferred Items

- **WebSocket reconnection bug** — This is a pre-existing frontend bug, not a testing concern. Will add a test that documents the broken behavior but won't fix it as part of this testing project.
- **WebSocket re-creation on scene change** — Documented as known behavior. Tests will account for connection lifecycle in multi-scene tests.
- **Scene deactivation on campaign reset** — Same gap exists in existing devserver fixture. Out of scope for this plan.
- **CI integration** — Noted as follow-up work.
