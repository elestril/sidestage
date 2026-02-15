"""Utilities for dev server integration tests.

LogObserver tracks log file growth during a test. Polling helpers wait for
async results (agent responses) to appear in scene messages or logs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass
class LogObserver:
    """Observe log file growth during a test.

    Usage::

        observer = LogObserver({"server": Path("server.log"), ...})
        observer.mark()        # snapshot current positions
        # ... do something ...
        new_lines = observer.read_new("server")
        assert any("entity loaded" in line for line in new_lines)
    """

    log_files: dict[str, Path]
    _positions: dict[str, int] = field(default_factory=dict, init=False)

    def mark(self) -> None:
        """Record the current end-of-file position for each log file."""
        for name, path in self.log_files.items():
            if path.exists():
                self._positions[name] = path.stat().st_size
            else:
                self._positions[name] = 0

    def read_new(self, log_name: str) -> list[str]:
        """Read lines written since the last ``mark()``."""
        path = self.log_files[log_name]
        start_pos = self._positions.get(log_name, 0)
        if not path.exists():
            return []
        with open(path, "r") as f:
            f.seek(start_pos)
            return f.readlines()

    def read_new_text(self, log_name: str) -> str:
        """Read raw text written since the last ``mark()``."""
        return "".join(self.read_new(log_name))

    def wait_for_pattern(
        self, log_name: str, pattern: str, timeout: float = 10.0
    ) -> str | None:
        """Poll a log file until a regex pattern appears in new lines.

        Returns the first matching line, or ``None`` on timeout.
        """
        compiled = re.compile(pattern)
        deadline = time.time() + timeout
        while time.time() < deadline:
            for line in self.read_new(log_name):
                if compiled.search(line):
                    return line
            time.sleep(0.5)
        return None

    def assert_contains(self, log_name: str, substring: str) -> None:
        """Assert the new log content contains *substring*."""
        text = self.read_new_text(log_name)
        assert substring in text, (
            f"Expected '{substring}' in {log_name} log. "
            f"Got ({len(text)} chars): {text[:500]}"
        )

    def assert_not_contains(self, log_name: str, substring: str) -> None:
        """Assert the new log content does NOT contain *substring*."""
        text = self.read_new_text(log_name)
        assert substring not in text, (
            f"Did not expect '{substring}' in {log_name} log, but found it."
        )


def poll_scene_messages(
    client: httpx.Client,
    scene_id: str,
    *,
    min_count: int = 1,
    predicate: object = None,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Poll ``GET /v1/scenes/{id}/messages`` until a condition is met.

    Args:
        client: httpx Client pointed at the dev server.
        scene_id: Scene to poll.
        min_count: Minimum number of messages to wait for.
        predicate: Optional ``callable(messages) -> bool`` for custom conditions.
        timeout: Maximum wait time in seconds.

    Returns:
        The final list of messages.

    Raises:
        AssertionError: If timeout expires before the condition is met.
    """
    deadline = time.time() + timeout
    messages: list[dict] = []
    while time.time() < deadline:
        resp = client.get(f"/v1/scenes/{scene_id}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        if len(messages) >= min_count:
            if predicate is None or predicate(messages):  # type: ignore[operator]
                return messages
        time.sleep(0.5)

    raise AssertionError(
        f"Timeout ({timeout}s) waiting for scene '{scene_id}' messages. "
        f"Expected min_count={min_count}, got {len(messages)}."
    )


def server_is_running(base_url: str = "http://localhost:8000") -> bool:
    """Return True if the dev server responds to a health-check request."""
    try:
        resp = httpx.get(f"{base_url}/v1/entities", timeout=2.0)
        return resp.status_code == 200
    except httpx.ConnectError:
        return False


def llm_is_running(base_url: str = "http://localhost:8080") -> bool:
    """Return True if the LLM server is reachable."""
    try:
        resp = httpx.get(f"{base_url}/health", timeout=2.0)
        return resp.status_code == 200
    except httpx.ConnectError:
        return False
