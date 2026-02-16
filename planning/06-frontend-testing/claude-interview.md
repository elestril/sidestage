# Interview Transcript: Frontend & E2E Testing Strategy

## Q1: E2E Backend Infrastructure

**Question:** For Playwright E2E tests, should they run against the existing devserver fixture (live process with real FalkorDB) or should we create a lighter in-process variant?

**Answer:** Use existing devserver, but reset the whole dev campaign state and rotate all logs as part of initializing the test fixture.

## Q2: Frontend Unit Test Layout

**Question:** For the Vitest frontend unit tests, should tests be co-located alongside components or in a separate test directory?

**Answer:** Co-located — tests next to components (e.g., `ChatWidget.tsx` + `ChatWidget.test.tsx` in same directory).

## Q3: LLM in E2E Tests

**Question:** What level of AI/LLM testing should the E2E tests include?

**Answer:** Both tiers — mock-based tests always run, real LLM tests gated by marker/environment.

## Q4: Mock Agent Approach

**Question:** For mock LLM in E2E tests, what approach should the mock agent take?

**Answer:** Configurable mock actor — a mock Actor class that can be configured per-test with expected responses, delays, and event types.

## Q5: Campaign State Reset Isolation

**Question:** For the E2E campaign state reset, should the reset happen once per test session, per test class, or per individual test?

**Answer:** Per test class — reset once per test class, tests within a class share state. Similar to existing `fresh_campaign` fixture.

## Q6: Frontend Unit Test Priority

**Question:** Which frontend components are highest priority for unit testing?

**Answer:** All equally important — build test infrastructure that covers all components from the start.

## Q7: Real-Time Sync Scenarios

**Question:** For the real-time sync E2E test, what specific sync scenarios matter most?

**Answer:** Chat message broadcast (message sent in one browser appears in the other's chat) and entity list updates (creating/deleting entities in one browser updates the list in the other).

## Q8: Browser Mode

**Question:** Should the Playwright tests run in headed or headless mode by default?

**Answer:** Headless everywhere — headless by default, can override with `--headed` for debugging.

## Q9: E2E Server Architecture

**Question:** How should the frontend be served for E2E tests?

**Answer:** Use a dedicated test-managed server (extending the devserver fixture pattern). The E2E tests manage their own FastAPI server serving the built frontend from `dist/`.

## Q10: Frontend Build Step

**Question:** Should the test fixture auto-build dist/ if it's missing/stale, or should it be a prerequisite?

**Answer:** Auto-build if needed — fixture runs `npm run build` in `frontend/` if `dist/` doesn't exist or is older than source files.

## Q11: Browser Requirements

**Question:** Which browsers should Playwright test against?

**Answer:** Chromium only — fastest, most reliable. Cross-browser testing adds complexity for little benefit in an internal tool.
