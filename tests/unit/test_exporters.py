"""Tests for InMemoryTraceExporter and SQLiteTraceExporter."""

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from sidestage.tracing.exporters import (
    InMemoryTraceExporter,
    SQLiteTraceExporter,
    _serialize_span,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SpanCollector(SpanExporter):
    """Collects ReadableSpan objects for feeding to our custom exporters."""

    def __init__(self):
        self._spans: list = []

    def export(self, spans):
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def get_finished_spans(self) -> list:
        return list(self._spans)


def _make_spans(
    *,
    span_names: list[str] | None = None,
    attributes: dict | None = None,
    parent: bool = False,
) -> list:
    """Create real ReadableSpan objects using a TracerProvider.

    Returns a list of ReadableSpan instances.
    """
    collector = _SpanCollector()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(collector))
    tracer = provider.get_tracer("test")

    if span_names is None:
        span_names = ["test-span"]

    if parent and len(span_names) >= 2:
        # First span is root, rest are children
        root_ctx = None
        for i, name in enumerate(span_names):
            if i == 0:
                span = tracer.start_span(name, attributes=attributes)
                span.end()
                root_ctx = span.get_span_context()
            else:
                from opentelemetry import trace

                ctx = trace.set_span_in_context(
                    trace.NonRecordingSpan(root_ctx)
                )
                span = tracer.start_span(name, context=ctx, attributes=attributes)
                span.end()
    else:
        for name in span_names:
            span = tracer.start_span(name, attributes=attributes)
            span.end()

    provider.shutdown()
    return collector.get_finished_spans()


def _make_spans_with_different_traces(
    count: int,
    scene_ids: list[str | None] | None = None,
    event_ids: list[str | None] | None = None,
) -> list[list]:
    """Create spans belonging to `count` different traces.

    Returns a list of lists -- each inner list is the spans from one trace.
    """
    result = []
    for i in range(count):
        attrs = {}
        if scene_ids and i < len(scene_ids) and scene_ids[i]:
            attrs["sidestage.scene.id"] = scene_ids[i]
        if event_ids and i < len(event_ids) and event_ids[i]:
            attrs["sidestage.event.id"] = event_ids[i]
        spans = _make_spans(span_names=[f"trace-{i}-root"], attributes=attrs or None)
        result.append(spans)
    return result


# ===========================================================================
# _serialize_span tests
# ===========================================================================


class TestSerializeSpan:
    def test_produces_correct_keys(self):
        spans = _make_spans(span_names=["my-span"])
        d = _serialize_span(spans[0])
        expected_keys = {
            "trace_id", "span_id", "parent_span_id", "name", "kind",
            "start_time_ms", "end_time_ms", "duration_ms", "status",
            "attributes", "events", "scene_id", "event_id",
        }
        assert set(d.keys()) == expected_keys

    def test_trace_id_is_hex_string(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert isinstance(d["trace_id"], str)
        assert len(d["trace_id"]) == 32
        int(d["trace_id"], 16)  # should not raise

    def test_span_id_is_hex_string(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert isinstance(d["span_id"], str)
        assert len(d["span_id"]) == 16
        int(d["span_id"], 16)

    def test_parent_span_id_none_for_root(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert d["parent_span_id"] is None

    def test_parent_span_id_set_for_child(self):
        spans = _make_spans(span_names=["root", "child"], parent=True)
        child = [s for s in spans if s.parent is not None][0]
        d = _serialize_span(child)
        assert d["parent_span_id"] is not None
        assert len(d["parent_span_id"]) == 16

    def test_nanosecond_to_millisecond_conversion(self):
        spans = _make_spans()
        span = spans[0]
        d = _serialize_span(span)
        expected_start_ms = span.start_time / 1_000_000
        assert d["start_time_ms"] == expected_start_ms

    def test_duration_ms_calculated(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert d["duration_ms"] == d["end_time_ms"] - d["start_time_ms"]

    def test_scene_id_extracted_from_attributes(self):
        spans = _make_spans(attributes={"sidestage.scene.id": "scene-42"})
        d = _serialize_span(spans[0])
        assert d["scene_id"] == "scene-42"

    def test_event_id_extracted_from_attributes(self):
        spans = _make_spans(attributes={"sidestage.event.id": "evt-99"})
        d = _serialize_span(spans[0])
        assert d["event_id"] == "evt-99"

    def test_scene_id_none_when_missing(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert d["scene_id"] is None

    def test_kind_is_string(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert isinstance(d["kind"], str)

    def test_status_is_dict(self):
        spans = _make_spans()
        d = _serialize_span(spans[0])
        assert isinstance(d["status"], dict)
        assert "code" in d["status"]


# ===========================================================================
# InMemoryTraceExporter tests
# ===========================================================================


class TestInMemoryTraceExporter:
    def test_export_single_span_retrieve_by_trace_id(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        spans = _make_spans(span_names=["root-op"])
        result = exporter.export(spans)
        assert result == SpanExportResult.SUCCESS

        trace_id = format(spans[0].context.trace_id, "032x")
        trace_spans = exporter.get_trace(trace_id)
        assert trace_spans is not None
        assert len(trace_spans) == 1
        assert trace_spans[0]["name"] == "root-op"

    def test_export_multiple_spans_same_trace(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        spans = _make_spans(span_names=["root", "child"], parent=True)
        exporter.export(spans)

        trace_id = format(spans[0].context.trace_id, "032x")
        trace_spans = exporter.get_trace(trace_id)
        assert trace_spans is not None
        assert len(trace_spans) == 2

    def test_ring_buffer_evicts_oldest(self):
        exporter = InMemoryTraceExporter(max_traces=2)
        trace_groups = _make_spans_with_different_traces(3)

        for group in trace_groups:
            exporter.export(group)

        # Only 2 traces should remain
        all_traces = exporter.get_traces()
        assert len(all_traces) == 2

        # The first trace should be evicted
        first_trace_id = format(trace_groups[0][0].context.trace_id, "032x")
        assert exporter.get_trace(first_trace_id) is None

    def test_get_traces_for_scene(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        groups = _make_spans_with_different_traces(
            3, scene_ids=["scene-A", "scene-B", "scene-A"]
        )
        for group in groups:
            exporter.export(group)

        scene_a = exporter.get_traces_for_scene("scene-A")
        assert len(scene_a) == 2

    def test_get_traces_returns_all_ordered(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        groups = _make_spans_with_different_traces(3)
        for group in groups:
            exporter.export(group)

        traces = exporter.get_traces()
        assert len(traces) == 3
        # Most recent first
        for i in range(len(traces) - 1):
            assert traces[i]["start_time_ms"] >= traces[i + 1]["start_time_ms"]

    def test_thread_safety(self):
        exporter = InMemoryTraceExporter(max_traces=100)
        errors = []

        def writer():
            try:
                for _ in range(20):
                    spans = _make_spans(span_names=["thread-span"])
                    exporter.export(spans)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(20):
                    exporter.get_traces()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_callback_fires_on_export(self):
        callback = MagicMock()
        exporter = InMemoryTraceExporter(max_traces=10, on_export_callback=callback)
        spans = _make_spans(span_names=["cb-span"])
        exporter.export(spans)

        callback.assert_called_once()
        args = callback.call_args[0][0]
        assert isinstance(args, list)
        assert args[0]["name"] == "cb-span"

    def test_span_serialization_format(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        spans = _make_spans(
            span_names=["formatted-op"],
            attributes={"sidestage.scene.id": "s1", "sidestage.event.id": "e1"},
        )
        exporter.export(spans)

        trace_id = format(spans[0].context.trace_id, "032x")
        trace_spans = exporter.get_trace(trace_id)
        d = trace_spans[0]
        assert "trace_id" in d
        assert "span_id" in d
        assert "start_time_ms" in d
        assert "duration_ms" in d
        assert d["scene_id"] == "s1"
        assert d["event_id"] == "e1"

    def test_get_trace_returns_none_for_unknown(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        assert exporter.get_trace("nonexistent") is None

    def test_shutdown_clears_traces(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        spans = _make_spans()
        exporter.export(spans)
        exporter.shutdown()
        assert exporter.get_traces() == []

    def test_load_spans(self):
        exporter = InMemoryTraceExporter(max_traces=10)
        fake_spans = [
            {"trace_id": "abc", "span_id": "001", "name": "loaded",
             "start_time_ms": 100.0, "scene_id": None, "event_id": None,
             "parent_span_id": None}
        ]
        exporter.load_spans("abc", fake_spans)
        assert exporter.get_trace("abc") is not None


# ===========================================================================
# SQLiteTraceExporter tests
# ===========================================================================


class TestSQLiteTraceExporter:
    def test_tables_created_on_init(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db, max_traces_stored=100)
        import sqlite3

        conn = sqlite3.connect(str(db))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "traces" in table_names
        assert "spans" in table_names
        conn.close()
        exporter.shutdown()

    def test_export_single_span(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        spans = _make_spans(span_names=["sqlite-op"])
        result = exporter.export(spans)
        assert result == SpanExportResult.SUCCESS

        traces = exporter.query_traces()
        assert len(traces) == 1
        assert traces[0]["root_span_name"] == "sqlite-op"
        exporter.shutdown()

    def test_export_multiple_spans_same_trace_increments_count(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        spans = _make_spans(span_names=["root", "child"], parent=True)
        exporter.export(spans)

        traces = exporter.query_traces()
        assert len(traces) == 1
        assert traces[0]["span_count"] == 2
        exporter.shutdown()

    def test_query_traces_by_scene_id(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        groups = _make_spans_with_different_traces(
            3, scene_ids=["scene-X", "scene-Y", "scene-X"]
        )
        for group in groups:
            exporter.export(group)

        results = exporter.query_traces(scene_id="scene-X")
        assert len(results) == 2
        exporter.shutdown()

    def test_query_traces_by_event_id(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        groups = _make_spans_with_different_traces(
            2, event_ids=["ev-1", "ev-2"]
        )
        for group in groups:
            exporter.export(group)

        results = exporter.query_traces(event_id="ev-1")
        assert len(results) == 1
        exporter.shutdown()

    def test_query_all_traces_returns_recent_ordered(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        groups = _make_spans_with_different_traces(3)
        for group in groups:
            exporter.export(group)

        results = exporter.query_traces()
        assert len(results) == 3
        for i in range(len(results) - 1):
            assert results[i]["start_time_ms"] >= results[i + 1]["start_time_ms"]
        exporter.shutdown()

    def test_retention_cleanup_age(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db, max_trace_age_hours=1)
        spans = _make_spans(span_names=["old-span"])
        exporter.export(spans)

        # Manually backdate the trace
        import sqlite3

        conn = sqlite3.connect(str(db))
        conn.execute(
            "UPDATE traces SET created_at = datetime('now', '-2 hours')"
        )
        conn.commit()
        conn.close()

        deleted = exporter.run_retention_cleanup()
        assert deleted >= 1
        assert exporter.query_traces() == []
        exporter.shutdown()

    def test_retention_cleanup_max_stored(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db, max_traces_stored=2)
        groups = _make_spans_with_different_traces(4)
        for group in groups:
            exporter.export(group)

        deleted = exporter.run_retention_cleanup()
        assert deleted >= 2
        remaining = exporter.query_traces()
        assert len(remaining) == 2
        exporter.shutdown()

    def test_reload_into_memory(self, tmp_path):
        db = tmp_path / "traces.db"
        sqlite_exp = SQLiteTraceExporter(db)
        groups = _make_spans_with_different_traces(3)
        for group in groups:
            sqlite_exp.export(group)

        mem_exp = InMemoryTraceExporter(max_traces=10)
        loaded = sqlite_exp.reload_into_memory(mem_exp)
        assert loaded == 3
        assert len(mem_exp.get_traces()) == 3
        sqlite_exp.shutdown()

    def test_export_handles_errors_gracefully(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        # Close the connection to force export errors
        exporter._conn.close()
        spans = _make_spans()
        result = exporter.export(spans)
        assert result == SpanExportResult.FAILURE

    def test_query_spans(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        spans = _make_spans(span_names=["root", "child"], parent=True)
        exporter.export(spans)

        trace_id = format(spans[0].context.trace_id, "032x")
        span_rows = exporter.query_spans(trace_id)
        assert len(span_rows) == 2
        exporter.shutdown()

    def test_query_spans_has_compatible_shape(self, tmp_path):
        """query_spans returns dicts with scene_id, event_id, duration_ms
        so they work with _trace_summary and load_spans."""
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        spans = _make_spans(
            span_names=["root-op"],
            attributes={"sidestage.scene.id": "s1", "sidestage.event.id": "e1"},
        )
        exporter.export(spans)

        trace_id = format(spans[0].context.trace_id, "032x")
        span_rows = exporter.query_spans(trace_id)
        d = span_rows[0]
        assert "scene_id" in d
        assert "event_id" in d
        assert "duration_ms" in d
        assert d["scene_id"] == "s1"
        assert d["event_id"] == "e1"
        exporter.shutdown()

    def test_shutdown_is_idempotent(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        exporter.shutdown()
        exporter.shutdown()  # Should not raise

    def test_concurrent_exports(self, tmp_path):
        db = tmp_path / "traces.db"
        exporter = SQLiteTraceExporter(db)
        errors = []

        def writer():
            try:
                for _ in range(10):
                    spans = _make_spans(span_names=["concurrent-op"])
                    exporter.export(spans)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        exporter.shutdown()
