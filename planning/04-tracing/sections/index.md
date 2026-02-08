<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-tracing-config
section-02-tracing-core
section-03-exporters
section-04-backend-instrumentation
section-05-api-endpoints
section-06-frontend-trace-viewer
section-07-frontend-realtime-debug
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-tracing-config | - | 02, 03, 04, 05 | Yes |
| section-02-tracing-core | 01 | 03, 04 | No |
| section-03-exporters | 02 | 04, 05 | No |
| section-04-backend-instrumentation | 03 | 05, 06, 07 | No |
| section-05-api-endpoints | 04 | 06, 07 | No |
| section-06-frontend-trace-viewer | 05 | 07 | No |
| section-07-frontend-realtime-debug | 06 | - | No |

## Execution Order

1. section-01-tracing-config (no dependencies)
2. section-02-tracing-core (after 01)
3. section-03-exporters (after 02)
4. section-04-backend-instrumentation (after 03)
5. section-05-api-endpoints (after 04)
6. section-06-frontend-trace-viewer (after 05)
7. section-07-frontend-realtime-debug (after 06)

## Section Summaries

### section-01-tracing-config
TraceConfig Pydantic model, config.yml integration, tracing section in SidestageConfig. Tests for config parsing and defaults.

### section-02-tracing-core
TracerProvider setup, FilteringSpanProcessor, init_tracing/toggle_tracing/shutdown_tracing, convenience helpers (trace_span, current_trace_id, add_trace_event, record_error). Tests for provider lifecycle and helpers.

### section-03-exporters
InMemoryTraceExporter (ring buffer, span serialization, callbacks) and SQLiteTraceExporter (raw sqlite3, table creation, retention cleanup, reload). Tests for both exporters.

### section-04-backend-instrumentation
Manual span instrumentation at all key points: _process_event, _dispatch_to_npcs, on_event, assemble_context, arun, memory tools, _fire_embed context propagation, reload_defaults. Tests for span hierarchy and attributes.

### section-05-api-endpoints
REST endpoints (GET /v1/traces, GET /v1/traces/{id}, POST /v1/tracing/toggle, GET /v1/tracing/status) and WebSocket trace messages (trace_started, span_completed, trace_completed). Tests for API responses and WebSocket messages.

### section-06-frontend-trace-viewer
TraceViewerPage with route, SceneSelector, TraceList, TraceTimeline (waterfall), SpanDetail panel with PromptViewer. TypeScript types. Trace data fetching from API.

### section-07-frontend-realtime-debug
WebSocket integration for real-time trace updates in the trace viewer. Chat debug mode toggle with trace link icons on chat bubbles (event_id-based trace lookup).
