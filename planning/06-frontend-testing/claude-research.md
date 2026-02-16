# Research Findings: Frontend & E2E Testing Strategy

## Part 1: Codebase Research

### 1.1 Existing Test Infrastructure

**Directory Structure:**
- `tests/unit/` — 50+ unit tests covering graph, memory, migration, embeddings, storage
- `tests/integration/` — ~10 integration tests (graph queries, agent context, entity CRUD)
- `tests/devserver/` — E2E tests against a live dev server instance
- `tests/meta/` — validation tests (campaign fixture data well-formedness)

**Root `conftest.py` Fixtures:**
- `auto_init_config` (auto-use, session) — initializes `SidestageConfig` with temp directories
- `reset_otel` (auto-use) — resets OpenTelemetry provider between tests
- `_clean_request_context` (auto-use) — cleans up `RequestContext` tokens

**DevServer `conftest.py` Fixtures (`tests/devserver/`):**
- `devserver` (session-scoped) — manages the full server lifecycle
- `client` (session-scoped) — `httpx.Client` pointed at `http://localhost:8000`
- `log_observer` (function-scoped) — `LogObserver` instance with log file paths, auto-marks before each test
- `check_server_errors` (auto-use) — asserts no unexpected errors in server logs after each test
- `fresh_campaign` (class-scoped) — resets campaign state for test isolation

**Test Utilities (`tests/devserver/helpers.py`):**
- `LogObserver` — tracks log file growth: `mark()`, `read_new()`, `wait_for_pattern()`, `assert_contains()`
- `poll_scene_messages()` — polls GET `/v1/scenes/{id}/messages` with min_count and predicate
- `server_is_running()` — health check via `/v1/entities`
- `llm_is_running()` — checks LLM server at port 8080

**Test Dependencies (from `pyproject.toml`):**
- pytest, pytest-timeout, pytest-anyio, httpx, anyio[trio]
- No Playwright dependencies yet

**Test Markers:**
- `@pytest.mark.anyio` — async test support
- `@pytest.mark.llm` — tests requiring LLM (auto-skipped if unavailable)

### 1.2 Frontend Structure

**Stack:** React 19, Vite, Tailwind CSS 4, Tiptap editor, React Router 7

**Key Components:**
- `AppContext.tsx` — global state provider with WebSocket management, entity state, campaign operations
- `ChatWidget.tsx` — chat messages display and input, handles Chat/System/Error event types
- `EntityBrowser.tsx` — entity CRUD with Tiptap rich text editor integration
- `Layout.tsx` — header with campaign name, sidebar navigation
- `App.tsx` — React Router routes (`/sidestage/`, `/sidestage/scenes/:sceneId`)

**Build & Serve:**
- Built to `frontend/dist/` via Vite
- Served at `/sidestage/` by FastAPI `StaticFiles` mount
- Vite dev server proxies `/v1` to `localhost:8000` with WebSocket support enabled

**Existing Frontend Tests:** None. Only backend tests validate that the SPA is served correctly.

### 1.3 WebSocket & Real-Time Infrastructure

**Endpoint:** `/v1/ws` in `orchestrator.py`

**Server-to-Client Messages:**
- `entities_updated` — entity list changed
- `scene_updated` — scene data changed
- `event` — new event (chat, system, error)
- `actor_status` — actor state changes
- `entity_content_sync` — collaborative editing sync

**Client-to-Server Messages:**
- `chat_message` — user sends chat message
- `entity_content_sync` — collaborative editing updates

**Connection Management:**
- `User` actor class manages WebSocket connections list
- Broadcasts to all connected clients
- Starlette `TestClient.websocket_connect()` used in existing integration tests

### 1.4 Dev Mode

- `scripts/run-dev.sh` starts uvicorn with `reload=True` in `sidestage.dev/` directory
- Factory pattern (`get_app()`) with environment variables for campaign/dir config
- Auto-copies `data/dev_campaign/` on first run
- MCP configured via `.mcp.json` (HTTP endpoint at `localhost:8000/v1/mcp`)

### 1.5 Key Testing Patterns

- **Config auto-init:** Session-scoped fixture initializes `SidestageConfig` once
- **Async tests:** `@pytest.mark.anyio` with anyio[trio] backend
- **WebSocket testing:** `TestClient.websocket_connect()` for in-process testing
- **In-memory app testing:** `SidestageOrchestrator` + Starlette `TestClient`
- **LLM skip:** Auto-skip tests marked `@pytest.mark.llm` when LLM unavailable
- **Campaign mocking:** `tmp_path` fixtures with copied campaign data

---

## Part 2: Web Research

### 2.1 pytest-playwright + FastAPI Integration

**Installation:** `pip install pytest-playwright` then `playwright install` for browsers.

**Dev Server Fixture Pattern:**
- Session-scoped fixture that starts uvicorn in a subprocess
- Wait for readiness via health check polling
- Yield to tests, then kill process and clean up
- Sidestage already has this pattern in `tests/devserver/conftest.py` — can be extended

**Key Integration Points:**
- pytest-playwright provides `page`, `browser`, `context` fixtures automatically
- Configure `base_url` to match devserver fixture (`http://localhost:8000/sidestage`)
- Can share `httpx` client fixture alongside Playwright for cross-validation
- FastAPI's async nature works well with session-scoped fixtures

**Best Practices:**
- Keep tests isolated and repeatable
- Abstract browser interactions into page objects or helper functions
- Use Playwright's auto-waiting instead of explicit sleeps

### 2.2 Vitest + React Testing Library Setup

**Installation:**
```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

**Configuration (`vitest.config.ts` or in `vite.config.ts`):**
```typescript
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
  },
});
```

**Setup File (`tests/setup.ts`):**
```typescript
import { expect, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';

expect.extend(matchers);
afterEach(() => cleanup());
```

**Environment Choice:**
- `jsdom` is the standard, most compatible option
- `happy-dom` is faster but less complete — jsdom recommended for Sidestage given Tiptap/marked usage

**Testing Patterns:**
- `render()` + `screen.getByRole/getByText` for component queries
- `userEvent` for interaction simulation
- Mock `fetch` with `vi.fn()` or MSW for API calls
- Mock WebSocket with custom class or `vi.mock()`

### 2.3 Playwright WebSocket Testing

**WebSocket API (`page.on('websocket')`):**
- `websocket.on('framereceived', handler)` — intercept incoming frames
- `websocket.on('framesent', handler)` — intercept outgoing frames
- `websocket.waitForEvent(event)` — wait for specific events
- `websocket.url()` — get WebSocket URL
- `websocket.isClosed()` — check connection state

**WebSocketRoute (v1.48+) for Mocking/Intercepting:**
- `page.route_web_socket(url, handler)` — intercept WebSocket connections
- **Mock mode:** Don't call `connect_to_server()`, handle all messages manually
- **Intercept mode:** Call `connect_to_server()` to proxy with modifications
- `ws.on_message(handler)` — handle incoming messages (disables auto-forwarding)
- `ws.send(message)` — send data to page or server
- `ws.close(code, reason)` — close connection

**Multi-Client Sync Testing:**
- Open multiple `browser.new_context()` instances
- Each gets its own page and WebSocket connection
- Perform action in one, assert result appears in other
- Use `page.wait_for_selector()` or `expect(locator).to_have_text()` for assertions

**Timing Best Practices:**
- Use Playwright's built-in auto-retry assertions (`expect(locator).to_have_text()`)
- Avoid explicit `time.sleep()` — use `page.wait_for_selector()` or `page.wait_for_function()`
- For WebSocket messages, use `websocket.waitForEvent('framereceived')`
- Set reasonable timeouts (default 30s, configurable per-assertion)

**Sources:**
- [Playwright WebSocket API](https://playwright.dev/docs/api/class-websocket)
- [Playwright WebSocketRoute (Python)](https://playwright.dev/python/docs/api/class-websocketroute)
- [Vitest + React Testing Library Guide](https://www.robinwieruch.de/vitest-react-testing-library/)
- [Playwright Mock APIs](https://playwright.dev/docs/mock)
