Now I have a thorough understanding of the existing codebase patterns. Let me generate the section content.

# Section 05: API Endpoints and WebSocket Trace Messages

## Overview

This section adds four REST API endpoints and three WebSocket message types to the Sidestage backend, exposing the tracing system to the frontend. The REST endpoints allow querying trace data and controlling the tracing toggle. The WebSocket messages enable real-time trace streaming to connected clients.

All routes are added to `src/sidestage/orchestrator.py` within the existing `_setup_routes` method. The WebSocket broadcast mechanism uses the existing `SyncManager` class at `src/sidestage/sync.py`.

## Dependencies

This section depends on the following prior sections (reference only):

- **section-01-tracing-config**: Provides `TraceConfig` on `SidestageConfig.tracing`
- **section-02-tracing-core**: Provides `toggle_tracing()` and the `FilteringSpanProcessor` enabled flag
- **section-03-exporters**: Provides `InMemoryTraceExporter` (with `get_traces()`, `get_trace()`, `get_traces_for_scene()`) and `SQLiteTraceExporter` (with trace/span query methods)
- **section-04-backend-instrumentation**: Ensures spans are being created with the expected attributes (`sidestage.scene.id`, `sidestage.event.id`, etc.)

## Tests First

Tests go in `tests/unit/test_tracing_api.py`. The project uses `pytest` with `FastAPI`'s `TestClient` (synchronous). The existing pattern (visible in `tests/unit/test_migration_routes.py`) is to create a `SidestageOrchestrator` with a mocked `Campaign`, then wrap its `fastapi_app` in a `TestClient`.

For the WebSocket trace messages, tests go in `tests/unit/test_tracing_websocket.py`.

### REST API Tests

File: `/home/harald/src/sidestage/tests/unit/test_tracing_api.py`

```python
"""Tests for tracing REST API endpoints in orchestrator.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidestage.health import CampaignHealth
from sidestage.orchestrator import SidestageOrchestrator


# --- Fixtures ---

@pytest.fixture
def mock_orchestrator(tmp_path: Path) -> SidestageOrchestrator:
    """Create a SidestageOrchestrator with mocked Campaign and tracing dependencies."""
    # Fixture follows the pattern from test_migration_routes.py.
    # Must also mock the tracing module objects that the new endpoints access.
    ...


@pytest.fixture
def client(mock_orchestrator: SidestageOrchestrator) -> TestClient:
    """FastAPI TestClient wrapping mock_orchestrator.fastapi_app."""
    ...


# --- GET /v1/traces ---

def test_get_traces_returns_list_of_summaries(client: TestClient):
    """GET /v1/traces returns a JSON list of trace summary objects.
    Each summary has: trace_id, scene_id, event_id, event_type,
    start_time, duration_ms, span_count, root_span_name."""
    ...

def test_get_traces_filter_by_scene_id(client: TestClient):
    """GET /v1/traces?scene_id=X returns only traces for that scene."""
    ...

def test_get_traces_filter_by_event_id(client: TestClient):
    """GET /v1/traces?event_id=X returns the trace for that specific event."""
    ...

def test_get_traces_no_filter_returns_recent(client: TestClient):
    """GET /v1/traces with no query params returns most recent traces
    across all scenes, ordered by start_time descending."""
    ...

def test_get_traces_respects_limit(client: TestClient):
    """GET /v1/traces?limit=5 returns at most 5 traces."""
    ...

def test_get_traces_respects_offset(client: TestClient):
    """GET /v1/traces?offset=10&limit=5 skips the first 10 traces."""
    ...


# --- GET /v1/traces/{trace_id} ---

def test_get_trace_detail_returns_full_trace(client: TestClient):
    """GET /v1/traces/{trace_id} returns the full trace with all spans.
    Response shape: {trace_id: str, spans: [{span_id, parent_span_id, name, ...}]}"""
    ...

def test_get_trace_detail_nonexistent_returns_404(client: TestClient):
    """GET /v1/traces/{trace_id} for a trace_id that does not exist
    returns HTTP 404."""
    ...


# --- POST /v1/tracing/toggle ---

def test_toggle_tracing_enable(client: TestClient):
    """POST /v1/tracing/toggle with {"enabled": true} calls toggle_tracing(True)
    and returns {"tracing_enabled": true}."""
    ...

def test_toggle_tracing_disable(client: TestClient):
    """POST /v1/tracing/toggle with {"enabled": false} calls toggle_tracing(False)
    and returns {"tracing_enabled": false}."""
    ...


# --- GET /v1/tracing/status ---

def test_get_tracing_status(client: TestClient):
    """GET /v1/tracing/status returns {enabled: bool, config: {...}, trace_count: int}."""
    ...

def test_get_tracing_status_includes_trace_count(client: TestClient):
    """GET /v1/tracing/status includes the current number of traces
    in the in-memory exporter."""
    ...
```

### WebSocket Trace Message Tests

File: `/home/harald/src/sidestage/tests/unit/test_tracing_websocket.py`

```python
"""Tests for WebSocket trace message broadcasting."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from sidestage.sync import SyncManager


# --- trace_started ---

def test_trace_started_sent_on_root_span(mock_sync_manager):
    """When the InMemoryTraceExporter receives a span with no parent,
    a 'trace_started' message is broadcast via SyncManager.
    Payload: {type: 'trace_started', trace_id, scene_id, event_type, start_time_ms}."""
    ...

# --- span_completed ---

def test_span_completed_sent_on_any_span(mock_sync_manager):
    """When the InMemoryTraceExporter receives any span,
    a 'span_completed' message is broadcast.
    Payload: {type: 'span_completed', ...serialized span dict}."""
    ...

# --- trace_completed ---

def test_trace_completed_sent_on_root_span_finish(mock_sync_manager):
    """When the InMemoryTraceExporter receives a finished root span,
    a 'trace_completed' message is broadcast.
    Payload: {type: 'trace_completed', trace_id, scene_id, duration_ms}."""
    ...

# --- Payload format ---

def test_websocket_messages_have_correct_format(mock_sync_manager):
    """Verify the payload shapes match the documented format for each
    of the three trace message types."""
    ...

# --- Broadcast to all clients ---

def test_trace_messages_broadcast_to_all_clients(mock_sync_manager):
    """Verify that trace messages are sent via SyncManager.broadcast()
    which delivers to all connected WebSocket clients."""
    ...
```

## Implementation Details

### 5.1 REST Endpoints

All four endpoints are added inside `SidestageOrchestrator._setup_routes()` in `src/sidestage/orchestrator.py`. They interact with the tracing module via the public API from `src/sidestage/tracing/__init__.py`.

#### Data Flow for Trace Queries

The endpoints use a two-tier lookup strategy:
1. **In-memory first**: Check `InMemoryTraceExporter` (fast, covers recent traces)
2. **Fall back to SQLite**: Query `SQLiteTraceExporter` for older/persisted traces

The `SidestageOrchestrator` needs access to the exporter instances. The recommended approach is to store references to both exporters as module-level singletons in `src/sidestage/tracing/__init__.py` (set during `init_tracing()`) and import accessor functions into the orchestrator.

#### Endpoint: GET /v1/traces

Added to `_setup_routes()` in `/home/harald/src/sidestage/src/sidestage/orchestrator.py`.

```python
@self.fastapi_app.get("/v1/traces")
async def list_traces(
    scene_id: str | None = None,
    event_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List trace summaries, optionally filtered by scene_id or event_id.

    Returns a list of trace summary dicts, each containing:
    trace_id, scene_id, event_id, event_type, start_time, duration_ms,
    span_count, root_span_name.

    When scene_id is provided: filter by scene.
    When event_id is provided: return the trace for that specific event.
    When both omitted: return most recent traces across all scenes.

    Source: SQLite traces table (indexed on scene_id and event_id).
    """
    ...
```

Query parameters:
- `scene_id` (optional string): Filter traces to a specific scene
- `event_id` (optional string): Find the trace associated with a specific chat message event
- `limit` (int, default 50): Maximum number of traces to return
- `offset` (int, default 0): Number of traces to skip for pagination

Response: JSON array of trace summary objects:
```json
[
  {
    "trace_id": "abc123...",
    "scene_id": "campaign_planning",
    "event_id": "msg_xyz",
    "event_type": "ChatMessage",
    "start_time": "2026-02-07T12:00:00Z",
    "duration_ms": 1234.5,
    "span_count": 8,
    "root_span_name": "scene.process_event"
  }
]
```

The endpoint queries the `SQLiteTraceExporter`'s `traces` table. This table has indexes on `scene_id`, `event_id`, and `created_at`, making all three query patterns efficient.

#### Endpoint: GET /v1/traces/{trace_id}

```python
@self.fastapi_app.get("/v1/traces/{trace_id}")
async def get_trace_detail(trace_id: str):
    """Return the full trace with all spans for a given trace_id.

    Tries the in-memory exporter first (fast path for recent traces),
    then falls back to SQLite for older traces.

    Returns 404 if the trace is not found in either store.
    """
    ...
```

Response shape:
```json
{
  "trace_id": "abc123...",
  "spans": [
    {
      "trace_id": "abc123...",
      "span_id": "def456...",
      "parent_span_id": null,
      "name": "scene.process_event",
      "kind": "INTERNAL",
      "start_time_ms": 1707307200000.0,
      "end_time_ms": 1707307201234.0,
      "duration_ms": 1234.0,
      "status": {"code": "OK", "description": null},
      "attributes": {"sidestage.scene.id": "campaign_planning"},
      "events": []
    }
  ]
}
```

When the trace is not found in either the in-memory exporter or SQLite, the endpoint raises `HTTPException(status_code=404, detail="Trace not found")`.

#### Endpoint: POST /v1/tracing/toggle

```python
@self.fastapi_app.post("/v1/tracing/toggle")
async def toggle_tracing_endpoint(body: dict):
    """Toggle tracing on or off.

    Request body: {"enabled": bool}
    Calls toggle_tracing(enabled) to flip the FilteringSpanProcessor flag.
    Returns: {"tracing_enabled": bool}
    """
    ...
```

This endpoint calls `toggle_tracing(enabled)` from `src/sidestage/tracing/__init__.py`, which flips the `enabled` flag on the `FilteringSpanProcessor` instances. The change takes effect immediately for new spans.

Consider defining a small Pydantic model for the request body:
```python
class TracingToggleRequest(BaseModel):
    enabled: bool
```

This can be added to `src/sidestage/schemas.py` or defined inline in the orchestrator.

#### Endpoint: GET /v1/tracing/status

```python
@self.fastapi_app.get("/v1/tracing/status")
async def get_tracing_status():
    """Return current tracing status.

    Returns: {
        "enabled": bool,
        "config": {
            "capture_prompts": bool,
            "capture_tool_args": bool,
            "capture_memory_content": bool,
            "max_attribute_length": int,
            ...
        },
        "trace_count": int
    }
    """
    ...
```

The `enabled` field reflects the current `FilteringSpanProcessor` state. The `config` field is the serialized `TraceConfig` from `SidestageConfig.tracing`. The `trace_count` is the number of traces currently held in the `InMemoryTraceExporter`.

### 5.2 WebSocket Trace Messages

The tracing system broadcasts three types of WebSocket messages to all connected clients via `SyncManager`. The frontend filters client-side by `scene_id` (this is a single-user tool, so no subscription mechanism is needed).

#### Broadcast Callback Integration

The `InMemoryTraceExporter` (from section-03) accepts a callback function at init time. This callback fires whenever spans are exported. The orchestrator wires this callback to `SyncManager.broadcast()`.

The callback is an async function, but the `InMemoryTraceExporter.export()` method runs synchronously (it is called from `SimpleSpanProcessor` in the trace pipeline). The callback must therefore schedule the async broadcast onto the event loop. The recommended pattern:

```python
def _make_trace_broadcast_callback(sync_manager: SyncManager):
    """Create a callback for InMemoryTraceExporter that broadcasts
    trace events via WebSocket.

    The callback is called synchronously from the span export pipeline.
    It schedules the async broadcast onto the running event loop.
    """
    def callback(span_data: dict, is_root: bool):
        """Called by InMemoryTraceExporter on each exported span.

        Args:
            span_data: Serialized span dict (ms timestamps, all fields).
            is_root: True if this span has no parent (root span).
        """
        ...
    return callback
```

This callback function is created in the orchestrator and passed to the `InMemoryTraceExporter` during `init_tracing()`. The orchestrator's `_lifespan` or `__init__` is the appropriate place to wire this up, depending on when `init_tracing()` is called.

#### Message Type: trace_started

Sent when a root span (a span with no parent) is received by the exporter. This indicates a new trace has begun.

```json
{
  "type": "trace_started",
  "trace_id": "abc123...",
  "scene_id": "campaign_planning",
  "event_type": "ChatMessage",
  "start_time_ms": 1707307200000.0
}
```

The `scene_id` and `event_type` are extracted from the span's attributes (`sidestage.scene.id` and `sidestage.event.type`).

#### Message Type: span_completed

Sent when any span finishes. The payload is the full serialized span dict.

```json
{
  "type": "span_completed",
  "trace_id": "abc123...",
  "span_id": "def456...",
  "parent_span_id": "abc123...",
  "name": "llm.completion",
  "kind": "INTERNAL",
  "start_time_ms": 1707307200100.0,
  "end_time_ms": 1707307200900.0,
  "duration_ms": 800.0,
  "status": {"code": "OK", "description": null},
  "attributes": {"gen_ai.request.model": "llama-3"},
  "events": [],
  "scene_id": "campaign_planning",
  "event_id": null
}
```

#### Message Type: trace_completed

Sent when a root span finishes, indicating the entire trace is done.

```json
{
  "type": "trace_completed",
  "trace_id": "abc123...",
  "scene_id": "campaign_planning",
  "duration_ms": 1234.0
}
```

#### Determining Root Spans

A span is a root span when its `parent_span_id` is `None` (or the parent context is invalid/not set). The `InMemoryTraceExporter` checks this during export. For root spans, the callback fires with `is_root=True`, and the callback implementation sends both `trace_started` (if it is the first time this trace_id is seen -- i.e., when a root span starts) and `trace_completed` (when the root span ends and has valid `end_time_ms`).

In practice, since `SimpleSpanProcessor` calls `export()` in `on_end()` (when the span finishes), the exporter only sees completed spans. This means:
- Every span triggers a `span_completed` message
- Root spans additionally trigger a `trace_completed` message
- The `trace_started` message is also sent on the root span's export (since root spans arrive in `on_end`, the "started" message is technically sent at the same time as "completed" for the root -- but this is acceptable because child spans finish before the root, so the `span_completed` messages for children arrive first, followed by the root's `trace_started` + `trace_completed` together)

**Alternative approach**: To get a true `trace_started` at the beginning of the trace, use `on_start()` in a custom `SpanProcessor` that only fires the WebSocket callback for root spans when they start. The `FilteringSpanProcessor` from section-02 could be extended, or a separate lightweight processor could handle this. This is the preferred approach: use `on_start()` for `trace_started` and `on_end()` (via the exporter callback) for `span_completed` and `trace_completed`.

### 5.3 Request/Response Models

Add to `/home/harald/src/sidestage/src/sidestage/schemas.py` (or define locally in the orchestrator):

```python
class TracingToggleRequest(BaseModel):
    """Request body for POST /v1/tracing/toggle."""
    enabled: bool
```

The trace summary and detail response models do not need Pydantic models -- they can be returned as plain dicts since they are constructed from the exporter query methods. However, if strict typing is desired, define:

```python
class TraceSummary(BaseModel):
    """Summary of a single trace, returned in GET /v1/traces list."""
    trace_id: str
    scene_id: str | None
    event_id: str | None
    event_type: str | None
    start_time: str  # ISO format
    duration_ms: float
    span_count: int
    root_span_name: str | None
```

### 5.4 Imports Required in orchestrator.py

The orchestrator needs to import from the tracing module:

```python
from sidestage.tracing import toggle_tracing, get_tracing_status, get_in_memory_exporter, get_sqlite_exporter
```

The exact accessor function names depend on the public API defined in section-02 and section-03. The key point is that the orchestrator needs access to:
1. `toggle_tracing(enabled: bool)` -- to flip the FilteringSpanProcessor flag
2. A way to query the current enabled state and config
3. The `InMemoryTraceExporter` instance (for `get_trace()`, `get_traces()`, `get_traces_for_scene()`)
4. The `SQLiteTraceExporter` instance (for fallback queries and the `traces` table)

### 5.5 Lifespan Integration

The `_lifespan` method in `SidestageOrchestrator` must call `shutdown_tracing()` during teardown to flush pending `BatchSpanProcessor` spans to SQLite:

```python
@asynccontextmanager
async def _lifespan(self, app: FastAPI):
    """Write PID file on startup, remove on shutdown."""
    self._write_pid_file()
    try:
        yield
    finally:
        shutdown_tracing()  # Flush pending spans before exit
        self._remove_pid_file()
```

### 5.6 Error Handling

- If the tracing module has not been initialized (e.g., `init_tracing()` was never called), the trace endpoints should return empty results or appropriate defaults rather than crashing. Guard with checks like `if exporter is None: return []`.
- The toggle endpoint should be idempotent -- toggling to the current state is a no-op.
- The status endpoint should work even when tracing is disabled, returning `enabled: false` and the config.

### 5.7 File Summary

Files to create:
- `/home/harald/src/sidestage/tests/unit/test_tracing_api.py` -- REST endpoint tests
- `/home/harald/src/sidestage/tests/unit/test_tracing_websocket.py` -- WebSocket message tests

Files to modify:
- `/home/harald/src/sidestage/src/sidestage/orchestrator.py` -- Add four route handlers in `_setup_routes()`, add `shutdown_tracing()` call in `_lifespan`, wire up the trace broadcast callback
- `/home/harald/src/sidestage/src/sidestage/schemas.py` -- Add `TracingToggleRequest` model (optional, could also be inline)
- `/home/harald/src/sidestage/src/sidestage/tracing/__init__.py` -- Ensure public API exposes accessor functions for the exporters and toggle (depends on section-02/03 implementation)