"""Cross-CUJ observability tests: logging, request context, log file structure."""

from __future__ import annotations

import time

import httpx

from tests.devserver.helpers import LogObserver


class TestRequestContext:
    """Verify request-context propagation through response headers."""

    def test_x_request_id_echoed(self, client: httpx.Client) -> None:
        """Server echoes X-Request-ID in response headers."""
        resp = client.get(
            "/v1/entities",
            headers={"X-Request-ID": "obs-echo-001"},
        )
        assert resp.headers["x-request-id"] == "obs-echo-001"

    def test_auto_generated_request_id(self, client: httpx.Client) -> None:
        """When no X-Request-ID is sent, the server generates one."""
        resp = client.get("/v1/entities")
        rid = resp.headers.get("x-request-id")
        assert rid is not None
        assert len(rid) > 0

    def test_debug_headers_dont_break_requests(self, client: httpx.Client) -> None:
        """X-Debug-* headers propagate without breaking the request."""
        resp = client.get(
            "/v1/entities",
            headers={
                "X-Request-ID": "obs-debug-test",
                "X-Debug-Tag": "test-tag-value",
            },
        )
        assert resp.status_code == 200


class TestLogFileStructure:
    """Verify the four log files exist and accumulate content."""

    def test_server_log_exists_and_has_content(
        self, log_observer: LogObserver
    ) -> None:
        """server.log exists and has content."""
        path = log_observer.log_files["server"]
        assert path.exists(), f"server.log not found at {path}"
        assert path.stat().st_size > 0

    def test_request_log_exists(self, log_observer: LogObserver) -> None:
        """request.log exists."""
        path = log_observer.log_files["request"]
        assert path.exists(), f"request.log not found at {path}"

    def test_campaign_log_exists_and_has_content(
        self, log_observer: LogObserver
    ) -> None:
        """campaign.log exists with campaign operation messages."""
        path = log_observer.log_files["campaign"]
        assert path.exists(), f"campaign.log not found at {path}"
        assert path.stat().st_size > 0

    def test_chat_log_exists(self, log_observer: LogObserver) -> None:
        """chat.log exists."""
        path = log_observer.log_files["chat"]
        assert path.exists(), f"chat.log not found at {path}"


class TestLogIsolation:
    """Verify logs go to the correct files."""

    def test_request_log_has_http_entries(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """request.log accumulates entries when HTTP requests are made."""
        log_observer.mark()
        client.get("/v1/entities")
        client.get("/v1/scenes")
        time.sleep(0.5)
        new_text = log_observer.read_new_text("request")
        assert len(new_text) > 0, "request.log should grow with HTTP requests"

    def test_request_log_records_path_and_status(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """request.log contains the HTTP method, path, and status code."""
        log_observer.mark()
        client.get("/v1/entities")
        time.sleep(0.5)
        log_observer.assert_contains("request", "GET /v1/entities")
        log_observer.assert_contains("request", "200")

    def test_access_log_does_not_propagate_to_server_log(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """uvicorn.access lines stay out of server.log (propagate=False)."""
        log_observer.mark()
        client.get("/v1/entities")
        time.sleep(0.5)
        # Access log lines mention the full HTTP request line; this should
        # NOT appear in server.log.
        server_text = log_observer.read_new_text("server")
        assert '"GET /v1/entities HTTP/1.1"' not in server_text
