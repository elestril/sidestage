# Usage Guide — Frontend & E2E Testing (06-frontend-testing)

## Quick Start

### Unit Tests (Vitest + jsdom)

```bash
# Run all frontend unit/component tests
cd frontend && npx vitest run

# Watch mode for development
cd frontend && npx vitest

# Run with coverage
cd frontend && npx vitest run --coverage
```

### E2E Tests (Playwright)

```bash
# All E2E tests (mock agent, headless Chromium)
uv run pytest tests/e2e/ -m "e2e and not llm"

# Specific test file
uv run pytest tests/e2e/test_chat_flow.py

# Headed mode for debugging
uv run pytest tests/e2e/test_chat_flow.py --headed

# Real LLM tests only (requires live LLM backend)
uv run pytest tests/e2e/ -m llm
```

### All Tests Combined

```bash
# Backend unit + integration + E2E
uv run pytest tests/ -m "not llm"
```

## What Was Built

### Section 01: Vitest Infrastructure
- `frontend/vitest.config.ts` — Vitest config with jsdom, path aliases, coverage thresholds
- `frontend/src/test/setup.ts` — Test setup with fetch/WebSocket polyfills

### Section 02: Frontend Mocks
- `frontend/src/test/mocks/handlers.ts` — MSW request handlers for all API endpoints
- `frontend/src/test/mocks/server.ts` — MSW server setup for test environment
- `frontend/src/test/mocks/data.ts` — Realistic mock data (entities, scenes, messages)
- `frontend/src/test/renderWithProviders.tsx` — Test utility wrapping components with Router + QueryClient

### Section 03: Component Tests
- `frontend/src/components/__tests__/EntityBrowser.test.tsx` — Entity list, filtering, selection, edit/save
- `frontend/src/components/__tests__/ChatWidget.test.tsx` — Chat input, message display, reload defaults

### Section 04: E2E Infrastructure
- `tests/e2e/conftest.py` — Session-scoped server fixture (port 8001), campaign reset, log observer
- `tests/e2e/test_canary.py` — Smoke tests verifying server reachability and frontend loading
- `pytest.ini` markers: `e2e`, `llm`

### Section 05: Mock Actor
- `src/sidestage/testing/mock_actor.py` — MockLLMAgent with FIFO response queue
- `src/sidestage/testing/routes.py` — Test-only API routes for mock agent configuration
- `src/sidestage/actors.py` — Conditional mock injection via SIDESTAGE_MOCK_AGENT env var
- `tests/unit/test_mock_actor.py` — 7 unit tests
- `tests/unit/test_mock_actor_integration.py` — 3 integration tests
- `tests/unit/test_mock_actor_routes.py` — 5 route tests

### Section 06: E2E Tests
- `tests/e2e/test_chat_flow.py` — 3 mock agent tests + 1 LLM placeholder
- `tests/e2e/test_entity_management.py` — 3 entity CRUD tests
- `tests/e2e/test_realtime_sync.py` — 4 multi-client WebSocket sync tests
- `tests/e2e/test_scene_navigation.py` — 4 scene navigation tests
- `tests/e2e/test_campaign_operations.py` — 2 campaign operation tests

## Test Architecture

```
frontend/
├── vitest.config.ts              # Vitest configuration
├── src/test/
│   ├── setup.ts                  # Global test setup
│   ├── mocks/
│   │   ├── handlers.ts           # MSW API handlers
│   │   ├── server.ts             # MSW server
│   │   └── data.ts               # Mock data
│   └── renderWithProviders.tsx   # Test render utility
└── src/components/__tests__/
    ├── EntityBrowser.test.tsx     # Component tests
    └── ChatWidget.test.tsx

tests/
├── e2e/
│   ├── conftest.py               # E2E fixtures (server, campaign, scene activation)
│   ├── test_canary.py            # Smoke tests
│   ├── test_chat_flow.py         # Chat send/receive
│   ├── test_entity_management.py # Entity CRUD
│   ├── test_realtime_sync.py     # Multi-client WebSocket
│   ├── test_scene_navigation.py  # Scene switching
│   └── test_campaign_operations.py # Reload defaults
└── unit/
    ├── test_mock_actor.py        # MockLLMAgent unit tests
    ├── test_mock_actor_integration.py
    └── test_mock_actor_routes.py

src/sidestage/testing/
├── __init__.py
├── mock_actor.py                 # MockLLMAgent + MockResponse
└── routes.py                     # Test-only API routes
```

## Key Environment Variables

| Variable | Purpose |
|----------|---------|
| `SIDESTAGE_MOCK_AGENT=1` | Injects MockLLMAgent instead of real LLM |
| `SIDESTAGE_PORT=8001` | Override server port (used by E2E fixtures) |

## Mock Agent API (Test-Only)

Available when `SIDESTAGE_MOCK_AGENT=1`:

```bash
# Configure mock responses (FIFO queue)
curl -X POST http://localhost:8001/v1/test/mock-agent/configure \
  -H "Content-Type: application/json" \
  -d '{"responses": [{"body": "Hello!", "delay": 0.3}]}'

# Reset to defaults
curl -X POST http://localhost:8001/v1/test/mock-agent/reset
```
