# Code Review: Section 08 - Routes and Frontend

The implementation is largely faithful to the plan. Both backend routes and frontend buttons are present with correct logic. However, there are several issues ranging from moderate to low severity.

**MODERATE: Frontend does not handle non-ok, non-409 responses (silent failures)**

In `frontend/src/EntityBrowser.tsx`, the backup flow only handles `response.status === 409` and `response.ok`. If the server returns a 500 or any other error status, the function silently does nothing. The same problem exists in the execute phase: if `executeResponse` is not ok and not 409, the user sees nothing.

**MODERATE: Execute phase does not handle 409 from the second request**

The Phase 2 execute request does not check for a 409 status code. While unlikely in practice, a concurrent operation could start between the validate and execute calls.

**MODERATE: No test for WebSocket broadcast after backup (Acceptance Criterion 7)**

The plan's acceptance criteria item 7 states: "After successful backup, entities_updated is broadcast by the route handler." The backup route does call `sync_manager.broadcast`, but the test does not assert that it was called.

**LOW: Concurrency guard is not atomic (TOCTOU race)**

The health status check is a simple if-statement with no locking. Two simultaneous import requests could both pass the check. In a single-worker uvicorn deployment this is less likely, but the window exists.

**LOW: Missing test for markdown directory not found**

The implementation handles the missing markdown directory correctly, but there is no test for this case.

**LOW: Import response model `validation` field is Optional but always present**

The frontend code accesses `validateResult.validation.valid` without null-checking. If validation were ever null, this would cause a runtime TypeError.

**COSMETIC: Lazy import inside route handler**

`MigrationValidationReport` and `MigrationValidationIssue` are imported inside the route handler for the markdown-directory-missing case, but should be imported at the module level alongside the other migration model imports.
