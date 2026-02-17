# Code Review Interview: Section 06 - E2E Test Scenarios

**Date:** 2026-02-16

## Auto-Fixes

1. **Fix `self._base` crash bug** — `TestRealTimeSyncEntities._setup` doesn't set `self._base`, causing AttributeError. Adding it.

2. **Move `_activate_scene` to conftest** — Duplicated across 3 test files. Moving to `tests/e2e/conftest.py` as a fixture.

3. **Add mock agent reset fixture** — Using a yield fixture to guarantee cleanup even on test failure.

4. **Tighten URL assertion** — Remove the overly loose `or "/scenes" in page.url` fallback.

5. **Add missing `test_entity_created_via_api_appears_in_both_clients`** — Add the test from the plan, using reload-defaults approach.

## Let Go

6. **`test_error_event_rendering`** — Cannot work because MockLLMAgent doesn't plumb event_type through to NPCActor.process(). NPCActor always creates responses with EventType.CHAT_MESSAGE. This is a known design limitation noted in section 05 notes. Would require MockLLMAgent changes that are out of scope.

7. **Minor concerns** — init message pollution, wait_for_timeout usage, LLM test placeholders, CSS selector brittleness. All acceptable for E2E test context.
