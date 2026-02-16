# Implementation Plan: Integrated Frontend & E2E Testing Strategy

## 1. Context and Motivation

Sidestage's backend has 50+ unit tests, 10+ integration tests, and devserver E2E tests, but the React 19 SPA frontend has zero test coverage. This plan introduces two testing layers: Vitest-based component unit tests and Playwright-based full-stack E2E tests. Both layers integrate with the existing pytest infrastructure and follow established project conventions.

**Known frontend issues that affect testing:**
- The WebSocket `onclose` handler in `AppContext.tsx` has a no-op reconnect — `setTimeout(() => {}, 2000)` does nothing. Tests should document this, but fixing it is out of scope.
- The WebSocket `useEffect` depends on `currentSceneId`, meaning every scene navigation destroys and recreates the WebSocket connection. Multi-scene E2E tests must account for this.

## 2. Frontend Unit Testing Infrastructure

### 2.1 Vitest Configuration

The frontend uses Vite (v7) with React plugin, Tailwind CSS 4, and TypeScript 5.9. Vitest integrates natively with this stack.

**Dependencies to add to `frontend/package.json` devDependencies:**
- `vitest` — test runner
- `@testing-library/react` (>=16.0.0) — component rendering and queries (v16+ required for React 19 compatibility)
- `@testing-library/jest-dom` — DOM assertion matchers (`.toBeInTheDocument()`, `.toHaveTextContent()`, etc.)
- `@testing-library/user-event` — user interaction simulation (clicking, typing). Note: v14+ is async-by-default — all interaction calls must be `await`ed
- `jsdom` — DOM environment for Node.js (chosen over happy-dom for better Tiptap/marked compatibility)

**Configuration approach:** Add a `test` block to the existing `vite.config.ts` rather than creating a separate `vitest.config.ts`. This ensures test configuration inherits the existing React plugin, Tailwind plugin, and `base: '/sidestage/'` setting.

```typescript
// Addition to vite.config.ts defineConfig
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test-setup.ts',
  css: false,  // Disable CSS processing in tests (Tailwind CSS 4 plugin doesn't work in jsdom)
}
```

**Setup file `frontend/src/test-setup.ts`:**
- Import and extend `expect` with `@testing-library/jest-dom` matchers
- Register `afterEach` cleanup from React Testing Library
- Register `afterEach` with `vi.restoreAllMocks()` to prevent cross-test mock pollution
- Mock `globalThis.WebSocket` with `MockWebSocket` class
- Mock `globalThis.fetch` with default empty responses for mount-time calls
- This file runs before every test file

**Package.json scripts:**
- Add `"test": "vitest"` for interactive watch mode
- Add `"test:run": "vitest run"` for single-run CI mode

### 2.2 TypeScript Configuration for Tests

Create a `frontend/tsconfig.test.json` that extends `tsconfig.app.json` and adds `"types": ["vitest/globals"]`. This provides global type definitions for `describe`, `it`, `expect` without explicit imports (matching `globals: true` in Vitest config). The existing `tsconfig.app.json` has `"verbatimModuleSyntax": true`, so the test config must be a separate reference.

### 2.3 Mocking Strategy for Frontend Tests

The frontend has two external dependencies that need mocking in unit tests.

**Critical: AppProvider mount side effects.** Every test that renders `<AppProvider>` immediately triggers:
- `fetch('/v1/scenes')` — scene list
- `fetch('/v1/entities')` — entity list
- `fetch('/v1/tracing/status')` — debug tracing
- `new WebSocket(...)` — WebSocket connection

All of these must be mocked before render. Create a `renderWithContext()` helper that wraps components in `<AppProvider>`, pre-mocks all mount-time fetches with default data, and returns the render result. Tests that need specific mock data override the relevant fetch before calling `renderWithContext()`.

**Fetch API mocking:**
- Use `vi.fn()` to mock `globalThis.fetch` in setup
- Each test provides mock responses for the specific API calls it triggers
- Pattern: `vi.spyOn(globalThis, 'fetch').mockImplementation(url => ...)` matching URL paths like `/v1/scenes`, `/v1/entities`, `/v1/chat`
- Note: The frontend uses bare paths (`/v1/entities`), not absolute URLs. In jsdom these resolve relative to `http://localhost`. The mock must match these path patterns.

**WebSocket mocking:**
- Create a `MockWebSocket` class in `frontend/src/__mocks__/MockWebSocket.ts`
- Implements the `WebSocket` interface: `send()`, `close()`, event handlers (`onopen`, `onmessage`, `onclose`)
- Provides test helpers: `simulateMessage(data)`, `simulateOpen()`, `simulateClose()`
- Assign to `globalThis.WebSocket` in test setup
- This enables testing `AppContext`'s WebSocket message handling (entity updates, chat events, actor status, content sync) without a real server

**marked library note:** `marked` v17 may return a `Promise` from `marked.parse()`. The `ChatWidget.tsx` casts the result with `as string`. In test setup, configure `marked.use({ async: false })` to ensure synchronous behavior, or mock `marked.parse()` to return strings directly.

### 2.4 Component Test Plans

All tests co-located alongside their components in `frontend/src/`.

**`AppContext.test.tsx`:**
- Test initial state loading: verify `loadScenes()` and `loadEntities()` call fetch on mount
- Test `sendMessage()`: verify POST to `/v1/chat` with correct payload (`{ message, scene_id }`)
- Test `saveEntityMarkdown()`: verify POST to `/v1/entities/{id}/markdown`
- Test `saveEntity()`: verify POST to `/v1/entities/{id}`
- Test WebSocket message routing: simulate `entities_updated` -> verify `loadEntities()` called
- Test WebSocket `event` message: simulate event -> verify message added to state
- Test WebSocket `actor_status` message: simulate thinking/done -> verify `thinkingActors` set updates
- Test WebSocket `scene_updated` message: simulate -> verify `loadScenes()` called
- Test `entity_content_sync` message: verify sync listeners are notified
- Test `debugMode` and `tracingError`: verify tracing status fetch on mount, error state management

**`ChatWidget.test.tsx`:**
- Test message rendering: provide messages array via context, verify bubbles render with correct content
- Test user vs NPC message styling: user messages (`actor_id === 'user'`) align right with purple background, NPC messages align left with character name header
- Test event type handling: `JoinEvent`, `LeaveEvent`, `AdjustGametime` render as centered system messages
- Test `Error` event type: renders in red error styling with markdown content
- Test markdown rendering: message body with markdown is rendered as HTML via `marked`
- Test thinking indicator: when `thinkingActors` contains a character, bouncing dots appear with character name
- Test message input: type text, submit form, verify `sendMessage()` called, input clears
- Test empty input prevention: submit with empty input does nothing
- Test entity widget: message with `metadata.widget.type === 'entity'` renders entity card. Note: clicking the card opens `EntityModal` which fetches `/v1/entities/{id}/markdown` — this fetch must be mocked in tests that test the click interaction
- Test gametime display: active scene gametime formatted as "Day N, HH:MM:SS"

**`EntityBrowser.test.tsx`:**
- Test entity list rendering: provide entities via context, verify list items appear
- Test entity type filtering: verify filter controls work
- Test entity save: trigger save, verify `saveEntityMarkdown()` called
- Test entity modal: verify modal opens with entity data
- **Note on Tiptap:** Tiptap uses `contentEditable` divs and ProseMirror under the hood. In jsdom, `contentEditable` support is minimal and Tiptap will not render or accept input properly. Tiptap-specific tests (editor rendering, content editing, markdown export) should be E2E-only. Unit tests should mock the Tiptap editor component and test the surrounding logic (entity list, selection, save API calls).

**`Layout.test.tsx`:**
- Test header rendering: campaign name, navigation links
- Test sidebar scene list: scenes from context render as nav items
- Test scene switching: clicking scene calls `setCurrentSceneId()`

**`App.test.tsx`:**
- Test route rendering: `/sidestage/` renders default scene view
- Test scene route: `/sidestage/scenes/:sceneId` renders with correct scene
- **Important:** Use `MemoryRouter` from `react-router-dom` instead of `BrowserRouter` in tests. jsdom does not properly support the History API needed by `BrowserRouter`. Wrap the component in `<MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>`.

## 3. E2E Testing Infrastructure (Playwright + pytest)

### 3.1 Python Dependencies

Add `pytest-playwright` to the `dev` dependency group in `pyproject.toml`. This provides:
- `page`, `browser`, `context` fixtures
- Browser installation CLI (`playwright install chromium`)
- Pytest integration with tracing and screenshot support

After adding the dependency, run `playwright install chromium` to download the browser binary.

Add pytest marker for e2e tests: `"e2e: end-to-end browser tests requiring Playwright"` to `pyproject.ini_options.markers`.

### 3.2 Frontend Build Fixture

E2E tests require the built frontend at `frontend/dist/`. A session-scoped fixture handles this automatically.

**Fixture `frontend_dist` in `tests/e2e/conftest.py`:**

Logic:
1. Check if `frontend/node_modules/` exists. If missing, run `npm install` in `frontend/`. Fail with clear error if npm is not available.
2. Check if `frontend/dist/index.html` exists
3. If missing, run `npm run build` in `frontend/` and fail if build fails
4. If present, compare mtime of `frontend/dist/` against newest file in `frontend/src/`
5. If src is newer, rebuild
6. Return the dist path

This fixture is session-scoped so the build happens at most once per test run.

### 3.3 E2E Server Fixture

The E2E tests manage their own server instance, similar to the existing devserver pattern in `tests/devserver/conftest.py` but with additional setup for Playwright.

**Port:** Default to port **8001** to avoid conflicts with the dev instance (which runs on port 8000 as configured in `sidestage.dev/`). Pass `SIDESTAGE_PORT=8001` as an environment variable. If port 8001 is unavailable, the fixture should probe for the next available port (8002, 8003, etc.) by attempting to bind a socket. This ensures tests work even if another process occupies 8001.

**Fixture `e2e_server` in `tests/e2e/conftest.py` (session-scoped):**

1. Depend on `frontend_dist` fixture (ensures frontend is built)
2. Restore dev campaign markdown from `data/dev_campaign/` (full reset)
3. Rotate all log files (server.log, request.log, campaign.log, chat.log)
4. Start devserver using `scripts/run-dev.sh` via subprocess with custom environment:
   ```python
   env = {**os.environ, "SIDESTAGE_MOCK_AGENT": "1", "SIDESTAGE_PORT": "8001"}
   subprocess.Popen([str(run_script)], cwd=str(REPO_ROOT), env=env, ...)
   ```
5. Wait for server readiness via health check polling (`/v1/entities` on port 8001)
6. Yield the base URL (`http://localhost:8001`)
7. On teardown: SIGTERM the server, wait, kill if needed

**Integration with existing devserver fixture:**
Import and reuse `server_is_running()` helper and `LogObserver` from `tests/devserver/helpers.py`. The key differences:
- Uses port 8001 instead of 8000
- Full campaign state reset with log rotation at session start
- Frontend build verification
- Always starts fresh (never reuses already-running server)
- Passes `SIDESTAGE_MOCK_AGENT=1` for mock agent support

### 3.4 Campaign Reset Fixture

**Fixture `fresh_e2e_campaign` in `tests/e2e/conftest.py` (class-scoped):**

Per test class:
1. Copy `data/dev_campaign/markdown/` to `sidestage.dev/dev/markdown/` (overwrite)
2. POST `/v1/campaign/import` with `{"action": "execute", "force": true}`
3. Assert import phase is "complete"
4. POST `/v1/campaign/reload-defaults`
5. Assert success

This mirrors the existing `fresh_campaign` fixture in `tests/devserver/conftest.py`. The default scene `campaign_planning` is assumed to exist after reset — this is a precondition for chat-related E2E tests.

### 3.5 Playwright Configuration

**Fixture `base_url`:**
Return `http://localhost:8001/sidestage` — this is where the SPA is mounted on the E2E port.

**Browser settings:**
- Chromium only
- Headless by default (override with `--headed` flag)
- Default timeout: 30 seconds for assertions
- Viewport: 1280x720

**`conftest.py` provides:**
- `page` fixture (from pytest-playwright, scoped per test)
- `e2e_client` fixture — `httpx.Client` pointed at `http://localhost:8001` for backend verification
- `log_observer` fixture — `LogObserver` for asserting backend log behavior

### 3.6 Playwright Base URL and Navigation

The SPA is served at `/sidestage/` with React Router handling client-side routes. Playwright navigates to the full URL:
- Home/default scene: `http://localhost:8001/sidestage/`
- Specific scene: `http://localhost:8001/sidestage/scenes/{sceneId}`

After navigation, wait for the app to hydrate:
- Wait for the WebSocket connection to establish (the app logs "WebSocket connection established" to console)
- Wait for entities to load (entity list appears in sidebar)

**Note on WebSocket lifecycle:** The WebSocket connection is destroyed and recreated on scene navigation (due to `currentSceneId` dependency in the useEffect). E2E tests that navigate between scenes must wait for the new WebSocket connection to establish before asserting on real-time behavior.

## 4. Mock Actor for E2E Tests

### 4.1 Design

A configurable mock LLM agent that replaces the real `LiteLLMAgent` in the NPC actors. This enables deterministic E2E testing of the chat flow without depending on an LLM.

**Class `MockLLMAgent` in `src/sidestage/testing/mock_actor.py`:**

The mock implements the same `arun()` interface as `LiteLLMAgent`. It does not replace the entire `NPCActor` — only the agent instance inside it.

Fields:
- `responses: list[MockResponse]` — queue of canned responses to return
- `default_response: str` — fallback response when queue is empty
- `response_delay: float` — simulated thinking time in seconds

```python
@dataclass
class MockResponse:
    body: str
    character_id: str | None = None
    actor_id: str = "agent:co_author"
    event_type: str = "ChatMessage"  # Must match TypeScript EventType
    delay: float = 0.5
```

**Behavior:**
1. When `arun()` is called, wait for `response_delay` seconds (simulates LLM thinking time)
2. Pop next response from queue (or use default_response)
3. Return the response in the format expected by `NPCActor.process()`

### 4.2 Integration Point

The mock agent is injected at the `NPCActor._update_prompt()` level. This method currently constructs a `LiteLLMAgent` based on LLM config. The modification:

In `NPCActor._update_prompt()` in `src/sidestage/actors.py`:
1. Check for `os.environ.get("SIDESTAGE_MOCK_AGENT")`
2. If set, create a `MockLLMAgent` instead of `LiteLLMAgent`
3. The `MockLLMAgent` implements the same interface (`arun()` method) as `LiteLLMAgent`

This is a minimal change — a single conditional at the top of `_update_prompt()` that short-circuits the real agent creation.

### 4.3 Test-Only API Endpoints

When `SIDESTAGE_MOCK_AGENT=1` is set, register additional routes in the orchestrator's FastAPI app:

- `POST /v1/test/mock-agent/configure` — set response queue, delay, etc. Traverses `orchestrator.active_scenes -> scene.characters -> character.actor.agent` to update all mock agents.
- `POST /v1/test/mock-agent/reset` — clear queue, reset to defaults
- These endpoints only exist when the mock flag is set, never in production

**Route registration:** Add a conditional in `src/sidestage/orchestrator.py`'s route setup (or in a separate `src/sidestage/testing/routes.py` imported conditionally) that checks the environment variable and adds the test routes.

## 5. E2E Test Scenarios

### 5.1 Chat Flow (Mock Agent)

**Test class: `TestChatFlow`**

Uses `fresh_e2e_campaign` fixture. Mock agent configured with known responses.

**Test: send message and receive response**
1. Navigate to `/sidestage/`
2. Configure mock agent via `POST /v1/test/mock-agent/configure` with response: `{"body": "Hello, adventurer!", "event_type": "ChatMessage"}`
3. Type "Hello" into chat input
4. Click send button (or press Enter)
5. Assert: user message bubble appears (right-aligned, purple background)
6. Assert: thinking indicator appears (bouncing dots)
7. Assert: thinking indicator disappears
8. Assert: agent response bubble appears with "Hello, adventurer!" text
9. Backend verification: `poll_scene_messages()` returns both messages

**Test: markdown rendering in responses**
1. Configure mock agent with response containing markdown (headers, bold, lists)
2. Send a message
3. Assert: response bubble contains rendered HTML (not raw markdown)

**Test: error event rendering**
1. Configure mock agent to emit response with `event_type: "Error"`
2. Send a message
3. Assert: error message appears with red styling

### 5.2 Chat Flow (Real LLM)

**Test class: `TestChatFlowLLM`**

Marked with `@pytest.mark.llm`. Skipped when LLM unavailable. This test class does NOT use the mock agent — the E2E server for this class should be started without `SIDESTAGE_MOCK_AGENT=1`.

**Test: real agent response**
1. Navigate to `/sidestage/`
2. Type a simple message (e.g., "Hello")
3. Assert: user message appears
4. Assert: thinking indicator appears
5. Wait (longer timeout, e.g., 60s) for response
6. Assert: agent response appears with non-empty text
7. Backend verification via LogObserver: verify agent log entries

### 5.3 Entity Management

**Test class: `TestEntityManagement`**

Uses `fresh_e2e_campaign` fixture.

**Test: entity list loads**
1. Navigate to `/sidestage/`
2. Assert: entity browser sidebar shows entities
3. Assert: entity count matches backend (verify via httpx GET `/v1/entities`)

**Test: entity selection and editing**
1. Navigate to `/sidestage/`
2. Click an entity in the browser
3. Assert: entity editor opens with entity content (Tiptap renders in real browser)
4. Modify text in the Tiptap editor
5. Save the entity
6. Assert: save succeeds (no error)
7. Backend verification: GET `/v1/entities/{id}/markdown` returns updated content

### 5.4 Real-Time Sync — Chat Broadcast

**Test class: `TestRealTimeSync`**

Uses `fresh_e2e_campaign` fixture and two browser contexts.

**Test: chat message appears in second client**
1. Create two browser contexts (`browser.new_context()`)
2. Navigate both to `/sidestage/`
3. Wait for WebSocket connection in both (wait for entity list to load as a proxy)
4. In context_a: type "Sync test message" and send
5. Assert context_a: user message bubble appears
6. Assert context_b: the message event appears (via WebSocket broadcast of `event` type)
7. Use Playwright's auto-retry assertion with reasonable timeout (10s)

### 5.5 Real-Time Sync — Entity List Updates

**Test class: `TestRealTimeSync`** (continued)

**Test: entity creation reflects in second client**
1. Create two browser contexts
2. Navigate both to `/sidestage/`
3. Count initial entities in both contexts
4. Via httpx client: POST to create a new test entity
5. Assert both contexts: entity list updates to include new entity (via `entities_updated` WebSocket message)
6. Via httpx client: DELETE the entity
7. Assert both contexts: entity disappears from list

### 5.6 Scene Navigation

**Test class: `TestSceneNavigation`**

**Test: navigate between scenes**
1. Navigate to `/sidestage/`
2. Assert: default scene (campaign_planning) is active — header shows scene name
3. Click a different scene in the sidebar
4. Assert: scene name updates in the header
5. Assert: chat messages reload for the new scene (wait for WebSocket reconnection)
6. Assert: URL updates to `/sidestage/scenes/{sceneId}`

### 5.7 Campaign Import

**Test class: `TestCampaignOperations`**

**Test: campaign import via UI**
1. Navigate to `/sidestage/`
2. Find and click the "Reload Defaults" button (exists in ChatWidget header)
3. Accept the confirmation dialog
4. Assert: operation succeeds (entities refresh)
5. Backend verification: entities match expected campaign data

## 6. Directory Structure

```
frontend/
  src/
    test-setup.ts                  # Vitest setup: matchers, cleanup, global mocks
    __mocks__/
      MockWebSocket.ts             # Mock WebSocket class for unit tests
    App.test.tsx                   # Route rendering tests (uses MemoryRouter)
    AppContext.test.tsx             # State/WebSocket handling tests
    ChatWidget.test.tsx            # Chat UI tests
    EntityBrowser.test.tsx         # Entity management tests (Tiptap mocked)
    Layout.test.tsx                # Layout/navigation tests
  vite.config.ts                   # Extended with test block
  tsconfig.test.json               # Test-specific TypeScript config
  package.json                     # New test deps and scripts

tests/
  e2e/
    conftest.py                    # E2E fixtures: server (port 8001), build, campaign reset
    test_chat_flow.py              # Chat send/receive E2E tests (mock + real LLM)
    test_entity_management.py      # Entity CRUD E2E tests
    test_realtime_sync.py          # Multi-client WebSocket sync tests
    test_scene_navigation.py       # Scene switching E2E tests
    test_campaign_operations.py    # Campaign import E2E tests

src/sidestage/
  testing/
    __init__.py
    mock_actor.py                  # MockLLMAgent class (replaces LiteLLMAgent)
    routes.py                      # Test-only API endpoints (conditional on SIDESTAGE_MOCK_AGENT)
```

## 7. Test Running

**Frontend unit tests:**
```bash
cd frontend && npm test          # Watch mode
cd frontend && npm run test:run  # Single run (CI)
```

**E2E tests:**
```bash
uv run pytest tests/e2e/                    # All E2E tests (mock agent, port 8001)
uv run pytest tests/e2e/ -m llm             # Only real LLM tests
uv run pytest tests/e2e/ --headed           # Headed mode for debugging
```

**All tests:**
```bash
uv run pytest tests/                        # Backend unit + integration + E2E
cd frontend && npm run test:run             # Frontend unit tests
```

## 8. Implementation Order

The implementation should follow this dependency order:

1. **Frontend unit test infrastructure** — Vitest config, tsconfig.test.json, setup file, MockWebSocket, renderWithContext helper, package.json deps
2. **Frontend component tests** — AppContext, ChatWidget, EntityBrowser (Tiptap mocked), Layout, App (MemoryRouter)
3. **E2E infrastructure** — pytest-playwright dep, conftest.py (port 8001), build fixture (with npm install check), server fixture, campaign reset fixture
4. **Mock actor** — MockLLMAgent class, test-only API routes, `_update_prompt()` conditional, `SIDESTAGE_PORT` env var support in server.py
5. **E2E test suite** — Chat flow (mock), entity management, real-time sync, scene navigation, campaign operations
6. **Real LLM E2E tests** — LLM-gated variants of chat tests (separate server without mock agent)

Each step builds on the previous, so they should be implemented in order.
