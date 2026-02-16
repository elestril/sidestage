I now have all the context I need. Let me produce the section content.

# Section 4: E2E Infrastructure

## Overview

This section sets up the end-to-end testing infrastructure using Playwright (via `pytest-playwright`) and pytest. The goal is to produce a working `uv run pytest tests/e2e/` command that can discover and run a canary E2E test against a fully built and running Sidestage instance on port 8001.

This section has **no dependencies** on sections 01-03 (the Vitest/frontend unit test infrastructure). It **blocks** section 05 (Mock Actor) and section 06 (E2E Tests).

## Background

Sidestage already has a devserver test pattern in `tests/devserver/conftest.py` that manages a server lifecycle, provides an httpx client, and includes a `LogObserver` for asserting on log files. The E2E infrastructure follows the same pattern but with key differences:

- Uses port **8001** (not 8000) to avoid conflicts with the dev instance
- Always starts a **fresh** server (never reuses an already-running instance)
- Performs a **full campaign state reset** with log rotation at session start
- Requires the **frontend to be built** (`frontend/dist/`) before the server starts
- Passes `SIDESTAGE_MOCK_AGENT=1` environment variable for mock agent support (used in section 05)
- Integrates with **Playwright** for browser-based testing

The existing server at `/home/harald/src/sidestage/src/sidestage/server.py` accepts `--port` as a CLI argument (default 8000). The startup script `scripts/run-dev.sh` does not forward a port argument, so the E2E fixture will invoke `uv run sidestage` directly rather than using the shell script.

The existing helpers at `/home/harald/src/sidestage/tests/devserver/helpers.py` provide `LogObserver`, `server_is_running()`, and `poll_scene_messages()` -- all of which are reusable in E2E tests.

## Tests First

The following tests validate that the E2E infrastructure is correctly set up. These are not traditional unit tests -- they are canary/smoke tests that verify the fixtures and configuration work. Some are expressed as fixture behavior specifications rather than runnable test files, since fixtures are tested implicitly by the tests that use them.

### Canary E2E Test

Create file: `/home/harald/src/sidestage/tests/e2e/test_canary.py`

```python
"""Canary test to verify E2E infrastructure works end-to-end."""

import pytest


@pytest.mark.e2e
class TestCanary:
    """Minimal test that verifies the E2E server starts and Playwright can connect."""

    def test_server_is_reachable(self, e2e_client):
        """The e2e_client fixture provides an httpx.Client on port 8001."""
        resp = e2e_client.get("/v1/entities")
        assert resp.status_code == 200

    def test_frontend_loads(self, page, e2e_server):
        """Playwright can navigate to the SPA and the page loads."""
        page.goto(f"{e2e_server}/sidestage/")
        # The app should render something -- wait for any content
        page.wait_for_selector("body", timeout=10000)
        assert "sidestage" in page.url.lower() or page.title() != ""

    def test_frontend_has_content(self, page, e2e_server):
        """The SPA renders actual application content (not a blank page)."""
        page.goto(f"{e2e_server}/sidestage/")
        # Wait for the React app to hydrate -- look for the entity list
        # or any substantive DOM element
        page.wait_for_selector("[data-testid], main, .app, #root *", timeout=15000)
```

### Infrastructure Validation Tests (Fixture Behavior)

These describe the expected behavior of each fixture. They are validated implicitly when the canary test runs, and explicitly in the specifications below.

```
# pytest-playwright dependency
- pytest-playwright is importable (import pytest; import playwright)
- playwright chromium binary is installed
- e2e marker is registered in pytest.ini_options

# Frontend build fixture (frontend_dist)
- Detects missing node_modules/ and runs npm install
- Detects missing dist/ and runs npm build
- Detects stale dist/ (src newer than dist) and rebuilds
- Skips build when dist/ is up-to-date
- Fails with clear error if npm is not found
- Fails with clear error if build command fails

# E2E server fixture (e2e_server)
- Server starts on port 8001 (or finds next available port)
- Server passes SIDESTAGE_MOCK_AGENT=1 env var
- Server waits for readiness before yielding
- Server tears down cleanly on session end (SIGTERM + wait)
- Server does not reuse already-running instance
- Campaign markdown is restored before server start
- Log files are rotated before server start

# Campaign reset fixture (fresh_e2e_campaign)
- Restores markdown from data/dev_campaign/
- Calls /v1/campaign/import with force=true
- Calls /v1/campaign/reload-defaults
- Is class-scoped (runs once per test class)

# Playwright configuration
- base_url points to correct port and /sidestage path
- Chromium browser launches in headless mode by default
- page fixture is available in test functions
- e2e_client fixture returns httpx.Client on correct port
```

## Implementation

### Step 1: Add pytest-playwright Dependency

Modify file: `/home/harald/src/sidestage/pyproject.toml`

Add `pytest-playwright` to the `dev` dependency group:

```toml
[dependency-groups]
dev = [
    "pytest (>=9.0.2,<10.0.0)",
    "pyright (>=1.1.408,<2.0.0)",
    "types-pyyaml (>=6.0.12.20250915,<7.0.0.0)",
    "httpx (>=0.28.1,<0.29.0)",
    "mcp-server-git (>=2026.1.14,<2027.0.0)",
    "pytest-timeout (>=2.4.0,<3.0.0)",
    "anyio[trio] (>=4.9.0,<5.0.0)",
    "pytest-anyio (>=0.0.0)",
    "uv (>=0.10.0,<0.11.0)",
    "pdoc (>=15.0.0,<16.0.0)",
    "pytest-playwright",
]
```

Add the `e2e` marker to `pytest.ini_options`:

```toml
[tool.pytest.ini_options]
pythonpath = "src"
testpaths = ["tests"]
markers = [
    "llm: tests requiring a live LLM instance at localhost:8080",
    "e2e: end-to-end browser tests requiring Playwright",
]
```

After modifying `pyproject.toml`, run:

```bash
cd /home/harald/src/sidestage && uv sync
uv run playwright install chromium
```

### Step 2: Create the E2E conftest.py

Create file: `/home/harald/src/sidestage/tests/e2e/__init__.py` (empty)

Create file: `/home/harald/src/sidestage/tests/e2e/conftest.py`

This is the core of this section. The conftest provides these fixtures:

1. **`frontend_dist`** (session-scoped) -- ensures the frontend is built
2. **`e2e_server`** (session-scoped) -- starts the Sidestage server on port 8001
3. **`fresh_e2e_campaign`** (class-scoped) -- resets campaign state per test class
4. **`e2e_client`** (session-scoped) -- httpx.Client for backend verification
5. **`log_observer`** (function-scoped) -- LogObserver for log assertions

Below is the implementation structure with key logic described.

```python
"""Fixtures for end-to-end Playwright tests.

Session-scoped fixtures build the frontend, start a Sidestage server on port 8001,
and provide an httpx client. Class-scoped fixtures reset campaign state.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

# ---------------------------------------------------------------------------
# Import helpers from devserver (LogObserver, server_is_running, poll_scene_messages)
# ---------------------------------------------------------------------------
import importlib.util

_helpers_path = Path(__file__).resolve().parent.parent / "devserver" / "helpers.py"
_spec = importlib.util.spec_from_file_location("tests.devserver.helpers", _helpers_path)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules.setdefault(_spec.name, _helpers)
_spec.loader.exec_module(_helpers)

LogObserver = _helpers.LogObserver
server_is_running = _helpers.server_is_running

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEVSERVER_DIR = REPO_ROOT / "sidestage.dev"
FRONTEND_DIR = REPO_ROOT / "frontend"
CAMPAIGN_NAME = "dev"

DEV_CAMPAIGN_SOURCE = REPO_ROOT / "data" / "dev_campaign"
CAMPAIGN_MARKDOWN_DIR = DEVSERVER_DIR / CAMPAIGN_NAME / "markdown"

DEFAULT_E2E_PORT = 8001


def _find_available_port(start: int = DEFAULT_E2E_PORT, max_attempts: int = 10) -> int:
    """Find an available TCP port starting from *start*.

    Tries to bind a socket to each port in sequence. Returns the first
    port that is available. Raises RuntimeError if none found.
    """
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No available port found in range {start}-{start + max_attempts - 1}"
    )


def _log_files(base_dir: Path, campaign: str = CAMPAIGN_NAME) -> dict[str, Path]:
    """Return the standard log file paths for a given base directory."""
    return {
        "server": base_dir / "server.log",
        "request": base_dir / "request.log",
        "campaign": base_dir / campaign / "campaign.log",
        "chat": base_dir / campaign / "chat.log",
    }


def _rotate_logs(log_files: dict[str, Path]) -> None:
    """Rotate log files by truncating them (preserves the file for tailing)."""
    for path in log_files.values():
        if path.exists():
            path.write_text("")


def _restore_campaign_markdown() -> None:
    """Copy source markdown from data/dev_campaign/ into the working dir."""
    src = DEV_CAMPAIGN_SOURCE / "markdown"
    if not src.exists():
        return
    if CAMPAIGN_MARKDOWN_DIR.exists():
        shutil.rmtree(CAMPAIGN_MARKDOWN_DIR)
    shutil.copytree(src, CAMPAIGN_MARKDOWN_DIR)


# ---------------------------------------------------------------------------
# Session-scoped: Frontend build
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def frontend_dist() -> Path:
    """Ensure frontend/dist/ exists and is up-to-date.

    1. Check for node_modules/, run npm install if missing
    2. Check for dist/index.html
    3. If missing or stale (src newer than dist), run npm build
    4. Return the dist path
    """
    node_modules = FRONTEND_DIR / "node_modules"
    dist_dir = FRONTEND_DIR / "dist"
    dist_index = dist_dir / "index.html"
    src_dir = FRONTEND_DIR / "src"

    # Verify npm is available
    npm_path = shutil.which("npm")
    if npm_path is None:
        pytest.fail(
            "npm is not installed or not on PATH. "
            "Install Node.js to run E2E tests."
        )

    # Step 1: npm install if needed
    if not node_modules.exists():
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(FRONTEND_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(f"npm install failed:\n{result.stderr}")

    # Step 2-5: Check dist freshness
    needs_build = False
    if not dist_index.exists():
        needs_build = True
    else:
        # Compare newest src file mtime against dist mtime
        dist_mtime = dist_dir.stat().st_mtime
        for src_file in src_dir.rglob("*"):
            if src_file.is_file() and src_file.stat().st_mtime > dist_mtime:
                needs_build = True
                break

    if needs_build:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(f"Frontend build failed:\n{result.stderr}")

    return dist_dir


# ---------------------------------------------------------------------------
# Session-scoped: E2E server
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_server(frontend_dist: Path) -> Generator[str, None, None]:
    """Start a Sidestage server on port 8001 for E2E tests.

    - Always starts fresh (never reuses running instance)
    - Restores campaign markdown before start
    - Rotates log files
    - Passes SIDESTAGE_MOCK_AGENT=1
    - Waits for readiness via health check polling
    - Tears down with SIGTERM on session end
    """
    port = _find_available_port(DEFAULT_E2E_PORT)
    base_url = f"http://localhost:{port}"

    # Restore campaign state and rotate logs
    _restore_campaign_markdown()
    logs = _log_files(DEVSERVER_DIR)
    _rotate_logs(logs)

    # Ensure the working directory exists
    DEVSERVER_DIR.mkdir(parents=True, exist_ok=True)
    campaign_dir = DEVSERVER_DIR / CAMPAIGN_NAME
    if not campaign_dir.exists():
        shutil.copytree(DEV_CAMPAIGN_SOURCE, campaign_dir)

    # Remove stale PID file if present
    pid_file = DEVSERVER_DIR / "sidestage.pid"
    if pid_file.exists():
        pid_file.unlink()

    # Start the server directly (not via run-dev.sh, to control port)
    env = {
        **os.environ,
        "SIDESTAGE_MOCK_AGENT": "1",
        "SIDESTAGE_PORT": str(port),
    }

    process = subprocess.Popen(
        [
            sys.executable, "-m", "sidestage.server",
            "--sidestage_dir", str(DEVSERVER_DIR),
            "--port", str(port),
            CAMPAIGN_NAME,
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for readiness
    deadline = time.time() + 30
    while time.time() < deadline:
        if server_is_running(base_url):
            break
        # Check if process died
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(
                f"E2E server exited unexpectedly (code {process.returncode}).\n"
                f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
            )
        time.sleep(1.0)
    else:
        process.kill()
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(
            f"E2E server failed to start within 30s on port {port}.\n"
            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield base_url

    # Teardown: graceful shutdown
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


# ---------------------------------------------------------------------------
# Session-scoped: HTTP client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_client(e2e_server: str) -> Generator[httpx.Client, None, None]:
    """Session-scoped httpx client pointed at the E2E server."""
    with httpx.Client(base_url=e2e_server, timeout=30.0) as client:
        yield client


# ---------------------------------------------------------------------------
# Class-scoped: Campaign reset
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def fresh_e2e_campaign(e2e_client: httpx.Client) -> None:
    """Restore campaign state: re-import markdown and reload defaults.

    Class-scoped so it runs once per test class.
    """
    _restore_campaign_markdown()

    resp = e2e_client.post(
        "/v1/campaign/import",
        json={"action": "execute", "force": True},
    )
    assert resp.status_code == 200, f"Campaign re-import failed: {resp.text}"
    data = resp.json()
    result = data.get("result", {})
    errors = result.get("errors", [])
    assert result.get("phase") == "complete", (
        f"Campaign import phase={result.get('phase')!r}, errors={errors}"
    )

    resp = e2e_client.post("/v1/campaign/reload-defaults")
    assert resp.status_code == 200, f"reload-defaults failed: {resp.text}"


# ---------------------------------------------------------------------------
# Per-test: Log observer
# ---------------------------------------------------------------------------

@pytest.fixture()
def log_observer() -> Any:
    """Per-test log observer for asserting on backend log output."""
    logs = _log_files(DEVSERVER_DIR)
    observer = LogObserver(logs)
    observer.mark()
    return observer
```

### Key Design Decisions

**Server startup:** The fixture invokes `python -m sidestage.server` directly rather than using `scripts/run-dev.sh` because:
- `run-dev.sh` does not accept a `--port` argument
- `run-dev.sh` exits silently if a PID file exists, which could cause flaky behavior
- Direct invocation gives full control over the command-line arguments and environment

**Port selection:** The fixture starts at port 8001 and probes upward if that port is occupied. The `_find_available_port()` function tries to bind a socket to each port in sequence. This ensures tests work even if another process occupies 8001.

**SIDESTAGE_PORT env var:** The `SIDESTAGE_PORT` environment variable is set but not yet consumed by the server (that change is part of section 05). For now, the `--port` CLI argument is what actually controls the port. The env var is passed for forward compatibility.

**Frontend build:** The `frontend_dist` fixture is session-scoped so the build happens at most once per test run. It checks `node_modules/` existence (runs `npm install` if missing) and compares source file mtimes against `dist/` mtime to decide whether to rebuild.

**Campaign reset:** The `fresh_e2e_campaign` fixture mirrors the existing `fresh_campaign` fixture from `tests/devserver/conftest.py`. It copies markdown from `data/dev_campaign/markdown/` to `sidestage.dev/dev/markdown/`, then calls the import and reload-defaults APIs.

**Helper reuse:** `LogObserver` and `server_is_running` are imported from `tests/devserver/helpers.py` using `importlib.util` (same pattern as the existing devserver conftest). This avoids duplicating code.

### Step 3: Playwright Configuration via pytest-playwright

`pytest-playwright` provides built-in fixtures (`page`, `browser`, `context`) that are automatically available. No separate `playwright.config.ts` file is needed -- pytest-playwright is configured via `conftest.py` fixtures and CLI flags.

The default behavior gives:
- **Chromium** browser (default for pytest-playwright)
- **Headless** mode by default (override with `--headed` CLI flag)
- **30 second** default timeout for Playwright assertions (configurable per-test)
- **1280x720** viewport (pytest-playwright default)

No additional Playwright configuration fixtures are needed beyond what `pytest-playwright` provides out of the box. The `e2e_server` fixture provides the base URL, and individual tests use `page.goto(f"{e2e_server}/sidestage/")` to navigate.

### Step 4: Create the Canary Test

Create file: `/home/harald/src/sidestage/tests/e2e/test_canary.py`

This file is described in the "Tests First" section above. It validates that:
1. The `e2e_client` fixture can reach the server's `/v1/entities` endpoint
2. Playwright can navigate to `/sidestage/` and the page loads
3. The SPA renders actual content (not a blank page)

### Step 5: Verify the Infrastructure

After implementing all files, run:

```bash
cd /home/harald/src/sidestage

# Sync dependencies (installs pytest-playwright)
uv sync

# Install Playwright browser
uv run playwright install chromium

# Run the canary test
uv run pytest tests/e2e/test_canary.py -v
```

Expected result: all three canary tests pass. The server starts on port 8001 (or the next available port), the frontend builds if needed, and Playwright successfully navigates to the SPA.

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `/home/harald/src/sidestage/pyproject.toml` | Modify | Add `pytest-playwright` dep, add `e2e` marker |
| `/home/harald/src/sidestage/tests/e2e/__init__.py` | Create | Package marker (empty file) |
| `/home/harald/src/sidestage/tests/e2e/conftest.py` | Create | All E2E fixtures: server, build, campaign reset, client, log observer |
| `/home/harald/src/sidestage/tests/e2e/test_canary.py` | Create | Canary tests validating the infrastructure works |

## Dependencies

- **No dependencies on other sections.** This section is independently implementable.
- **Blocks section 05** (Mock Actor) which adds `SIDESTAGE_MOCK_AGENT` handling to the server.
- **Blocks section 06** (E2E Tests) which writes the actual E2E test scenarios.

## Notes for Implementer

1. The `SIDESTAGE_MOCK_AGENT=1` env var is passed by the server fixture but is not yet consumed by the server code. That integration happens in section 05. The server will simply ignore the unknown env var for now, which is fine.

2. The `sys.executable` approach (`python -m sidestage.server`) ensures the server runs in the same Python environment as pytest (the `uv` virtual environment). Using `uv run sidestage` would also work but adds a subprocess layer.

3. The existing `tests/conftest.py` has an `autouse=True` fixture `_init_config` that initializes a global config singleton with `tmp_path`. This fixture runs for ALL tests including E2E tests. Since E2E tests use a real server process (not in-process), this is harmless -- the config initialization happens in the test process while the server has its own config. However, if this causes issues, the E2E conftest can override it with a no-op.

4. The `frontend_dist` fixture uses `subprocess.run` with `timeout=120` for npm operations. If the frontend has many dependencies or the build is slow, this timeout may need adjustment.

5. The canary test `test_frontend_has_content` uses a broad CSS selector (`[data-testid], main, .app, #root *`) to detect that the React app rendered. This is intentionally loose -- the goal is to verify infrastructure, not test specific UI elements. More precise selectors belong in section 06's E2E tests.