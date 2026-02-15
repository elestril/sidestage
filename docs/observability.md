# Observability in Sidestage

Sidestage provides transparency into agent behavior, prompt logging, and tool execution primarily through structured file logging.

## Request Context

Every HTTP request, WebSocket message, and MCP call is tagged with an ambient `RequestContext` that propagates automatically through the entire async call stack via Python's `contextvars`.

### What it carries
- **`request_id`** — unique per-request identifier (from `X-Request-ID` header, or auto-generated).
- **`user`** — who made the request (from `X-Actor` header, defaults to `"anonymous"`).
- **`origin`** — entry point: `"http"`, `"ws"`, `"mcp"`, or `"internal"`.
- **`annotations`** — free-form debug tags from `X-Debug-*` headers (e.g. `X-Debug-Tag: test-memory-recall`).

### How it's set
- **HTTP** — `RequestContextMiddleware` (Starlette middleware on the FastAPI app) extracts headers and sets context before route handlers run.
- **WebSocket** — Context is set in `orchestrator._handle_ws_message()` before dispatching.
- **Internal/background** — `get_or_create_context()` lazily creates a context with `origin="internal"`.

### Integration with logging
A `RequestContextFilter` is installed on the root log handlers. Every log line automatically includes `request_id` and `user` fields:
```
2025-01-15 10:00:00 [a1b2c3d4] alice - sidestage.scene - INFO - Scene activated
```

### Integration with tracing
`stamp_span_with_request_context()` copies the context fields onto OTel span attributes (`sidestage.request_id`, `sidestage.user`, `sidestage.origin`, `sidestage.annotation.*`). This is called automatically by the `@trace_span` decorator.

### Reading it in code
```python
from sidestage.request_context import get_request_context

ctx = get_request_context()
if ctx:
    log.info("processing for user=%s", ctx.user)
```

### Response correlation
The `X-Request-ID` header is echoed back on HTTP responses for client-side correlation.

## Server Logging

Every campaign maintains its own dedicated log file.

- **Location:** `~/.sidestage/<campaign_name>/server.log`
- **Format:** `%(asctime)s [%(request_id)s] %(user)s - %(name)s - %(levelname)s - %(message)s`
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

The tracing subsystem provides full OpenTelemetry instrumentation with OTLP export to an external viewer (e.g. [otel-desktop-viewer](https://github.com/CtrlSpice/otel-desktop-viewer)).

### Configuration
Tracing is configured in `config.yml` under the `tracing:` key. See `TraceConfig` in `config.py` for all options:
- `enabled` — master switch (default: false)
- `otlp_endpoint` — OTLP HTTP endpoint (default: `http://localhost:4318`)
- `capture_prompts` — include gen_ai.prompt/completion events (default: true)
- `capture_tool_args` — include tool.* events (default: true)
- `capture_memory_content` — include memory.* events (default: true)
- `max_attribute_length` — truncate long string attributes (default: 4096)

### Endpoint Validation
On startup (and when toggling tracing on at runtime), Sidestage validates that the OTLP endpoint is reachable via a TCP connect check. If the endpoint is unreachable, tracing is automatically disabled and the error is surfaced in the `/v1/tracing/status` response and as a warning banner in the frontend UI.

### Export
Traces are exported via OTLP HTTP to the configured endpoint using `BatchSpanProcessor` and `OTLPSpanExporter`. Run `otel-desktop-viewer` (or any OTLP-compatible collector) to receive and view traces.

### Instrumentation
Backend modules are instrumented with span creation and attribute recording:
- `scene.py` — scene event processing spans
- `agent.py` — agent run spans with LLM call sub-spans, prompt/completion events
- `character.py` — character event handling spans
- `memory/context.py` — context assembly spans
- `memory/tools.py` — memory tool execution and embedding spans
- `campaign.py` — campaign import/export spans

### API Endpoints
- `POST /v1/tracing/toggle` — Enable/disable tracing at runtime
- `GET /v1/tracing/status` — Current tracing status and configuration

## Why this matters
Observability allows Game Masters to:
- Inspect the exact prompts being sent to the LLM.
- Debug why an agent made a specific decision.
- Verify that tools are being called with the correct parameters.
- Audit performance (latency) of agent runs.
- Monitor campaign health and diagnose embedding or database issues.
