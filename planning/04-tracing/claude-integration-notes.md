# Integration Notes: Opus Review Feedback

## Changes Accepted

### Critical Fixes
1. **Storage layer** - Switch from SQLAlchemy to raw `sqlite3` to match existing `Storage` pattern. SQLiteTraceExporter receives `db_path: Path` and manages its own connection.
2. **Toggle mechanism** - Replace provider-swap approach with a custom `FilteringSpanProcessor` that checks an `enabled` flag. Always register a real TracerProvider; control behavior at the processor level.
3. **Dual-trace for NPC replies** - Document as intentional behavior. User message trace contains the full agent execution (heavy trace). NPC reply trace is just persist+broadcast (lightweight). Add `origin_trace_id` as a span attribute on NPC reply traces for correlation.

### Significant Fixes
4. **Root span placement** - Move span creation after the `isinstance(event, ChatMessage)` check.
5. **Token usage** - Add explicit extraction of `resp_obj.usage` with None-safety guard.
6. **SQLite blocking** - Use `BatchSpanProcessor` for the SQLite exporter. Keep `SimpleSpanProcessor` for the in-memory exporter (pure memory ops, no blocking concern).

### Moderate Fixes
7. **WebSocket filtering** - Accept broadcast-to-all. Frontend filters client-side by scene_id. Simpler and appropriate for single-user tool.
8. **trace_id on ChatMessage** - Do NOT add to persisted model. Instead, include trace_id only in the WebSocket broadcast payload (add to the dict sent by SyncManager, not to the Pydantic model).
9. **trace_started message** - Add to plan. Sent when root span starts.
10. **DmMemoryTools** - Instrument `_fire_embed` identically to MemoryTools.
11. **Trace retention** - Add `max_trace_age_hours: int = 72` to TraceConfig. On startup, delete traces older than this. Also add `max_traces_stored: int = 5000`.
12. **Timestamps** - Convert to milliseconds in API responses. Frontend uses millisecond precision throughout.

### Missing Items Added
13. **Error status** - Add `span.set_status(StatusCode.ERROR)` and `span.record_exception()` in all instrumented try/except blocks.
14. **Provider shutdown** - Call `provider.shutdown()` in the `_lifespan` context manager during teardown.
15. **scene_id optional** - Make `scene_id` an optional query param on `GET /v1/traces`. When omitted, return most recent traces across all scenes.
16. **Async decorator** - Explicitly design `trace_span` for async functions.
17. **Frontend route testing** - Note that SPA catch-all + StaticFiles interaction needs testing.

## Changes Not Accepted
- None. All review findings were valid and incorporated.
