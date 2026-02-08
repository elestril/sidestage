# Code Review Interview: Section 03 - Exporters

**Date:** 2026-02-07

## Auto-Fixes (applying without discussion)

### Fix 1: Re-set PRAGMA foreign_keys after executescript
The executescript() call in _init_tables() may reset pragma state. Re-set pragmas after table creation.

### Fix 2: Add try/except to InMemoryTraceExporter.export()
Plan requires both exporters never propagate exceptions.

### Fix 3: Wrap callback invocation in try/except
Prevents WebSocket broadcast errors from crashing the caller.

### Fix 4: Make SQLiteTraceExporter.shutdown() idempotent
Guard against double-close.

### Fix 5: Fix upsert to update root_span_name/scene_id when root span arrives later
Use COALESCE in the ON CONFLICT clause to update NULL values.

### Fix 6: Use actual rowcount in retention cleanup
Return accurate deletion count.

### Fix 7: Fix query_spans to return compatible dict shape
Include scene_id, event_id, duration_ms in returned dicts so reload_into_memory produces spans compatible with _trace_summary().

### Fix 8: Fix test_export_handles_errors_gracefully
Actually assert the exporter handles errors without raising.

### Fix 9: Remove unused trace_id parameter from _make_spans

### Fix 10: Remove unused time import

## Let Go

- Lock reentrance concern in reload_into_memory - works fine as designed
- No span events serialization test - low priority
- Documentation update - handled in Step 9
