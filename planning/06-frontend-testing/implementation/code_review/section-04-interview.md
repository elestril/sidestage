# Code Review Interview: Section 04 - E2E Infrastructure

**Date:** 2026-02-16

## Items Discussed with User

### 1. Server reload=True (High #1)
**Issue:** Server always starts with `reload=True`, causing watcher/worker process complications for E2E tests.
**User response:** The `--dev` flag is part of the project plan but not yet implemented. Add `--no-reload` flag for now.
**Resolution:** Added `--no-reload` CLI argument to server.py. E2E fixture passes it.

### 2. Shared sidestage.dev/ directory (High #2 + #3)
**Issue:** E2E tests share working directory with dev instance, risking PID file collision and data corruption.
**User response:** Use `sidestage.e2e/` as a separate working directory.
**Resolution:** Changed E2E_DIR from `sidestage.dev/` to `sidestage.e2e/`. Added to `.gitignore`.

## Auto-fixes Applied

### 3. Stale dist detection mtime (Medium #8)
Changed `dist_dir.stat().st_mtime` to `dist_index.stat().st_mtime` for correct freshness comparison.

### 4. sys.modules.setdefault inconsistency (Low #9)
Changed to `sys.modules[_spec.name] = _helpers` to match devserver conftest pattern.

### 5. stdout/stderr PIPE deadlock risk (Medium #7)
Changed from `stdout=subprocess.PIPE, stderr=subprocess.PIPE` to writing to `sidestage.e2e/server_stdout.log` with `stderr=subprocess.STDOUT`. Output is still available on failure for diagnostics.

## Items Let Go

- **#4 Unrelated diff hunks:** The tsconfig/vite fixes are needed for the build to work — they fix issues discovered during this section.
- **#5 No _check_server_errors fixture:** Useful but not required for infrastructure section. Can add in section 06 when actual E2E tests need it.
- **#6 No e2e marker auto-skip:** Users run E2E tests specifically, not accidentally. pytest.fail at fixture setup is acceptable.
- **#10 No timeout marker:** Default pytest-timeout is sufficient for canary tests.
- **#11 _init_config interference:** Acknowledged as harmless — E2E tests use out-of-process server.
