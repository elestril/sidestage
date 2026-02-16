# TDD Plan: Frontend & E2E Testing Strategy

This document mirrors the structure of `claude-plan.md` and defines what tests to write BEFORE implementing each section. Since this project is itself about creating test infrastructure, the TDD approach here focuses on validating infrastructure correctness before writing the actual application tests.

## Testing Conventions

**Python (pytest):** Follow existing project patterns in `tests/`. Use `@pytest.mark.anyio` for async tests, `@pytest.mark.llm` for LLM-dependent tests. Fixtures in `conftest.py`. Test files named `test_*.py`.

**Frontend (Vitest):** Co-located `*.test.tsx` files. Use `@testing-library/react` for rendering, `@testing-library/user-event` for interactions. All `userEvent` calls are async.

---

## 2. Frontend Unit Testing Infrastructure

### 2.1 Vitest Configuration

**Tests before implementation:**
```
# Test: Vitest can find and run a trivial test file (canary test)
# Test: globals mode works (describe/it/expect available without imports)
# Test: jsdom environment is active (document and window exist)
# Test: setup file runs (jest-dom matchers like .toBeInTheDocument() work)
# Test: afterEach cleanup runs (component unmount between tests)
```

### 2.2 TypeScript Configuration

```
# Test: TypeScript compiles test files without errors (vitest/globals types resolve)
# Test: test files can import .tsx components without type errors
```

### 2.3 Mocking Strategy

**MockWebSocket tests:**
```
# Test: MockWebSocket constructor stores URL and protocol
# Test: MockWebSocket.send() records sent messages
# Test: MockWebSocket.close() sets readyState to CLOSED
# Test: simulateOpen() calls onopen handler and sets readyState to OPEN
# Test: simulateMessage(data) calls onmessage with MessageEvent containing data
# Test: simulateClose() calls onclose handler
# Test: multiple listeners via addEventListener work
```

**Fetch mock tests:**
```
# Test: fetch mock intercepts calls and returns configured responses
# Test: fetch mock can match by URL path (/v1/entities, /v1/scenes, etc.)
# Test: unmocked fetch calls throw or return a clear error (not silently succeed)
```

**renderWithContext helper tests:**
```
# Test: renderWithContext wraps component in AppProvider
# Test: renderWithContext pre-mocks mount-time fetches (/v1/scenes, /v1/entities, /v1/tracing/status)
# Test: renderWithContext creates MockWebSocket and auto-opens it
# Test: custom mock data can be passed to override defaults
```

### 2.4 Component Tests

**AppContext.test.tsx:**
```
# Test: mount triggers fetch to /v1/scenes
# Test: mount triggers fetch to /v1/entities
# Test: mount triggers fetch to /v1/tracing/status
# Test: mount creates WebSocket connection to ws://localhost/v1/ws
# Test: sendMessage() POSTs to /v1/chat with { message, scene_id }
# Test: saveEntityMarkdown() POSTs to /v1/entities/{id}/markdown
# Test: saveEntity() POSTs to /v1/entities/{id} with data
# Test: WebSocket entities_updated message triggers loadEntities()
# Test: WebSocket event message for current scene adds to messages state
# Test: WebSocket event message for different scene is ignored
# Test: WebSocket actor_status thinking adds to thinkingActors set
# Test: WebSocket actor_status idle removes from thinkingActors set
# Test: WebSocket scene_updated triggers loadScenes()
# Test: WebSocket entity_content_sync notifies registered listeners
# Test: scene change triggers loadMessages for new scene
# Test: tracingError state set when /v1/tracing/status returns error
```

**ChatWidget.test.tsx:**
```
# Test: renders message bubbles for each message in context
# Test: user messages (actor_id='user') have right-aligned purple styling
# Test: NPC messages show character name header
# Test: NPC messages for unseen characters show "(Unseen)" badge
# Test: JoinEvent renders as centered system text
# Test: LeaveEvent renders as centered system text
# Test: AdjustGametime renders as centered system text
# Test: Error event renders with red border and error styling
# Test: message body is rendered through marked (HTML output, not raw markdown)
# Test: thinking indicator (bouncing dots) appears for actors in thinkingActors set
# Test: thinking indicator shows character name
# Test: form submit calls sendMessage with input text
# Test: input clears after successful submit
# Test: empty/whitespace-only input does not trigger sendMessage
# Test: send button is disabled when input is empty
# Test: entity widget renders when metadata.widget.type === 'entity'
# Test: entity widget shows entity type, name, and description
# Test: clicking entity widget opens EntityModal (sets selectedEntityId)
# Test: gametime displays as "Day N, HH:MM:SS" format
# Test: null gametime renders empty string
```

**EntityBrowser.test.tsx:**
```
# Test: renders entity list from context
# Test: entity type filter shows available types
# Test: selecting a type filter updates displayed entities
# Test: clicking an entity selects it
# Test: save triggers saveEntityMarkdown with entity id and content
# Test: EntityModal renders when entityId prop is set
# Test: EntityModal calls onClose when dismissed
# Note: Tiptap editor is mocked in unit tests — editor interaction tests are E2E only
```

**Layout.test.tsx:**
```
# Test: header renders campaign/scene name
# Test: sidebar renders scene list from context
# Test: clicking a scene calls setCurrentSceneId
# Test: active scene is visually highlighted
```

**App.test.tsx:**
```
# Test: renders without crashing (uses MemoryRouter with /sidestage/)
# Test: default route shows main view with ChatWidget and EntityBrowser
# Test: /sidestage/scenes/:sceneId route renders with correct scene
# Note: uses MemoryRouter, not BrowserRouter
```

---

## 3. E2E Testing Infrastructure

### 3.1 Python Dependencies

```
# Test: pytest-playwright is importable
# Test: playwright chromium binary is installed (playwright install check)
# Test: e2e marker is registered in pytest.ini_options
```

### 3.2 Frontend Build Fixture

```
# Test: fixture detects missing node_modules/ and runs npm install
# Test: fixture detects missing dist/ and runs npm build
# Test: fixture detects stale dist/ (src newer) and rebuilds
# Test: fixture skips build when dist/ is up-to-date
# Test: fixture fails with clear error if npm is not found
# Test: fixture fails with clear error if build command fails
```

### 3.3 E2E Server Fixture

```
# Test: server starts on port 8001 (or finds available port)
# Test: server passes SIDESTAGE_MOCK_AGENT=1 env var
# Test: server waits for readiness before yielding
# Test: server tears down cleanly on session end (SIGTERM + wait)
# Test: server does not reuse already-running instance
# Test: campaign markdown is restored before server start
# Test: log files are rotated before server start
```

### 3.4 Campaign Reset Fixture

```
# Test: fresh_e2e_campaign restores markdown from data/dev_campaign/
# Test: fresh_e2e_campaign calls /v1/campaign/import with force=true
# Test: fresh_e2e_campaign calls /v1/campaign/reload-defaults
# Test: fixture is class-scoped (runs once per test class)
```

### 3.5-3.6 Playwright Configuration

```
# Test: base_url points to correct port and /sidestage path
# Test: Chromium browser launches in headless mode by default
# Test: page fixture is available in test functions
# Test: e2e_client fixture returns httpx.Client on correct port
```

---

## 4. Mock Actor

### 4.1 MockLLMAgent

```
# Test: MockLLMAgent.arun() returns next response from queue
# Test: MockLLMAgent.arun() uses default_response when queue is empty
# Test: MockLLMAgent.arun() waits response_delay before returning
# Test: MockLLMAgent.arun() returns response with correct event_type
# Test: MockLLMAgent.arun() returns response with correct actor_id
# Test: MockResponse defaults: event_type="ChatMessage", delay=0.5
```

### 4.2 Integration Point

```
# Test: NPCActor._update_prompt() creates MockLLMAgent when SIDESTAGE_MOCK_AGENT=1
# Test: NPCActor._update_prompt() creates LiteLLMAgent when env var not set
# Test: mock agent processes chat messages and returns canned response
```

### 4.3 Test-Only API Endpoints

```
# Test: POST /v1/test/mock-agent/configure sets response queue
# Test: POST /v1/test/mock-agent/reset clears response queue
# Test: test endpoints return 404 when SIDESTAGE_MOCK_AGENT not set
# Test: configure endpoint reaches into active scenes to update mock agents
```

---

## 5. E2E Test Scenarios

### 5.1 Chat Flow (Mock Agent)

```
# Test: sending a message creates user bubble (right-aligned)
# Test: after sending, thinking indicator appears
# Test: thinking indicator disappears after mock response
# Test: mock agent response appears as NPC bubble
# Test: response markdown is rendered as HTML
# Test: error event_type response renders with error styling
# Test: backend poll_scene_messages confirms both messages stored
```

### 5.2 Chat Flow (Real LLM)

```
# Test: (llm marker) real agent response appears after sending message
# Test: (llm marker) response is non-empty text
# Test: (llm marker) LogObserver confirms agent activity in logs
```

### 5.3 Entity Management

```
# Test: entity list loads and matches backend entity count
# Test: clicking entity opens editor with content
# Test: editing and saving entity updates backend data
```

### 5.4 Real-Time Sync — Chat Broadcast

```
# Test: message sent in context_a appears in context_b (WebSocket broadcast)
# Test: both contexts show the same message content
```

### 5.5 Real-Time Sync — Entity List Updates

```
# Test: entity created via API appears in both browser contexts
# Test: entity deleted via API disappears from both browser contexts
```

### 5.6 Scene Navigation

```
# Test: default scene (campaign_planning) is active on load
# Test: clicking different scene updates header name
# Test: scene switch reloads chat messages
# Test: URL updates to /sidestage/scenes/{sceneId}
```

### 5.7 Campaign Operations

```
# Test: reload defaults button triggers confirmation dialog
# Test: accepting confirmation reloads entities
```
