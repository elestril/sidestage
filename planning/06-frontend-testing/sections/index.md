<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-vitest-infrastructure
section-02-frontend-mocks
section-03-component-tests
section-04-e2e-infrastructure
section-05-mock-actor
section-06-e2e-tests
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-vitest-infrastructure | - | 02, 03 | Yes |
| section-02-frontend-mocks | 01 | 03 | No |
| section-03-component-tests | 02 | - | No |
| section-04-e2e-infrastructure | - | 05, 06 | Yes |
| section-05-mock-actor | 04 | 06 | No |
| section-06-e2e-tests | 05 | - | No |

## Execution Order

1. section-01-vitest-infrastructure, section-04-e2e-infrastructure (parallel, no dependencies)
2. section-02-frontend-mocks (after 01)
3. section-03-component-tests, section-05-mock-actor (parallel: 03 after 02, 05 after 04)
4. section-06-e2e-tests (after 05)

## Section Summaries

### section-01-vitest-infrastructure
Vitest configuration, package.json deps, tsconfig.test.json, setup file, npm scripts. Produces a working `npm test` that can find and run a canary test.

### section-02-frontend-mocks
MockWebSocket class, fetch mock helpers, renderWithContext test helper, marked mock setup. Provides the testing utilities needed by all component tests.

### section-03-component-tests
All frontend component test files: AppContext.test.tsx, ChatWidget.test.tsx, EntityBrowser.test.tsx, Layout.test.tsx, App.test.tsx. Uses MemoryRouter for route tests, mocks Tiptap for EntityBrowser.

### section-04-e2e-infrastructure
pytest-playwright dependency, tests/e2e/conftest.py with server fixture (port 8001 with fallback), frontend build fixture (npm install + build), campaign reset fixture, Playwright configuration. Produces a working `uv run pytest tests/e2e/` that can run a canary E2E test.

### section-05-mock-actor
MockLLMAgent class, test-only API routes (/v1/test/mock-agent/configure, /v1/test/mock-agent/reset), NPCActor._update_prompt() conditional, SIDESTAGE_PORT env var support.

### section-06-e2e-tests
All E2E test files: test_chat_flow.py (mock + real LLM), test_entity_management.py, test_realtime_sync.py (multi-context WebSocket tests), test_scene_navigation.py, test_campaign_operations.py.
