# Code Review: Section 08 - Routes and Frontend

**Date:** 2026-02-07

## Auto-Fixes (applying without asking)

1. **Lazy import inside route handler**: Move `MigrationValidationReport` and `MigrationValidationIssue` to the top-level import block.
2. **Frontend missing error handling**: Add `else` branches for non-ok/non-409 responses in backup and execute flows.
3. **Execute phase missing 409 check**: Add explicit 409 check to the execute phase request.

## Let Go (not worth changing)

- TOCTOU race on concurrency guard: Single-worker asyncio deployment, importer handles health atomically.
- No test for broadcast after backup: Will be covered by section-09 integration tests.
- Missing test for markdown dir not found: Low-value edge case test.
- Optional validation field: Route always populates it; model optionality is correct.
