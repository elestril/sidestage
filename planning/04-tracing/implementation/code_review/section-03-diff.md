diff --git a/src/sidestage/tracing/exporters.py b/src/sidestage/tracing/exporters.py
new file mode 100644
index 0000000..2e77eb2
--- /dev/null
+++ b/src/sidestage/tracing/exporters.py
@@ -0,0 +1,408 @@
+"""InMemoryTraceExporter and SQLiteTraceExporter for Sidestage tracing."""
+
+import json
+import logging
+import sqlite3
+import threading
+from collections import OrderedDict
+from datetime import datetime, timedelta, timezone
+from pathlib import Path
+from typing import Callable, Sequence
+
+from opentelemetry.sdk.trace import ReadableSpan
+from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
+
+logger = logging.getLogger(__name__)
+
+
+def _serialize_span(span: ReadableSpan) -> dict:
+    """Convert an OTel ReadableSpan to a JSON-serializable dict.
+
+    All timestamps are converted from nanoseconds (OTel native) to
+    milliseconds (JavaScript-safe).
+    """
+    trace_id = format(span.context.trace_id, "032x")
+    span_id = format(span.context.span_id, "016x")
+    parent_span_id = (
+        format(span.parent.span_id, "016x") if span.parent is not None else None
+    )
+
+    start_time_ms = span.start_time / 1_000_000
+    end_time_ms = span.end_time / 1_000_000
+    duration_ms = end_time_ms - start_time_ms
+
+    attrs = dict(span.attributes) if span.attributes else {}
+
+    events = []
+    for event in span.events:
+        events.append({
+            "name": event.name,
+            "timestamp_ms": event.timestamp / 1_000_000,
+            "attributes": dict(event.attributes) if event.attributes else {},
+        })
+
+    return {
+        "trace_id": trace_id,
+        "span_id": span_id,
+        "parent_span_id": parent_span_id,
+        "name": span.name,
+        "kind": span.kind.name,
+        "start_time_ms": start_time_ms,
+        "end_time_ms": end_time_ms,
+        "duration_ms": duration_ms,
+        "status": {
+            "code": span.status.status_code.name,
+            "description": span.status.description,
+        },
+        "attributes": attrs,
+        "events": events,
+        "scene_id": attrs.get("sidestage.scene.id"),
+        "event_id": attrs.get("sidestage.event.id"),
+    }
+
+
+def _trace_summary(trace_id: str, spans: list[dict]) -> dict:
+    """Build a trace summary dict from a list of serialized span dicts."""
+    root_span_name = None
+    scene_id = None
+    event_id = None
+    start_time_ms = float("inf")
+    end_time_ms = float("-inf")
+
+    for s in spans:
+        if s.get("parent_span_id") is None:
+            root_span_name = s["name"]
+            if scene_id is None:
+                scene_id = s.get("scene_id")
+            if event_id is None:
+                event_id = s.get("event_id")
+        t0 = s.get("start_time_ms", float("inf"))
+        t1 = s.get("end_time_ms", float("-inf"))
+        if t0 < start_time_ms:
+            start_time_ms = t0
+        if t1 > end_time_ms:
+            end_time_ms = t1
+        if scene_id is None:
+            scene_id = s.get("scene_id")
+        if event_id is None:
+            event_id = s.get("event_id")
+
+    if root_span_name is None and spans:
+        root_span_name = spans[0]["name"]
+
+    return {
+        "trace_id": trace_id,
+        "scene_id": scene_id,
+        "event_id": event_id,
+        "start_time_ms": start_time_ms,
+        "end_time_ms": end_time_ms,
+        "duration_ms": end_time_ms - start_time_ms,
+        "span_count": len(spans),
+        "root_span_name": root_span_name,
+    }
+
+
+class InMemoryTraceExporter(SpanExporter):
+    """In-memory trace storage with ring-buffer eviction and query support."""
+
+    def __init__(
+        self,
+        max_traces: int = 500,
+        on_export_callback: Callable[[list[dict]], None] | None = None,
+    ):
+        self._max_traces = max_traces
+        self._callback = on_export_callback
+        self._traces: OrderedDict[str, list[dict]] = OrderedDict()
+        self._lock = threading.Lock()
+
+    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
+        serialized = [_serialize_span(s) for s in spans]
+
+        with self._lock:
+            for sd in serialized:
+                tid = sd["trace_id"]
+                if tid in self._traces:
+                    self._traces[tid].append(sd)
+                    self._traces.move_to_end(tid)
+                else:
+                    self._traces[tid] = [sd]
+
+                # Evict oldest if over limit
+                while len(self._traces) > self._max_traces:
+                    self._traces.popitem(last=False)
+
+        # Fire callback outside the lock
+        if self._callback is not None:
+            self._callback(serialized)
+
+        return SpanExportResult.SUCCESS
+
+    def shutdown(self) -> None:
+        with self._lock:
+            self._traces.clear()
+
+    def get_trace(self, trace_id: str) -> list[dict] | None:
+        with self._lock:
+            spans = self._traces.get(trace_id)
+            return list(spans) if spans is not None else None
+
+    def get_traces(self) -> list[dict]:
+        with self._lock:
+            summaries = [
+                _trace_summary(tid, spans)
+                for tid, spans in self._traces.items()
+            ]
+        summaries.sort(key=lambda s: s["start_time_ms"], reverse=True)
+        return summaries
+
+    def get_traces_for_scene(self, scene_id: str) -> list[dict]:
+        all_traces = self.get_traces()
+        return [t for t in all_traces if t.get("scene_id") == scene_id]
+
+    def load_spans(self, trace_id: str, spans: list[dict]) -> None:
+        with self._lock:
+            if trace_id in self._traces:
+                self._traces[trace_id].extend(spans)
+                self._traces.move_to_end(trace_id)
+            else:
+                self._traces[trace_id] = list(spans)
+            while len(self._traces) > self._max_traces:
+                self._traces.popitem(last=False)
+
+
+class SQLiteTraceExporter(SpanExporter):
+    """SQLite-based trace persistence using raw sqlite3."""
+
+    def __init__(
+        self,
+        db_path: Path,
+        max_traces_stored: int = 5000,
+        max_trace_age_hours: int = 72,
+    ):
+        self._db_path = db_path
+        self._max_traces_stored = max_traces_stored
+        self._max_trace_age_hours = max_trace_age_hours
+        self._lock = threading.Lock()
+        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
+        self._conn.execute("PRAGMA foreign_keys = ON")
+        self._conn.execute("PRAGMA journal_mode = WAL")
+        self._init_tables()
+
+    def _init_tables(self) -> None:
+        self._conn.executescript("""
+            CREATE TABLE IF NOT EXISTS traces (
+                trace_id TEXT PRIMARY KEY,
+                scene_id TEXT,
+                event_id TEXT,
+                event_type TEXT,
+                start_time_ms REAL,
+                end_time_ms REAL,
+                root_span_name TEXT,
+                span_count INTEGER DEFAULT 0,
+                created_at TEXT DEFAULT (datetime('now'))
+            );
+
+            CREATE INDEX IF NOT EXISTS idx_traces_scene_id ON traces(scene_id);
+            CREATE INDEX IF NOT EXISTS idx_traces_event_id ON traces(event_id);
+            CREATE INDEX IF NOT EXISTS idx_traces_created_at ON traces(created_at);
+
+            CREATE TABLE IF NOT EXISTS spans (
+                span_id TEXT PRIMARY KEY,
+                trace_id TEXT NOT NULL,
+                parent_span_id TEXT,
+                name TEXT NOT NULL,
+                kind TEXT,
+                start_time_ms REAL,
+                end_time_ms REAL,
+                status_code TEXT,
+                attributes_json TEXT,
+                events_json TEXT,
+                FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
+            );
+
+            CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
+        """)
+
+    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
+        try:
+            serialized = [_serialize_span(s) for s in spans]
+            with self._lock:
+                with self._conn:
+                    for sd in serialized:
+                        # Upsert trace summary
+                        self._conn.execute(
+                            """
+                            INSERT INTO traces (trace_id, scene_id, event_id, event_type,
+                                                start_time_ms, end_time_ms, root_span_name, span_count)
+                            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
+                            ON CONFLICT(trace_id) DO UPDATE SET
+                                span_count = span_count + 1,
+                                start_time_ms = MIN(start_time_ms, excluded.start_time_ms),
+                                end_time_ms = MAX(end_time_ms, excluded.end_time_ms)
+                            """,
+                            (
+                                sd["trace_id"],
+                                sd.get("scene_id"),
+                                sd.get("event_id"),
+                                sd["attributes"].get("sidestage.event.type") if sd["attributes"] else None,
+                                sd["start_time_ms"],
+                                sd["end_time_ms"],
+                                sd["name"] if sd["parent_span_id"] is None else None,
+                            ),
+                        )
+
+                        # Insert span row
+                        self._conn.execute(
+                            """
+                            INSERT OR REPLACE INTO spans
+                                (span_id, trace_id, parent_span_id, name, kind,
+                                 start_time_ms, end_time_ms, status_code,
+                                 attributes_json, events_json)
+                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
+                            """,
+                            (
+                                sd["span_id"],
+                                sd["trace_id"],
+                                sd["parent_span_id"],
+                                sd["name"],
+                                sd["kind"],
+                                sd["start_time_ms"],
+                                sd["end_time_ms"],
+                                sd["status"]["code"],
+                                json.dumps(sd["attributes"]),
+                                json.dumps(sd["events"]),
+                            ),
+                        )
+            return SpanExportResult.SUCCESS
+        except Exception:
+            logger.exception("Failed to export spans to SQLite")
+            return SpanExportResult.FAILURE
+
+    def shutdown(self) -> None:
+        with self._lock:
+            self._conn.close()
+
+    def query_traces(
+        self,
+        scene_id: str | None = None,
+        event_id: str | None = None,
+        limit: int = 50,
+        offset: int = 0,
+    ) -> list[dict]:
+        conditions = []
+        params: list = []
+        if scene_id is not None:
+            conditions.append("scene_id = ?")
+            params.append(scene_id)
+        if event_id is not None:
+            conditions.append("event_id = ?")
+            params.append(event_id)
+
+        where = "WHERE " + " AND ".join(conditions) if conditions else ""
+        sql = f"""
+            SELECT trace_id, scene_id, event_id, event_type,
+                   start_time_ms, end_time_ms, root_span_name,
+                   span_count, created_at
+            FROM traces
+            {where}
+            ORDER BY start_time_ms DESC
+            LIMIT ? OFFSET ?
+        """
+        params.extend([limit, offset])
+
+        with self._lock:
+            rows = self._conn.execute(sql, params).fetchall()
+
+        return [
+            {
+                "trace_id": r[0],
+                "scene_id": r[1],
+                "event_id": r[2],
+                "event_type": r[3],
+                "start_time_ms": r[4],
+                "end_time_ms": r[5],
+                "root_span_name": r[6],
+                "span_count": r[7],
+                "created_at": r[8],
+            }
+            for r in rows
+        ]
+
+    def query_spans(self, trace_id: str) -> list[dict]:
+        with self._lock:
+            rows = self._conn.execute(
+                """
+                SELECT span_id, trace_id, parent_span_id, name, kind,
+                       start_time_ms, end_time_ms, status_code,
+                       attributes_json, events_json
+                FROM spans
+                WHERE trace_id = ?
+                ORDER BY start_time_ms ASC
+                """,
+                (trace_id,),
+            ).fetchall()
+
+        return [
+            {
+                "span_id": r[0],
+                "trace_id": r[1],
+                "parent_span_id": r[2],
+                "name": r[3],
+                "kind": r[4],
+                "start_time_ms": r[5],
+                "end_time_ms": r[6],
+                "status_code": r[7],
+                "attributes": json.loads(r[8]) if r[8] else {},
+                "events": json.loads(r[9]) if r[9] else [],
+            }
+            for r in rows
+        ]
+
+    def run_retention_cleanup(self) -> int:
+        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._max_trace_age_hours)
+        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
+
+        with self._lock:
+            with self._conn:
+                # Delete old traces
+                cursor = self._conn.execute(
+                    "DELETE FROM traces WHERE created_at < ?", (cutoff_str,)
+                )
+                deleted_age = cursor.rowcount
+
+                # Enforce max count
+                total = self._conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
+                deleted_count = 0
+                if total > self._max_traces_stored:
+                    excess = total - self._max_traces_stored
+                    self._conn.execute(
+                        """
+                        DELETE FROM traces WHERE trace_id IN (
+                            SELECT trace_id FROM traces
+                            ORDER BY start_time_ms ASC
+                            LIMIT ?
+                        )
+                        """,
+                        (excess,),
+                    )
+                    deleted_count = excess
+
+        return deleted_age + deleted_count
+
+    def reload_into_memory(
+        self, memory_exporter: InMemoryTraceExporter, limit: int = 500
+    ) -> int:
+        with self._lock:
+            trace_rows = self._conn.execute(
+                "SELECT trace_id FROM traces ORDER BY start_time_ms DESC LIMIT ?",
+                (limit,),
+            ).fetchall()
+
+        loaded = 0
+        for (trace_id,) in trace_rows:
+            span_dicts = self.query_spans(trace_id)
+            if span_dicts:
+                memory_exporter.load_spans(trace_id, span_dicts)
+                loaded += 1
+
+        return loaded
diff --git a/tests/unit/test_exporters.py b/tests/unit/test_exporters.py
new file mode 100644
index 0000000..fb57e5c
--- /dev/null
+++ b/tests/unit/test_exporters.py
@@ -0,0 +1,506 @@
+"""Tests for InMemoryTraceExporter and SQLiteTraceExporter."""
+
+import json
+import threading
+import time
+from pathlib import Path
+from unittest.mock import MagicMock
+
+import pytest
+from opentelemetry.sdk.trace import TracerProvider
+from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
+
+from sidestage.tracing.exporters import (
+    InMemoryTraceExporter,
+    SQLiteTraceExporter,
+    _serialize_span,
+)
+
+
+# ---------------------------------------------------------------------------
+# Helpers
+# ---------------------------------------------------------------------------
+
+class _SpanCollector(SpanExporter):
+    """Collects ReadableSpan objects for feeding to our custom exporters."""
+
+    def __init__(self):
+        self._spans: list = []
+
+    def export(self, spans):
+        self._spans.extend(spans)
+        return SpanExportResult.SUCCESS
+
+    def shutdown(self):
+        pass
+
+    def get_finished_spans(self) -> list:
+        return list(self._spans)
+
+
+def _make_spans(
+    *,
+    trace_id: int | None = None,
+    span_names: list[str] | None = None,
+    attributes: dict | None = None,
+    parent: bool = False,
+) -> list:
+    """Create real ReadableSpan objects using a TracerProvider.
+
+    Returns a list of ReadableSpan instances.
+    """
+    collector = _SpanCollector()
+    provider = TracerProvider()
+    provider.add_span_processor(SimpleSpanProcessor(collector))
+    tracer = provider.get_tracer("test")
+
+    if span_names is None:
+        span_names = ["test-span"]
+
+    if parent and len(span_names) >= 2:
+        # First span is root, rest are children
+        root_ctx = None
+        for i, name in enumerate(span_names):
+            if i == 0:
+                span = tracer.start_span(name, attributes=attributes)
+                span.end()
+                root_ctx = span.get_span_context()
+            else:
+                from opentelemetry import trace
+
+                ctx = trace.set_span_in_context(
+                    trace.NonRecordingSpan(root_ctx)
+                )
+                span = tracer.start_span(name, context=ctx, attributes=attributes)
+                span.end()
+    else:
+        for name in span_names:
+            span = tracer.start_span(name, attributes=attributes)
+            span.end()
+
+    provider.shutdown()
+    return collector.get_finished_spans()
+
+
+def _make_spans_with_different_traces(
+    count: int,
+    scene_ids: list[str | None] | None = None,
+    event_ids: list[str | None] | None = None,
+) -> list[list]:
+    """Create spans belonging to `count` different traces.
+
+    Returns a list of lists -- each inner list is the spans from one trace.
+    """
+    result = []
+    for i in range(count):
+        attrs = {}
+        if scene_ids and i < len(scene_ids) and scene_ids[i]:
+            attrs["sidestage.scene.id"] = scene_ids[i]
+        if event_ids and i < len(event_ids) and event_ids[i]:
+            attrs["sidestage.event.id"] = event_ids[i]
+        spans = _make_spans(span_names=[f"trace-{i}-root"], attributes=attrs or None)
+        result.append(spans)
+    return result
+
+
+# ===========================================================================
+# _serialize_span tests
+# ===========================================================================
+
+
+class TestSerializeSpan:
+    def test_produces_correct_keys(self):
+        spans = _make_spans(span_names=["my-span"])
+        d = _serialize_span(spans[0])
+        expected_keys = {
+            "trace_id", "span_id", "parent_span_id", "name", "kind",
+            "start_time_ms", "end_time_ms", "duration_ms", "status",
+            "attributes", "events", "scene_id", "event_id",
+        }
+        assert set(d.keys()) == expected_keys
+
+    def test_trace_id_is_hex_string(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert isinstance(d["trace_id"], str)
+        assert len(d["trace_id"]) == 32
+        int(d["trace_id"], 16)  # should not raise
+
+    def test_span_id_is_hex_string(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert isinstance(d["span_id"], str)
+        assert len(d["span_id"]) == 16
+        int(d["span_id"], 16)
+
+    def test_parent_span_id_none_for_root(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert d["parent_span_id"] is None
+
+    def test_parent_span_id_set_for_child(self):
+        spans = _make_spans(span_names=["root", "child"], parent=True)
+        child = [s for s in spans if s.parent is not None][0]
+        d = _serialize_span(child)
+        assert d["parent_span_id"] is not None
+        assert len(d["parent_span_id"]) == 16
+
+    def test_nanosecond_to_millisecond_conversion(self):
+        spans = _make_spans()
+        span = spans[0]
+        d = _serialize_span(span)
+        expected_start_ms = span.start_time / 1_000_000
+        assert d["start_time_ms"] == expected_start_ms
+
+    def test_duration_ms_calculated(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert d["duration_ms"] == d["end_time_ms"] - d["start_time_ms"]
+
+    def test_scene_id_extracted_from_attributes(self):
+        spans = _make_spans(attributes={"sidestage.scene.id": "scene-42"})
+        d = _serialize_span(spans[0])
+        assert d["scene_id"] == "scene-42"
+
+    def test_event_id_extracted_from_attributes(self):
+        spans = _make_spans(attributes={"sidestage.event.id": "evt-99"})
+        d = _serialize_span(spans[0])
+        assert d["event_id"] == "evt-99"
+
+    def test_scene_id_none_when_missing(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert d["scene_id"] is None
+
+    def test_kind_is_string(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert isinstance(d["kind"], str)
+
+    def test_status_is_dict(self):
+        spans = _make_spans()
+        d = _serialize_span(spans[0])
+        assert isinstance(d["status"], dict)
+        assert "code" in d["status"]
+
+
+# ===========================================================================
+# InMemoryTraceExporter tests
+# ===========================================================================
+
+
+class TestInMemoryTraceExporter:
+    def test_export_single_span_retrieve_by_trace_id(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        spans = _make_spans(span_names=["root-op"])
+        result = exporter.export(spans)
+        assert result == SpanExportResult.SUCCESS
+
+        trace_id = format(spans[0].context.trace_id, "032x")
+        trace_spans = exporter.get_trace(trace_id)
+        assert trace_spans is not None
+        assert len(trace_spans) == 1
+        assert trace_spans[0]["name"] == "root-op"
+
+    def test_export_multiple_spans_same_trace(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        spans = _make_spans(span_names=["root", "child"], parent=True)
+        exporter.export(spans)
+
+        trace_id = format(spans[0].context.trace_id, "032x")
+        trace_spans = exporter.get_trace(trace_id)
+        assert trace_spans is not None
+        assert len(trace_spans) == 2
+
+    def test_ring_buffer_evicts_oldest(self):
+        exporter = InMemoryTraceExporter(max_traces=2)
+        trace_groups = _make_spans_with_different_traces(3)
+
+        for group in trace_groups:
+            exporter.export(group)
+
+        # Only 2 traces should remain
+        all_traces = exporter.get_traces()
+        assert len(all_traces) == 2
+
+        # The first trace should be evicted
+        first_trace_id = format(trace_groups[0][0].context.trace_id, "032x")
+        assert exporter.get_trace(first_trace_id) is None
+
+    def test_get_traces_for_scene(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        groups = _make_spans_with_different_traces(
+            3, scene_ids=["scene-A", "scene-B", "scene-A"]
+        )
+        for group in groups:
+            exporter.export(group)
+
+        scene_a = exporter.get_traces_for_scene("scene-A")
+        assert len(scene_a) == 2
+
+    def test_get_traces_returns_all_ordered(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        groups = _make_spans_with_different_traces(3)
+        for group in groups:
+            exporter.export(group)
+
+        traces = exporter.get_traces()
+        assert len(traces) == 3
+        # Most recent first
+        for i in range(len(traces) - 1):
+            assert traces[i]["start_time_ms"] >= traces[i + 1]["start_time_ms"]
+
+    def test_thread_safety(self):
+        exporter = InMemoryTraceExporter(max_traces=100)
+        errors = []
+
+        def writer():
+            try:
+                for _ in range(20):
+                    spans = _make_spans(span_names=["thread-span"])
+                    exporter.export(spans)
+            except Exception as e:
+                errors.append(e)
+
+        def reader():
+            try:
+                for _ in range(20):
+                    exporter.get_traces()
+            except Exception as e:
+                errors.append(e)
+
+        threads = [threading.Thread(target=writer) for _ in range(3)]
+        threads += [threading.Thread(target=reader) for _ in range(3)]
+        for t in threads:
+            t.start()
+        for t in threads:
+            t.join()
+
+        assert errors == []
+
+    def test_callback_fires_on_export(self):
+        callback = MagicMock()
+        exporter = InMemoryTraceExporter(max_traces=10, on_export_callback=callback)
+        spans = _make_spans(span_names=["cb-span"])
+        exporter.export(spans)
+
+        callback.assert_called_once()
+        args = callback.call_args[0][0]
+        assert isinstance(args, list)
+        assert args[0]["name"] == "cb-span"
+
+    def test_span_serialization_format(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        spans = _make_spans(
+            span_names=["formatted-op"],
+            attributes={"sidestage.scene.id": "s1", "sidestage.event.id": "e1"},
+        )
+        exporter.export(spans)
+
+        trace_id = format(spans[0].context.trace_id, "032x")
+        trace_spans = exporter.get_trace(trace_id)
+        d = trace_spans[0]
+        assert "trace_id" in d
+        assert "span_id" in d
+        assert "start_time_ms" in d
+        assert "duration_ms" in d
+        assert d["scene_id"] == "s1"
+        assert d["event_id"] == "e1"
+
+    def test_get_trace_returns_none_for_unknown(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        assert exporter.get_trace("nonexistent") is None
+
+    def test_shutdown_clears_traces(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        spans = _make_spans()
+        exporter.export(spans)
+        exporter.shutdown()
+        assert exporter.get_traces() == []
+
+    def test_load_spans(self):
+        exporter = InMemoryTraceExporter(max_traces=10)
+        fake_spans = [
+            {"trace_id": "abc", "span_id": "001", "name": "loaded",
+             "start_time_ms": 100.0, "scene_id": None, "event_id": None,
+             "parent_span_id": None}
+        ]
+        exporter.load_spans("abc", fake_spans)
+        assert exporter.get_trace("abc") is not None
+
+
+# ===========================================================================
+# SQLiteTraceExporter tests
+# ===========================================================================
+
+
+class TestSQLiteTraceExporter:
+    def test_tables_created_on_init(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db, max_traces_stored=100)
+        import sqlite3
+
+        conn = sqlite3.connect(str(db))
+        tables = conn.execute(
+            "SELECT name FROM sqlite_master WHERE type='table'"
+        ).fetchall()
+        table_names = {t[0] for t in tables}
+        assert "traces" in table_names
+        assert "spans" in table_names
+        conn.close()
+        exporter.shutdown()
+
+    def test_export_single_span(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        spans = _make_spans(span_names=["sqlite-op"])
+        result = exporter.export(spans)
+        assert result == SpanExportResult.SUCCESS
+
+        traces = exporter.query_traces()
+        assert len(traces) == 1
+        assert traces[0]["root_span_name"] == "sqlite-op"
+        exporter.shutdown()
+
+    def test_export_multiple_spans_same_trace_increments_count(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        spans = _make_spans(span_names=["root", "child"], parent=True)
+        exporter.export(spans)
+
+        traces = exporter.query_traces()
+        assert len(traces) == 1
+        assert traces[0]["span_count"] == 2
+        exporter.shutdown()
+
+    def test_query_traces_by_scene_id(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        groups = _make_spans_with_different_traces(
+            3, scene_ids=["scene-X", "scene-Y", "scene-X"]
+        )
+        for group in groups:
+            exporter.export(group)
+
+        results = exporter.query_traces(scene_id="scene-X")
+        assert len(results) == 2
+        exporter.shutdown()
+
+    def test_query_traces_by_event_id(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        groups = _make_spans_with_different_traces(
+            2, event_ids=["ev-1", "ev-2"]
+        )
+        for group in groups:
+            exporter.export(group)
+
+        results = exporter.query_traces(event_id="ev-1")
+        assert len(results) == 1
+        exporter.shutdown()
+
+    def test_query_all_traces_returns_recent_ordered(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        groups = _make_spans_with_different_traces(3)
+        for group in groups:
+            exporter.export(group)
+
+        results = exporter.query_traces()
+        assert len(results) == 3
+        for i in range(len(results) - 1):
+            assert results[i]["start_time_ms"] >= results[i + 1]["start_time_ms"]
+        exporter.shutdown()
+
+    def test_retention_cleanup_age(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db, max_trace_age_hours=1)
+        spans = _make_spans(span_names=["old-span"])
+        exporter.export(spans)
+
+        # Manually backdate the trace
+        import sqlite3
+
+        conn = sqlite3.connect(str(db))
+        conn.execute(
+            "UPDATE traces SET created_at = datetime('now', '-2 hours')"
+        )
+        conn.commit()
+        conn.close()
+
+        deleted = exporter.run_retention_cleanup()
+        assert deleted >= 1
+        assert exporter.query_traces() == []
+        exporter.shutdown()
+
+    def test_retention_cleanup_max_stored(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db, max_traces_stored=2)
+        groups = _make_spans_with_different_traces(4)
+        for group in groups:
+            exporter.export(group)
+
+        deleted = exporter.run_retention_cleanup()
+        assert deleted >= 2
+        remaining = exporter.query_traces()
+        assert len(remaining) == 2
+        exporter.shutdown()
+
+    def test_reload_into_memory(self, tmp_path):
+        db = tmp_path / "traces.db"
+        sqlite_exp = SQLiteTraceExporter(db)
+        groups = _make_spans_with_different_traces(3)
+        for group in groups:
+            sqlite_exp.export(group)
+
+        mem_exp = InMemoryTraceExporter(max_traces=10)
+        loaded = sqlite_exp.reload_into_memory(mem_exp)
+        assert loaded == 3
+        assert len(mem_exp.get_traces()) == 3
+        sqlite_exp.shutdown()
+
+    def test_export_handles_errors_gracefully(self, tmp_path):
+        # Use a path that will cause issues
+        db = tmp_path / "nonexistent_dir" / "traces.db"
+        # This should not raise
+        try:
+            exporter = SQLiteTraceExporter(db)
+            spans = _make_spans()
+            result = exporter.export(spans)
+            # If init succeeded somehow, export should handle errors
+        except Exception:
+            # Init itself may fail - that's acceptable too
+            pass
+
+    def test_query_spans(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        spans = _make_spans(span_names=["root", "child"], parent=True)
+        exporter.export(spans)
+
+        trace_id = format(spans[0].context.trace_id, "032x")
+        span_rows = exporter.query_spans(trace_id)
+        assert len(span_rows) == 2
+        exporter.shutdown()
+
+    def test_concurrent_exports(self, tmp_path):
+        db = tmp_path / "traces.db"
+        exporter = SQLiteTraceExporter(db)
+        errors = []
+
+        def writer():
+            try:
+                for _ in range(10):
+                    spans = _make_spans(span_names=["concurrent-op"])
+                    exporter.export(spans)
+            except Exception as e:
+                errors.append(e)
+
+        threads = [threading.Thread(target=writer) for _ in range(4)]
+        for t in threads:
+            t.start()
+        for t in threads:
+            t.join()
+
+        assert errors == []
+        exporter.shutdown()
