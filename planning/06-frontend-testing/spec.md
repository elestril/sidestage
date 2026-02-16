# Proposal: Integrated Frontend & E2E Testing Strategy

This proposal outlines a multi-layered testing strategy for Sidestage, ensuring frontend components are robust and the full system (Frontend + Backend + Graph + AI) works in harmony.

## 1. Frontend Unit & Component Testing
We will use **Vitest** and **React Testing Library** for high-speed, isolated testing of UI components and logic.

*   **Tooling:** `vitest`, `@testing-library/react`, `jsdom`.
*   **Location:** `frontend/src/` (alongside components, e.g., `ChatWidget.test.tsx`).
*   **Scope:**
    -   **Component Rendering:** Ensure components render correctly with various props.
    -   **Local State Logic:** Test hooks and state transitions in `AppContext.tsx`.
    -   **Markdown Rendering:** Verify `marked` and `tiptap` integration.
    -   **Mocks:** Mock `fetch` and `WebSocket` for isolated component tests.

## 2. Development Mode (`--dev` Flag)
The `sidestage` command supports a `--dev` flag designed for rapid iteration. Testing should account for this mode:

- **Hot Reloading:** Uvicorn runs with `reload=true`, monitoring backend changes.
- **Frontend Source Sync:** The frontend is served directly from source (leveraging Vite's dev server or similar), ensuring UI changes are reflected immediately without a full build step.
- **MCP Integration:** MCP is enabled by default in dev mode, with pre-configured integrations for Gemini and Claude agents to allow for seamless tool-based interaction during development.

## 3. Integrated E2E Testing (The "Devserver" Bridge)
To ensure the frontend fully implements the spec and works with the backend, we will use **Playwright** integrated into the existing **pytest** suite.

*   **Tooling:** `pytest-playwright`.
*   **Integration Point:** `tests/devserver/conftest.py`.
*   **Workflow:**
    1.  **Frontend Readiness:** For CI/Production tests, a pre-test step ensures `frontend/dist` is populated. For local development tests, it can optionally use the `--dev` mode's source-serving capability.
    2.  **Start Devserver:** Reuse the `devserver` fixture to launch the FastAPI app (which serves the SPA at `/sidestage`).
    3.  **UI Interaction:** Use Playwright (in Python) to drive the browser.
    4.  **Cross-Validation:** Use the existing `httpx` `client` and `LogObserver` to verify backend side-effects while interacting with the UI.

### Example Test Scenario: "Scene Chat & Agent Response"
1.  Playwright navigates to `/sidestage/scenes/default`.
2.  Playwright types "Hello" into the `ChatWidget` and presses Enter.
3.  **UI Check:** Verify a user message bubble appears.
4.  **Backend Check:** Use `LogObserver` to verify the agent was triggered.
5.  **E2E Check:** Wait for the "thinking indicator" to appear and disappear in the UI.
6.  **E2E Check:** Verify the agent's response bubble appears with expected Markdown.

## 4. Implementation Plan

### Phase A: Infrastructure (Python/Root)
1.  **Add Dependencies:** Add `pytest-playwright` to `pyproject.toml`.
2.  **Update `conftest.py`:**
    -   Add support for testing against the `--dev` mode.
    -   Add a `frontend_dist` fixture that runs `npm run build` if `dist` is missing or stale (for non-dev tests).
    -   Configure the Playwright `base_url` to match the `devserver` fixture (`http://localhost:8000/sidestage`).
3.  **Create `tests/e2e/`:** A dedicated home for full-stack user journey tests.

### Phase B: Frontend Unit Setup (Frontend)
1.  **Add Dependencies:** Add `vitest`, `jsdom`, and testing libraries to `frontend/package.json`.
2.  **Configure Vitest:** Create `frontend/vitest.config.ts`.
3.  **Add Scripts:** Add `"test": "vitest"` to `frontend/package.json`.

### Phase C: Initial Test Suite
1.  **E2E - Campaign Import:** Test the "Import Campaign" button in the Entity Browser, verifying the confirmation dialog and final success state.
2.  **E2E - Real-time Sync:** Open two Playwright browser contexts and verify that typing in the Entity Editor in one reflects in the other via WebSockets.
3.  **E2E - MCP Integration:** Verify that the MCP endpoint is reachable and tools are discoverable when running in `--dev` mode.
4.  **Unit - Chat Parsing:** Test that `ChatWidget` correctly handles different event types (Chat, System, Error).

## Next Steps
- [ ] Install `pytest-playwright` and initialize browsers.
- [ ] Configure Vitest in the `frontend/` directory.
- [ ] Implement the first E2E test for Scene Navigation using the `--dev` infrastructure.
