"""Fixtures for dev server integration tests.

Session-scoped fixtures manage the dev server lifecycle and provide an httpx
client.  Per-test fixtures provide a LogObserver for asserting on log file
contents.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

import importlib.util
import sys

# Import helpers from the same directory (conftest.py can't use relative imports).
_helpers_path = Path(__file__).with_name("helpers.py")
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
DEVSERVER_DIR = REPO_ROOT / "sidestage.dev"
PID_FILE = DEVSERVER_DIR / "sidestage.pid"
CAMPAIGN_NAME = "dev"

LOG_FILES: dict[str, Path] = {
    "server": DEVSERVER_DIR / "server.log",
    "request": DEVSERVER_DIR / "request.log",
    "campaign": DEVSERVER_DIR / CAMPAIGN_NAME / "campaign.log",
    "chat": DEVSERVER_DIR / CAMPAIGN_NAME / "chat.log",
}

DEV_CAMPAIGN_SOURCE = REPO_ROOT / "data" / "dev_campaign"
CAMPAIGN_MARKDOWN_DIR = DEVSERVER_DIR / CAMPAIGN_NAME / "markdown"

DEVSERVER_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Session-scoped: server lifecycle
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _ensure_campaign_markdown() -> None:
    """Restore dev campaign markdown at the start of the test session."""
    _restore_campaign_markdown()


@pytest.fixture(scope="session")
def devserver() -> Generator[str, None, None]:
    """Ensure the dev server is running for the test session.

    If already running, reuse it.  Otherwise start via ``scripts/run-dev.sh``,
    wait for readiness, and kill on teardown.
    """
    if server_is_running(DEVSERVER_BASE_URL):
        yield DEVSERVER_BASE_URL
        return

    # Clean up stale PID file if the server isn't actually running.
    if PID_FILE.exists():
        PID_FILE.unlink()

    run_script = REPO_ROOT / "scripts" / "run-dev.sh"
    process = subprocess.Popen(
        [str(run_script)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if server_is_running(DEVSERVER_BASE_URL):
            break
        time.sleep(1.0)
    else:
        process.kill()
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(
            f"Dev server failed to start within 30 s.\n"
            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield DEVSERVER_BASE_URL

    # Teardown: graceful shutdown.
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
def client(devserver: str) -> Generator[httpx.Client, None, None]:
    """Session-scoped httpx client pointed at the dev server."""
    with httpx.Client(base_url=devserver, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Per-test: log observer
# ---------------------------------------------------------------------------


@pytest.fixture()
def log_observer() -> Any:
    """Per-test log observer — records file positions before the test body."""
    observer = LogObserver(LOG_FILES)
    observer.mark()
    return observer


@pytest.fixture(autouse=True)
def _check_server_errors() -> Generator[None, None, None]:
    """Fail the test if the server emitted ERROR-level log entries."""
    observer = LogObserver(LOG_FILES)
    observer.mark()
    yield
    new_text = observer.read_new_text("server")
    error_lines = [
        line for line in new_text.splitlines()
        if " - ERROR - " in line or "Traceback " in line
    ]
    assert not error_lines, (
        f"Server emitted {len(error_lines)} error(s) during test:\n"
        + "\n".join(error_lines[:10])
    )


# ---------------------------------------------------------------------------
# Class-scoped: campaign reset
# ---------------------------------------------------------------------------


def _restore_campaign_markdown() -> None:
    """Copy source markdown from data/dev_campaign/ into the working dir.

    This ensures backups or prior test runs cannot clobber the import source.
    """
    src = DEV_CAMPAIGN_SOURCE / "markdown"
    if not src.exists():
        return
    if CAMPAIGN_MARKDOWN_DIR.exists():
        shutil.rmtree(CAMPAIGN_MARKDOWN_DIR)
    shutil.copytree(src, CAMPAIGN_MARKDOWN_DIR)


@pytest.fixture(scope="class")
def fresh_campaign(client: httpx.Client) -> None:
    """Restore source markdown and re-import so the graph starts clean."""
    _restore_campaign_markdown()
    resp = client.post(
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

    # Re-add default entities (campaign_planning, co-author) to the graph.
    resp = client.post("/v1/campaign/reload-defaults")
    assert resp.status_code == 200, f"reload-defaults failed: {resp.text}"
