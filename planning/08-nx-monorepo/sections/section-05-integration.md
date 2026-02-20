# Section 05: Integration and Cleanup

## Goal
Update agent-project.json, verify cross-cutting Nx commands, commit everything.

## Files to Modify

### `agent-project.json`
Change build command:
```diff
-    "build": "bash -c 'cd frontend && npm run build'"
+    "build": "npx nx build frontend"
```

## Acceptance Criteria
- `npx nx run-many --target=test` runs tests for both frontend and backend
- `npx nx run-many --target=lint` lints both frontend and backend
- `npx nx affected --target=test` correctly detects affected projects
- Gateway MCP `run_build` works after reconnect (builds frontend via Nx)
- Existing `uv run pytest` and `npm run build` still work independently
- All changes committed
