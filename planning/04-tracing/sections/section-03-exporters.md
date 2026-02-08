Now I have all the context needed to write the section. Let me produce the content.

# Section 03: Exporters -- InMemoryTraceExporter and SQLiteTraceExporter

## Overview

This section implements the two custom OpenTelemetry `SpanExporter` classes that form the persistence layer for the Sidestage tracing system. Both live in `/home/harald/src/sidestage/src/sidestage/tracing/exporters.py`.

- **InMemoryTraceExporter** -- A bounded in-memory store of recent traces with ring-buffer eviction, span serialization to dicts, query methods, and a callback hook for WebSocket broadcast.
- **SQLiteTraceExporter** -- A raw `sqlite3`-based persistence layer with two tables (`traces` and `spans`), retention cleanup, and a method to reload recent traces into the in-memory exporter on startup.

Both exporters implement the `opentelemetry.sdk.trace.export.SpanExporter` protocol. They are wired into the `TracerProvider` by section-02 (tracing-core) via `SimpleSpanProcessor` (in-memory) and `BatchSpanProcessor` (SQLite).

## Dependencies

- **section-01-tracing-config**: Provides `TraceConfig` with fields `max_traces_in_memory`, `max_traces_stored`, `max_trace_age_hours`. Available as `SidestageConfig.tracing`.
- **section-02-tracing-core**: Provides `FilteringSpanProcessor`, `init_tracing()`, `toggle_tracing()`, and `shutdown_tracing()`. The exporters are instantiated inside `init_tracing()` and passed to span processors.

## File Locations

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/src/sidestage/tracing/exporters.py` | Both exporter classes |
| `/home/harald/src/sidestage/tests/unit/test_exporters.py` | Unit tests for both exporters |

---

## Tests

All tests go in `/home/harald/src/sidestage/tests/unit/test_exporters.py`. The project uses `pytest` with `pytest-anyio` for async tests. The `conftest.py` at `/home/harald/src/sidestage/tests/conftest.py` auto-initializes a `SidestageConfig` singleton for every test via the `_init_config(tmp_path)` fixture.

### Shared Test Helpers

Tests need a helper to create OTel `ReadableSpan` objects (the type that exporters receive). The simplest approach is to use a real `TracerProvider` with no exporters, start and end spans, and collect them via a simple list-based exporter. Alternatively, construct mock `ReadableSpan` objects with the required attributes. Define a helper fixture or factory function.

Key attributes on a `ReadableSpan` that the exporters access:
- `context.trace_id` (int) and `context.span_id` (int) -- convert to hex strings via `format(trace_id, '032x')` and `format(span_id, '016x')`
- `parent` -- a `SpanContext` or `None`; if present, `parent.span_id` gives the parent span ID
- `name` (str)
- `kind` (`SpanKind` enum)
- `start_time` (int, nanoseconds since epoch)
- `end_time` (int, nanoseconds since epoch)
- `status` (a `Status` object with `status_code` and `description`)
- `attributes` (dict-like)
- `events` (list of `Event` objects, each with `name`, `timestamp`, `attributes`)

A practical approach: create a real `TracerProvider`, use a `SimpleSpanProcessor` wrapping a `SimpleSpanExporter` (from opentelemetry.sdk.trace.export.in_memory), start spans, end them, then feed the collected `ReadableSpan` instances to the exporter under test.

### InMemoryTraceExporter Tests

```python
# Test: export single span, retrieve by trace_id
#   - Create a span, export it, call get_trace(trace_id) and verify it returns
#     a list containing one serialized span dict.

# Test: export multiple spans for same trace, all returned together
#   - Create two spans with the same trace_id (parent + child), export both,
#     verify get_trace returns both in a single list.

# Test: ring buffer evicts oldest trace when max_traces_in_memory exceeded
#   - Set max_traces_in_memory=2, export spans for 3 different traces,
#     verify only the 2 most recent traces are retained.

# Test: get_traces_for_scene returns only traces with matching scene_id
#   - Export spans for two traces with different scene_id attributes,
#     query with one scene_id, verify only matching trace returned.

# Test: get_traces returns all traces ordered by time
#   - Export spans for multiple traces, call get_traces(), verify all
#     present and ordered by start_time descending (most recent first).

# Test: thread safety - concurrent export and get_trace calls don't crash
#   - Use threading to concurrently call export() and get_traces(),
#     verify no exceptions raised.

# Test: callback fires on each export (mock callback, verify called with span data)
#   - Provide a mock callback at construction, export a span, verify the
#     callback was called with the serialized span dict.

# Test: span serialization produces correct dict format (ms timestamps, all fields)
#   - Export a span with known attributes and events, verify the returned
#     dict has keys: trace_id, span_id, parent_span_id, name, kind,
#     start_time_ms, end_time_ms, duration_ms, status, attributes, events,
#     scene_id, event_id.

# Test: nanosecond-to-millisecond timestamp conversion is accurate
#   - Create a span with a known start_time in nanoseconds, export it,
#     verify start_time_ms == start_time_ns / 1_000_000.
```

### SQLiteTraceExporter Tests

```python
# Test: export creates traces and spans tables if they don't exist
#   - Create exporter with a fresh db_path, verify tables exist after init.

# Test: export single span creates trace summary row and span row
#   - Export one root span, query the traces and spans tables directly,
#     verify one row in each with correct values.

# Test: export multiple spans for same trace increments span_count
#   - Export two spans with the same trace_id, verify traces.span_count == 2.

# Test: query traces by scene_id returns correct results
#   - Export spans for two traces with different scene_id attributes,
#     call query method, verify filtering works.

# Test: query traces by event_id returns correct results
#   - Export a span with sidestage.event.id attribute, query by event_id,
#     verify correct trace returned.

# Test: query all traces (no filter) returns recent traces
#   - Export multiple traces, query with no filters, verify all returned
#     ordered by recency.

# Test: retention cleanup deletes traces older than max_trace_age_hours
#   - Insert a trace with created_at far in the past, run cleanup,
#     verify it was deleted.

# Test: retention cleanup enforces max_traces_stored limit
#   - Set max_traces_stored=2, insert 3 traces, run cleanup,
#     verify only 2 remain (the most recent).

# Test: reload_into_memory loads recent traces into InMemoryTraceExporter
#   - Export spans to SQLite, create a fresh InMemoryTraceExporter,
#     call reload_into_memory, verify the in-memory exporter now has the traces.

# Test: export handles sqlite3 errors gracefully (logs, doesn't raise)
#   - Provide an invalid db_path (e.g., read-only directory), verify export()
#     returns SpanExportResult and does not raise.

# Test: concurrent exports don't corrupt data (serialized via lock or WAL mode)
#   - Use threading to concurrently export spans, verify all spans are
#     persisted correctly.
```

---

## Implementation Details

### Span Serialization Function

Both exporters share a common serialization function that converts a `ReadableSpan` (from the OTel SDK) into a plain dict. This function should be module-level in `exporters.py`.

```python
def _serialize_span(span: "ReadableSpan") -> dict:
    """Convert an OTel ReadableSpan to a JSON-serializable dict.

    All timestamps are converted from nanoseconds (OTel native) to
    milliseconds (JavaScript-safe). Fields extracted:

    - trace_id, span_id, parent_span_id: hex strings
    - name, kind: strings
    - start_time_ms, end_time_ms, duration_ms: floats (milliseconds)
    - status: {code: str, description: str | None}
    - attributes: dict (shallow copy)
    - events: list of {name, timestamp_ms, attributes}
    - scene_id: extracted from attributes["sidestage.scene.id"] or None
    - event_id: extracted from attributes["sidestage.event.id"] or None
    """
```

Key conversion details:
- `trace_id` is an int; convert with `format(span.context.trace_id, '032x')`
- `span_id` is an int; convert with `format(span.context.span_id, '016x')`
- `parent_span_id`: check `span.parent` is not None, then `format(span.parent.span_id, '016x')`
- Nanoseconds to milliseconds: divide by `1_000_000`
- `kind`: use `span.kind.name` (e.g., `"INTERNAL"`, `"CLIENT"`)
- `status.status_code.name` gives `"UNSET"`, `"OK"`, or `"ERROR"`
- `attributes` is a `MappingProxy`; convert to regular dict
- Each event's `attributes` is also a `MappingProxy`

### InMemoryTraceExporter

```python
class InMemoryTraceExporter(SpanExporter):
    """In-memory trace storage with ring-buffer eviction and query support.

    Maintains a bounded OrderedDict of traces keyed by trace_id (hex string).
    Each value is a list of serialized span dicts. When the number of traces
    exceeds max_traces, the oldest trace is evicted.

    Thread-safe via threading.Lock. All public query methods acquire the lock.

    An optional callback function is called on each export with the list of
    serialized span dicts, enabling WebSocket broadcast of trace events.
    """

    def __init__(
        self,
        max_traces: int = 500,
        on_export_callback: Callable[[list[dict]], None] | None = None,
    ):
        ...

    def export(self, spans: Sequence["ReadableSpan"]) -> SpanExportResult:
        """Serialize spans, store by trace_id, evict if over limit, fire callback."""
        ...

    def shutdown(self) -> None:
        """Clear all stored traces."""
        ...

    def get_trace(self, trace_id: str) -> list[dict] | None:
        """Return all spans for a given trace_id, or None if not found."""
        ...

    def get_traces(self) -> list[dict]:
        """Return summary info for all stored traces, ordered by start_time descending."""
        ...

    def get_traces_for_scene(self, scene_id: str) -> list[dict]:
        """Return summary info for traces matching the given scene_id."""
        ...

    def load_spans(self, trace_id: str, spans: list[dict]) -> None:
        """Load pre-serialized spans into the buffer (used by SQLite reload)."""
        ...
```

Key implementation notes:

- Use `collections.OrderedDict` for insertion-order tracking. When a new trace_id would exceed `max_traces`, call `popitem(last=False)` to evict the oldest.
- When `export()` is called with spans from the same trace_id that already exists, append to the existing list (do not replace).
- The `on_export_callback` receives the list of newly serialized span dicts (not the entire trace). The callback is called outside the lock to avoid deadlocks.
- The `get_traces()` method returns trace summaries (not full span lists). Each summary includes: `trace_id`, `scene_id`, `event_id`, `start_time_ms` (earliest span), `end_time_ms` (latest span), `duration_ms`, `span_count`, `root_span_name` (name of the span with no parent).
- `load_spans()` is used by the SQLite exporter's `reload_into_memory()` to populate the in-memory buffer on startup.

### SQLiteTraceExporter

```python
class SQLiteTraceExporter(SpanExporter):
    """SQLite-based trace persistence using raw sqlite3.

    Manages its own sqlite3 connection. Creates two tables on init:
    - traces: summary row per trace (PK: trace_id)
    - spans: one row per span (PK: span_id, FK: trace_id)

    The export() method receives batches from BatchSpanProcessor (runs in
    a background thread). Each batch is written in a single transaction.

    Consistent with the existing Storage class pattern (raw sqlite3, no ORM).
    """

    def __init__(self, db_path: Path, max_traces_stored: int = 5000, max_trace_age_hours: int = 72):
        ...

    def _init_tables(self) -> None:
        """Create traces and spans tables with indexes if they don't exist."""
        ...

    def export(self, spans: Sequence["ReadableSpan"]) -> SpanExportResult:
        """Serialize and persist spans in a single transaction.

        For each span:
        1. Serialize to dict via _serialize_span()
        2. INSERT into spans table
        3. UPSERT into traces table (increment span_count, update end_time_ms)

        Returns SUCCESS on success, FAILURE on error (logged, never raised).
        """
        ...

    def shutdown(self) -> None:
        """Close the sqlite3 connection."""
        ...

    def query_traces(
        self,
        scene_id: str | None = None,
        event_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Query trace summaries with optional filtering.

        Returns list of dicts with keys: trace_id, scene_id, event_id,
        event_type, start_time_ms, end_time_ms, root_span_name, span_count,
        created_at. Ordered by start_time_ms descending.
        """
        ...

    def query_spans(self, trace_id: str) -> list[dict]:
        """Return all spans for a trace_id as deserialized dicts."""
        ...

    def run_retention_cleanup(self) -> int:
        """Delete old traces and enforce max_traces_stored.

        1. Delete traces where created_at < now - max_trace_age_hours
        2. If remaining count > max_traces_stored, delete oldest excess
        3. CASCADE delete spans for removed traces (or explicit DELETE)

        Returns number of traces deleted.
        """
        ...

    def reload_into_memory(self, memory_exporter: "InMemoryTraceExporter", limit: int = 500) -> int:
        """Load recent traces from SQLite into the in-memory exporter.

        Queries the most recent `limit` traces, fetches their spans,
        and calls memory_exporter.load_spans() for each.

        Returns number of traces loaded.
        """
        ...
```

### Database Schema

The `_init_tables` method creates:

```sql
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    scene_id TEXT,
    event_id TEXT,
    event_type TEXT,
    start_time_ms REAL,
    end_time_ms REAL,
    root_span_name TEXT,
    span_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_traces_scene_id ON traces(scene_id);
CREATE INDEX IF NOT EXISTS idx_traces_event_id ON traces(event_id);
CREATE INDEX IF NOT EXISTS idx_traces_created_at ON traces(created_at);

CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    name TEXT NOT NULL,
    kind TEXT,
    start_time_ms REAL,
    end_time_ms REAL,
    status_code TEXT,
    attributes_json TEXT,
    events_json TEXT,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
```

Note: `PRAGMA foreign_keys = ON` must be set on each connection to enable cascade deletes.

### Traces Table Upsert Logic

When exporting a batch of spans, the traces summary row is upserted. For each unique trace_id in the batch:

1. If the trace does not exist yet: INSERT with `span_count = <spans in this batch>`, `start_time_ms` and `end_time_ms` from the span data, `scene_id` and `event_id` extracted from the root span's attributes (the span with no parent), and `root_span_name` from the root span's name.
2. If the trace already exists: UPDATE to increment `span_count`, expand the time range (`start_time_ms = MIN(existing, new)`, `end_time_ms = MAX(existing, new)`).

Use SQLite's `INSERT ... ON CONFLICT(trace_id) DO UPDATE` (UPSERT) syntax.

### Error Handling

Both exporters must never propagate exceptions to the traced code. The `export()` method wraps all work in a try/except, logs errors, and returns `SpanExportResult.FAILURE` on error. The `SpanExportResult.SUCCESS` is returned on normal completion.

### Threading Considerations

- **InMemoryTraceExporter**: Uses a `threading.Lock` to protect the `OrderedDict`. The `SimpleSpanProcessor` calls `export()` synchronously on the thread that ends the span (typically the asyncio event loop thread). Query methods are called from API handler coroutines (also on the event loop thread), but could be called from any thread. The lock ensures safety.
- **SQLiteTraceExporter**: The `BatchSpanProcessor` calls `export()` from a dedicated background thread. The `query_traces()` and `query_spans()` methods are called from API handlers (asyncio event loop thread). Since sqlite3 connections are not thread-safe by default, either: (a) use `check_same_thread=False` and protect with a `threading.Lock`, or (b) create a new connection per query call. Option (a) is simpler and more efficient for this low-volume application.

### Integration with init_tracing()

Section-02 (tracing-core) defines `init_tracing(config, campaign_name, db_path)`. That function instantiates both exporters and wires them into the TracerProvider. The relevant wiring (for context, not to implement in this section):

1. `InMemoryTraceExporter(max_traces=config.tracing.max_traces_in_memory, on_export_callback=<ws_broadcast>)` wrapped in `SimpleSpanProcessor`, wrapped in `FilteringSpanProcessor`.
2. `SQLiteTraceExporter(db_path=db_path, max_traces_stored=config.tracing.max_traces_stored, max_trace_age_hours=config.tracing.max_trace_age_hours)` wrapped in `BatchSpanProcessor`, wrapped in `FilteringSpanProcessor`.
3. After both are created: `sqlite_exporter.run_retention_cleanup()` and `sqlite_exporter.reload_into_memory(memory_exporter)`.

The exporters themselves are self-contained and testable in isolation. They receive `ReadableSpan` sequences and produce serialized output.

### Imports Required

```python
import json
import logging
import sqlite3
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
```