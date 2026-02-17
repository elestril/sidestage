# Code Review: Section 04 - E2E Infrastructure

## High Severity

### 1. Server starts with `reload=True` -- E2E tests will be flaky
The server's `main()` calls `uvicorn.run()` with `reload=True`. The E2E conftest launches the server via `sys.executable, "-m", "sidestage.server"`, which triggers `main()`. This means uvicorn spawns a child worker process, and `process.send_signal(signal.SIGTERM)` on teardown may leave orphan workers. If source files change during tests, the server will restart mid-test.

### 2. PID file collision with dev instance
The E2E server shares `sidestage.dev/` working directory with the dev instance. The conftest deletes PID files, which could corrupt the dev instance's state. A race condition exists if both are running.

### 3. Port collision / shared data directory
Even with different ports (8000 vs 8001), both servers would share the same `sidestage.dev/` directory, FalkorDB instance, and SQLite files. Concurrent writes will cause data corruption.

## Medium Severity

### 4. Unrelated diff hunks included
Changes to `frontend/tsconfig.app.json` and `frontend/vite.config.ts` are not in the section 4 plan -- they fix issues from sections 01-03.

### 5. No `_check_server_errors` autouse fixture
The devserver conftest has an autouse fixture that fails tests when the server emits ERROR-level log entries. The E2E conftest does not replicate this safety net.

### 6. No `pytest_collection_modifyitems` for `e2e` marker auto-skip
No graceful skip when Playwright/Chromium is not available. Running `pytest` without filtering will fail loudly at fixture setup.

### 7. stdout/stderr PIPE deadlock risk
Server process has `stdout=subprocess.PIPE, stderr=subprocess.PIPE` but output is never read during normal operation. Long-running E2E sessions could deadlock if pipe buffers fill up.

### 8. Stale dist detection uses wrong mtime
`dist_dir.stat().st_mtime` gets directory mtime, not file mtime. Should use `dist_index.stat().st_mtime` or newest file within dist/.

## Low Severity

### 9. `sys.modules.setdefault` vs `sys.modules[...]` inconsistency
### 10. No timeout marker on canary tests
### 11. `_init_config` autouse fixture from root conftest interference potential
