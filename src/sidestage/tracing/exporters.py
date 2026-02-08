"""InMemoryTraceExporter and SQLiteTraceExporter for Sidestage tracing."""

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

logger = logging.getLogger(__name__)


def _serialize_span(span: ReadableSpan) -> dict:
    """Convert an OTel ReadableSpan to a JSON-serializable dict.

    All timestamps are converted from nanoseconds (OTel native) to
    milliseconds (JavaScript-safe).
    """
    trace_id = format(span.context.trace_id, "032x")
    span_id = format(span.context.span_id, "016x")
    parent_span_id = (
        format(span.parent.span_id, "016x") if span.parent is not None else None
    )

    start_time_ms = span.start_time / 1_000_000
    end_time_ms = span.end_time / 1_000_000
    duration_ms = end_time_ms - start_time_ms

    attrs = dict(span.attributes) if span.attributes else {}

    events = []
    for event in span.events:
        events.append({
            "name": event.name,
            "timestamp_ms": event.timestamp / 1_000_000,
            "attributes": dict(event.attributes) if event.attributes else {},
        })

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": span.name,
        "kind": span.kind.name,
        "start_time_ms": start_time_ms,
        "end_time_ms": end_time_ms,
        "duration_ms": duration_ms,
        "status": {
            "code": span.status.status_code.name,
            "description": span.status.description,
        },
        "attributes": attrs,
        "events": events,
        "scene_id": attrs.get("sidestage.scene.id"),
        "event_id": attrs.get("sidestage.event.id"),
    }


def _trace_summary(trace_id: str, spans: list[dict]) -> dict:
    """Build a trace summary dict from a list of serialized span dicts."""
    root_span_name = None
    scene_id = None
    event_id = None
    start_time_ms = float("inf")
    end_time_ms = float("-inf")

    for s in spans:
        if s.get("parent_span_id") is None:
            root_span_name = s["name"]
            if scene_id is None:
                scene_id = s.get("scene_id")
            if event_id is None:
                event_id = s.get("event_id")
        t0 = s.get("start_time_ms", float("inf"))
        t1 = s.get("end_time_ms", float("-inf"))
        if t0 < start_time_ms:
            start_time_ms = t0
        if t1 > end_time_ms:
            end_time_ms = t1
        if scene_id is None:
            scene_id = s.get("scene_id")
        if event_id is None:
            event_id = s.get("event_id")

    if root_span_name is None and spans:
        root_span_name = spans[0]["name"]

    return {
        "trace_id": trace_id,
        "scene_id": scene_id,
        "event_id": event_id,
        "start_time_ms": start_time_ms,
        "end_time_ms": end_time_ms,
        "duration_ms": end_time_ms - start_time_ms,
        "span_count": len(spans),
        "root_span_name": root_span_name,
    }


class InMemoryTraceExporter(SpanExporter):
    """In-memory trace storage with ring-buffer eviction and query support."""

    def __init__(
        self,
        max_traces: int = 500,
        on_export_callback: Callable[[list[dict]], None] | None = None,
    ):
        self._max_traces = max_traces
        self._callback = on_export_callback
        self._traces: OrderedDict[str, list[dict]] = OrderedDict()
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            serialized = [_serialize_span(s) for s in spans]

            with self._lock:
                for sd in serialized:
                    tid = sd["trace_id"]
                    if tid in self._traces:
                        self._traces[tid].append(sd)
                        self._traces.move_to_end(tid)
                    else:
                        self._traces[tid] = [sd]

                    # Evict oldest if over limit
                    while len(self._traces) > self._max_traces:
                        self._traces.popitem(last=False)

            # Fire callback outside the lock
            if self._callback is not None:
                try:
                    self._callback(serialized)
                except Exception:
                    logger.exception("Error in trace export callback")

            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("Failed to export spans to in-memory store")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        with self._lock:
            self._traces.clear()

    def get_trace(self, trace_id: str) -> list[dict] | None:
        with self._lock:
            spans = self._traces.get(trace_id)
            return list(spans) if spans is not None else None

    def get_traces(self) -> list[dict]:
        with self._lock:
            summaries = [
                _trace_summary(tid, spans)
                for tid, spans in self._traces.items()
            ]
        summaries.sort(key=lambda s: s["start_time_ms"], reverse=True)
        return summaries

    def get_traces_for_scene(self, scene_id: str) -> list[dict]:
        all_traces = self.get_traces()
        return [t for t in all_traces if t.get("scene_id") == scene_id]

    def load_spans(self, trace_id: str, spans: list[dict]) -> None:
        with self._lock:
            if trace_id in self._traces:
                self._traces[trace_id].extend(spans)
                self._traces.move_to_end(trace_id)
            else:
                self._traces[trace_id] = list(spans)
            while len(self._traces) > self._max_traces:
                self._traces.popitem(last=False)


class SQLiteTraceExporter(SpanExporter):
    """SQLite-based trace persistence using raw sqlite3."""

    def __init__(
        self,
        db_path: Path,
        max_traces_stored: int = 5000,
        max_trace_age_hours: int = 72,
    ):
        self._db_path = db_path
        self._max_traces_stored = max_traces_stored
        self._max_trace_age_hours = max_trace_age_hours
        self._lock = threading.Lock()
        self._closed = False
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()
        # Set pragmas after executescript (which may reset them)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    def _init_tables(self) -> None:
        self._conn.executescript("""
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
        """)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            serialized = [_serialize_span(s) for s in spans]
            with self._lock:
                with self._conn:
                    for sd in serialized:
                        # Upsert trace summary -- use COALESCE to fill in
                        # root_span_name/scene_id/event_id when root span
                        # arrives after child spans.
                        self._conn.execute(
                            """
                            INSERT INTO traces (trace_id, scene_id, event_id, event_type,
                                                start_time_ms, end_time_ms, root_span_name, span_count)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                            ON CONFLICT(trace_id) DO UPDATE SET
                                span_count = span_count + 1,
                                start_time_ms = MIN(start_time_ms, excluded.start_time_ms),
                                end_time_ms = MAX(end_time_ms, excluded.end_time_ms),
                                root_span_name = COALESCE(excluded.root_span_name, traces.root_span_name),
                                scene_id = COALESCE(traces.scene_id, excluded.scene_id),
                                event_id = COALESCE(traces.event_id, excluded.event_id)
                            """,
                            (
                                sd["trace_id"],
                                sd.get("scene_id"),
                                sd.get("event_id"),
                                sd["attributes"].get("sidestage.event.type") if sd["attributes"] else None,
                                sd["start_time_ms"],
                                sd["end_time_ms"],
                                sd["name"] if sd["parent_span_id"] is None else None,
                            ),
                        )

                        # Insert span row
                        self._conn.execute(
                            """
                            INSERT OR REPLACE INTO spans
                                (span_id, trace_id, parent_span_id, name, kind,
                                 start_time_ms, end_time_ms, status_code,
                                 attributes_json, events_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                sd["span_id"],
                                sd["trace_id"],
                                sd["parent_span_id"],
                                sd["name"],
                                sd["kind"],
                                sd["start_time_ms"],
                                sd["end_time_ms"],
                                sd["status"]["code"],
                                json.dumps(sd["attributes"]),
                                json.dumps(sd["events"]),
                            ),
                        )
            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("Failed to export spans to SQLite")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def query_traces(
        self,
        scene_id: str | None = None,
        event_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = []
        params: list = []
        if scene_id is not None:
            conditions.append("scene_id = ?")
            params.append(scene_id)
        if event_id is not None:
            conditions.append("event_id = ?")
            params.append(event_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT trace_id, scene_id, event_id, event_type,
                   start_time_ms, end_time_ms, root_span_name,
                   span_count, created_at
            FROM traces
            {where}
            ORDER BY start_time_ms DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        return [
            {
                "trace_id": r[0],
                "scene_id": r[1],
                "event_id": r[2],
                "event_type": r[3],
                "start_time_ms": r[4],
                "end_time_ms": r[5],
                "root_span_name": r[6],
                "span_count": r[7],
                "created_at": r[8],
            }
            for r in rows
        ]

    def query_spans(self, trace_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT span_id, trace_id, parent_span_id, name, kind,
                       start_time_ms, end_time_ms, status_code,
                       attributes_json, events_json
                FROM spans
                WHERE trace_id = ?
                ORDER BY start_time_ms ASC
                """,
                (trace_id,),
            ).fetchall()

        results = []
        for r in rows:
            attrs = json.loads(r[8]) if r[8] else {}
            start = r[5]
            end = r[6]
            results.append({
                "span_id": r[0],
                "trace_id": r[1],
                "parent_span_id": r[2],
                "name": r[3],
                "kind": r[4],
                "start_time_ms": start,
                "end_time_ms": end,
                "duration_ms": (end - start) if start is not None and end is not None else 0,
                "status_code": r[7],
                "attributes": attrs,
                "events": json.loads(r[9]) if r[9] else [],
                "scene_id": attrs.get("sidestage.scene.id"),
                "event_id": attrs.get("sidestage.event.id"),
            })
        return results

    def run_retention_cleanup(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._max_trace_age_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            with self._conn:
                # Delete old traces
                cursor = self._conn.execute(
                    "DELETE FROM traces WHERE created_at < ?", (cutoff_str,)
                )
                deleted_age = cursor.rowcount

                # Enforce max count
                total = self._conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
                deleted_count = 0
                if total > self._max_traces_stored:
                    excess = total - self._max_traces_stored
                    cursor = self._conn.execute(
                        """
                        DELETE FROM traces WHERE trace_id IN (
                            SELECT trace_id FROM traces
                            ORDER BY start_time_ms ASC
                            LIMIT ?
                        )
                        """,
                        (excess,),
                    )
                    deleted_count = cursor.rowcount

        return deleted_age + deleted_count

    def reload_into_memory(
        self, memory_exporter: InMemoryTraceExporter, limit: int = 500
    ) -> int:
        with self._lock:
            trace_rows = self._conn.execute(
                "SELECT trace_id FROM traces ORDER BY start_time_ms DESC LIMIT ?",
                (limit,),
            ).fetchall()

        loaded = 0
        for (trace_id,) in trace_rows:
            span_dicts = self.query_spans(trace_id)
            if span_dicts:
                memory_exporter.load_spans(trace_id, span_dicts)
                loaded += 1

        return loaded
