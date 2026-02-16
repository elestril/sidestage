# Spec: Integrated Frontend & E2E Testing Strategy

## Overview

Sidestage is a real-time, AI-enhanced tabletop RPG campaign manager with a Python/FastAPI backend and React 19 SPA frontend. The frontend currently has zero tests. This project adds two testing layers:

1. **Frontend Unit Tests** — Vitest + React Testing Library for isolated component testing
2. **E2E Tests** — Playwright (via pytest-playwright) for full-stack browser-based tests

## Goals

- Every frontend component (`AppContext`, `ChatWidget`, `EntityBrowser`, `Layout`, `App`) gets unit test coverage
- E2E tests validate critical user journeys: chat flow, entity management, real-time sync
- Mock LLM tests always run; real LLM tests gated by `@pytest.mark.llm`
- Test infrastructure is reusable and follows existing codebase conventions

## Architecture Decisions

### Frontend Unit Tests

- **Framework:** Vitest with jsdom environment
- **Library:** React Testing Library + `@testing-library/jest-dom`
- **Location:** Co-located with components (`ChatWidget.test.tsx` next to `ChatWidget.tsx`)
- **Config:** Extend existing `vite.config.ts` with test block, plus setup file for matchers/cleanup
- **Mocking:** `vi.fn()` for fetch, custom mock class for WebSocket

### E2E Tests

- **Framework:** pytest-playwright (Python-side Playwright integration)
- **Location:** `tests/e2e/` directory, separate from existing `tests/devserver/`
- **Server:** Extends existing devserver fixture pattern — manages own FastAPI server serving built `frontend/dist/`
- **Build:** Auto-builds `frontend/dist/` if missing or stale (compares mtime against source)
- **Browser:** Chromium only, headless by default
- **Campaign Reset:** Per test class, similar to existing `fresh_campaign` fixture — restores dev campaign markdown, re-imports, rotates logs

### Mock Actor

- Configurable mock Actor class for E2E tests without real LLM
- Can be configured per-test with canned responses, delays, and event types
- Replaces real agent in the Actor registry during mock tests
- Real LLM tests use `@pytest.mark.llm` and are skipped when LLM unavailable

### Real-Time Sync Tests

- Two Playwright browser contexts connected simultaneously
- Test chat message broadcast: send in one, appears in the other
- Test entity list updates: create/delete entity in one, list updates in the other
- Use Playwright's built-in auto-retry assertions for timing

## Non-Goals

- Cross-browser testing (Chromium only)
- Visual regression testing
- Performance/load testing
- Mobile responsive testing

## Dependencies to Add

**Python (`pyproject.toml`):**
- `pytest-playwright`

**Frontend (`frontend/package.json`):**
- `vitest` (dev)
- `@testing-library/react` (dev)
- `@testing-library/jest-dom` (dev)
- `@testing-library/user-event` (dev)
- `jsdom` (dev)

## Existing Infrastructure to Leverage

- `tests/devserver/conftest.py` — devserver lifecycle, httpx client, LogObserver, fresh_campaign
- `tests/devserver/helpers.py` — LogObserver, poll_scene_messages, server_is_running
- Root `conftest.py` — SidestageConfig init, OTEL reset, RequestContext cleanup
- `scripts/run-dev.sh` — dev server startup script
- Frontend Vite proxy config — `/v1` proxied to `localhost:8000` with WebSocket support
