# Code Review Interview: Section 05 - Mock Actor

**Date:** 2026-02-16

## Auto-Fixes (no discussion needed)

1. **Add missing test** - `test_endpoints_return_404_when_mock_agent_not_set` was in the plan but missing from implementation. Adding it.

2. **Fix log message ordering** - `server.py` logged `args.port` before the SIDESTAGE_PORT override was applied. Moving port resolution before the log line.

3. **Remove unused import** - `field` imported from `dataclasses` in `mock_actor.py` but never used.

4. **Type annotation** - `self.agent` typed as `LiteLLMAgent | None` but MockLLMAgent is duck-typed, not a subclass. Adding `# type: ignore[assignment]` on the assignment line since this is intentional and test-only.

## Let Go

5. **Input validation on test routes** - Routes are test-only and gated behind SIDESTAGE_MOCK_AGENT env var. Not worth adding validation complexity.

6. **pop(0) performance** - O(n) list pop for a test mock with a handful of responses is irrelevant.
