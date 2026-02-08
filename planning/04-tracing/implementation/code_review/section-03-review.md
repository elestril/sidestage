# Code Review: Section 03 - Exporters

## Critical Issues

### 1. PRAGMA foreign_keys reset by executescript (Data Integrity Bug)
`PRAGMA foreign_keys = ON` is set before `_init_tables()` which uses `executescript()`. The pragma should be re-set after executescript to ensure it's active.

### 2. InMemoryTraceExporter.export() has no try/except (Crash Risk)
Plan requires both exporters to never propagate exceptions. InMemoryTraceExporter.export() has no error handling.

### 3. Callback exceptions crash the caller (Crash Risk)
The on_export_callback is called without try/except protection.

### 4. SQLiteTraceExporter.shutdown() not idempotent (Crash Risk)
Double-calling shutdown() raises sqlite3.ProgrammingError.

## Medium Issues

### 5. Upsert logic doesn't handle root span arriving after child span
When a child span arrives first, root_span_name is set to None. The upsert ON CONFLICT doesn't update root_span_name when a root span arrives later.

### 6. Retention cleanup overcounts deleted traces
`deleted_count` uses calculated `excess` rather than actual rowcount.

### 7. query_spans returns different dict shape than _serialize_span
Reloaded spans via reload_into_memory lack scene_id, event_id, duration_ms fields, breaking _trace_summary().

## Low Issues

### 8. test_export_handles_errors_gracefully is a no-op test
Bare try/except passes regardless.

### 9. Unused trace_id parameter in _make_spans
Dead code.

### 10. Unused time import in test file

### 11. Documentation update needed (handled in Step 9)
