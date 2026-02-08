# Observability in Sidestage

Sidestage provides transparency into agent behavior, prompt logging, and tool execution primarily through structured file logging.

## Server Logging

Every campaign maintains its own dedicated log file.

- **Location:** `~/.sidestage/<campaign_name>/server.log`
- **Contents:**
    - Agent thought process and turn history.
    - Tool execution logs and return values.
    - WebSocket connection events.
    - API request/response metadata.

## Campaign Health

Runtime health tracking exposes system state and gates operations.

- **States:**
    - `HEALTHY` — Normal operation. Chat, embeddings, and all APIs available.
    - `DEGRADED` — A non-fatal issue occurred (e.g., embedding failure, import/backup in progress). Chat still works; embedding generation paused; import/backup endpoints return `409 Conflict`.
    - `UNHEALTHY` — Critical failure. System cannot serve requests.
- **Transitions:** Health changes are logged and can trigger callbacks for downstream cleanup.

## OpenTelemetry Tracing

The tracing subsystem provides full OpenTelemetry instrumentation with in-browser visualization.

### Configuration
Tracing is configured in `config.yml` under the `tracing:` key. See `TraceConfig` in `config.py` for all options (enabled, capture_prompts, capture_tool_args, capture_memory_content, max_attribute_length, max_traces_in_memory, max_traces_stored, max_trace_age_hours).

### Storage
- **In-Memory:** Ring-buffer (`InMemoryTraceExporter`) for fast lookups, configurable max traces.
- **SQLite:** Persistent storage (`SQLiteTraceExporter`) at `<campaign_dir>/traces.db` with retention cleanup.
- Two-tier lookup: in-memory first, SQLite fallback.

### Instrumentation
Backend modules are instrumented with span creation and attribute recording:
- `scene.py` — scene event processing spans
- `agent.py` — agent run spans with LLM call sub-spans, prompt/completion events
- `character.py` — character event handling spans
- `memory/context.py` — context assembly spans
- `memory/tools.py` — memory tool execution and embedding spans
- `campaign.py` — campaign import/export spans

### API Endpoints
- `GET /v1/traces` — List trace summaries (filterable by scene_id, event_id)
- `GET /v1/traces/{trace_id}` — Get full trace with all spans
- `POST /v1/tracing/toggle` — Enable/disable tracing at runtime
- `GET /v1/tracing/status` — Current tracing status and configuration

### Real-time WebSocket Broadcasts
When tracing is enabled, trace events are broadcast over the existing WebSocket:
- `trace_started` — New trace begun (includes scene_id, event_type)
- `span_completed` — Individual span finished (includes full span data)
- `trace_completed` — Trace finished (includes final duration)

### Frontend Trace Viewer
The Trace Viewer page (`/traces`) provides a waterfall visualization of traces with:
- Scene-based filtering
- Collapsible span tree with color-coded duration bars
- Span detail panel with attributes, prompt/completion events, and error details
- Real-time updates via WebSocket (live waterfall building, running trace indicators)

### Chat Debug Mode
A debug toggle in the Chat Widget header enables trace link icons on chat messages. Clicking an icon resolves the message's trace via the `event_id` lookup API and navigates to the Trace Viewer.

## Why this matters
Observability allows Game Masters to:
- Inspect the exact prompts being sent to the LLM.
- Debug why an agent made a specific decision.
- Verify that tools are being called with the correct parameters.
- Audit performance (latency) of agent runs.
- Monitor campaign health and diagnose embedding or database issues.
