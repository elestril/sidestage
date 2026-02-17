"""Fixtures for end-to-end Playwright tests.

Session-scoped fixtures build the frontend, start a Sidestage server on port 8001,
and provide an httpx client. Class-scoped fixtures reset campaign state.

Uses a separate sidestage.e2e/ working directory to avoid conflicts with the
dev instance running in sidestage.dev/.
"""

from __future__ import annotations

import importlib.util
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
# Import helpers from devserver (LogObserver, server_is_running)
# ---------------------------------------------------------------------------

_helpers_path = Path(__file__).resolve().parent.parent / "devserver" / "helpers.py"
_spec = importlib.util.spec_from_file_location("tests.devserver.helpers", _helpers_path)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _helpers
_spec.loader.exec_module(_helpers)

LogObserver = _helpers.LogObserver
server_is_running = _helpers.server_is_running

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_DIR = REPO_ROOT / "sidestage.e2e"
FRONTEND_DIR = REPO_ROOT / "frontend"
CAMPAIGN_NAME = "dev"

DEV_CAMPAIGN_SOURCE = REPO_ROOT / "data" / "dev_campaign"
CAMPAIGN_MARKDOWN_DIR = E2E_DIR / CAMPAIGN_NAME / "markdown"

DEFAULT_E2E_PORT = 8001


def _find_available_port(start: int = DEFAULT_E2E_PORT, max_attempts: int = 10) -> int:
    """Find an available TCP port starting from *start*."""
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
    """Copy source markdown from data/dev_campaign/ into the E2E working dir."""
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
            pytest.fail(
                f"npm install failed:\n{result.stdout}\n{result.stderr}"
            )

    # Step 2-3: Check dist freshness
    needs_build = False
    if not dist_index.exists():
        needs_build = True
    else:
        # Compare newest src file mtime against dist/index.html mtime
        dist_mtime = dist_index.stat().st_mtime
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
            pytest.fail(
                f"Frontend build failed:\n{result.stdout}\n{result.stderr}"
            )

    return dist_dir


# ---------------------------------------------------------------------------
# Session-scoped: E2E server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_server(frontend_dist: Path) -> Generator[str, None, None]:
    """Start a Sidestage server on port 8001 for E2E tests.

    - Always starts fresh (never reuses running instance)
    - Uses sidestage.e2e/ working directory (isolated from dev instance)
    - Restores campaign markdown before start
    - Rotates log files
    - Passes SIDESTAGE_MOCK_AGENT=1 and --no-reload
    - Waits for readiness via health check polling
    - Tears down with SIGTERM on session end
    """
    port = _find_available_port(DEFAULT_E2E_PORT)
    base_url = f"http://localhost:{port}"

    # Restore campaign state and rotate logs
    _restore_campaign_markdown()
    logs = _log_files(E2E_DIR)
    _rotate_logs(logs)

    # Ensure the working directory exists
    E2E_DIR.mkdir(parents=True, exist_ok=True)
    campaign_dir = E2E_DIR / CAMPAIGN_NAME
    if not campaign_dir.exists():
        shutil.copytree(DEV_CAMPAIGN_SOURCE, campaign_dir)

    # Remove stale PID file if present
    pid_file = E2E_DIR / "sidestage.pid"
    if pid_file.exists():
        pid_file.unlink()

    # Start the server with --no-reload to avoid watcher/worker complications
    env = {
        **os.environ,
        "SIDESTAGE_MOCK_AGENT": "1",
        "SIDESTAGE_PORT": str(port),
    }

    # Capture stdout/stderr to a log file instead of PIPE to avoid deadlocks
    server_log = E2E_DIR / "server_stdout.log"
    log_fh = open(server_log, "w")

    process = subprocess.Popen(
        [
            sys.executable, "-m", "sidestage.server",
            "--sidestage_dir", str(E2E_DIR),
            "--port", str(port),
            "--no-reload",
            CAMPAIGN_NAME,
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    # Wait for readiness
    deadline = time.time() + 30
    while time.time() < deadline:
        if server_is_running(base_url):
            break
        # Check if process died
        if process.poll() is not None:
            log_fh.close()
            output = server_log.read_text()
            pytest.fail(
                f"E2E server exited unexpectedly (code {process.returncode}).\n"
                f"output:\n{output}"
            )
        time.sleep(1.0)
    else:
        process.kill()
        process.wait(timeout=5)
        log_fh.close()
        output = server_log.read_text()
        pytest.fail(
            f"E2E server failed to start within 30s on port {port}.\n"
            f"output:\n{output}"
        )

    yield base_url

    # Teardown: graceful shutdown
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    finally:
        log_fh.close()


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
    logs = _log_files(E2E_DIR)
    observer = LogObserver(logs)
    observer.mark()
    return observer


# ---------------------------------------------------------------------------
# Per-test: Scene activation and mock agent cleanup
# ---------------------------------------------------------------------------


@pytest.fixture()
def activate_scene(e2e_client: httpx.Client):
    """Activate the default scene so mock agents exist for configuration.

    Scenes activate lazily when a chat message is sent. This fixture
    sends a throwaway message to ensure mock agents are created, then
    resets the mock agent after the test completes.
    """
    e2e_client.post(
        "/v1/chat",
        json={"message": "init", "scene_id": "campaign_planning"},
    )
    time.sleep(1.0)
    yield
    e2e_client.post("/v1/test/mock-agent/reset")
