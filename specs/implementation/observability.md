# observability

Implements: [debugging](/specs/debugging.md)

## Overview {#overview}

The system provides transparency into agent behavior, prompt logging, and tool
execution through structured file logging, request context propagation, and
OpenTelemetry tracing.

## Request Context {#request-context}

Every HTTP request, WebSocket message, and MCP call MUST be tagged with an
ambient `RequestContext` that propagates automatically through the entire async
call stack via Python's `contextvars`.

### Context Fields {#context-fields}

The request context MUST carry:

<a id="ctx-request-id"></a>
- **`request_id`** — Unique per-request identifier (from `X-Request-ID`
  header, or auto-generated).

<a id="ctx-user"></a>
- **`user`** — Who made the request (from `X-Actor` header, defaults to
  `"anonymous"`).

<a id="ctx-origin"></a>
- **`origin`** — Entry point: `"http"`, `"ws"`, `"mcp"`, or `"internal"`.

<a id="ctx-annotations"></a>
- **`annotations`** — Free-form debug tags from `X-Debug-*` headers (e.g.,
  `X-Debug-Tag: test-memory-recall`).

### Context Sources {#context-sources}

<a id="ctx-http"></a>
- **HTTP** — `RequestContextMiddleware` (Starlette middleware on the FastAPI
  app) MUST extract headers and set context before route handlers run.

<a id="ctx-ws"></a>
- **WebSocket** — Context MUST be set in `orchestrator._handle_ws_message()`
  before dispatching.

<a id="ctx-internal"></a>
- **Internal/background** — `get_or_create_context()` MUST lazily create a
  context with `origin="internal"`.

### Integration with Logging {#ctx-logging}

<a id="ctx-log-filter"></a>
A `RequestContextFilter` MUST be installed on the root log handlers. Every log
line MUST automatically include `request_id` and `user` fields:

```
2025-01-15 10:00:00 [a1b2c3d4] alice - sidestage.scene - INFO - Scene activated
```

### Integration with Tracing {#ctx-tracing}

<a id="ctx-span-stamp"></a>
`stamp_span_with_request_context()` MUST copy the context fields onto OTel
span attributes (`sidestage.request_id`, `sidestage.user`,
`sidestage.origin`, `sidestage.annotation.*`). This MUST be called
automatically by the `@trace_span` decorator.

### Response Correlation {#ctx-response}

<a id="ctx-echo-header"></a>
The `X-Request-ID` header MUST be echoed back on HTTP responses for
client-side correlation.

## Logging {#logging}

All log files are volatile debugging output. Campaign state MUST live in the
graph database.

`SIDESTAGE_DIR` defaults to `~/.sidestage/`.

### Global Logs {#global-logs}

Global logs MUST reside in `SIDESTAGE_DIR`:

| File           | Logger(s)                        | Contents                                            |
|----------------|----------------------------------|-----------------------------------------------------|
| `server.log`   | root, `sidestage.*`, `uvicorn`   | System messages, module logs, uvicorn startup/errors |
| `request.log`  | `uvicorn.access`                 | HTTP access logs with request context                |

### Per-Campaign Logs {#campaign-logs}

Per-campaign logs MUST reside in `SIDESTAGE_DIR/<campaign>`:

| File            | Logger                            | Contents                                 |
|-----------------|-----------------------------------|------------------------------------------|
| `campaign.log`  | `sidestage.campaign.<name>`       | Campaign operational messages             |
| `chat.log`      | `sidestage.chat.<name>`           | Chat event debug trace                   |

### Configuration {#log-config}

Logging MUST be configured in `config.yml` under the `logging:` key:

```yaml
logging:
  level: INFO
```

The `level` field MUST accept: `DEBUG`, `INFO`, `WARNING`, `ERROR`,
`CRITICAL`.

### Rich Console Output {#rich-console}

<a id="rich-theme"></a>
Stdout logs MUST use Rich with the `SIDESTAGE_THEME` for colored output.

## OpenTelemetry Tracing {#tracing}

### Configuration {#tracing-config}

Tracing MUST be configured in `config.yml` under the `tracing:` key:

<a id="tracing-enabled"></a>
- `enabled` — Master switch (default: `false`).

<a id="tracing-otlp-endpoint"></a>
- `otlp_endpoint` — OTLP HTTP endpoint (default: `http://localhost:4318`).

<a id="tracing-capture-prompts"></a>
- `capture_prompts` — Include `gen_ai.prompt`/`completion` events (default:
  `true`).

<a id="tracing-capture-tool-args"></a>
- `capture_tool_args` — Include `tool.*` events (default: `true`).

<a id="tracing-capture-memory"></a>
- `capture_memory_content` — Include `memory.*` events (default: `true`).

<a id="tracing-max-attr-length"></a>
- `max_attribute_length` — Truncate long string attributes (default: `4096`).

### Endpoint Validation {#tracing-validation}

<a id="tracing-tcp-check"></a>
On startup and when toggling tracing on at runtime, the system MUST validate
that the OTLP endpoint is reachable via a TCP connect check. If the endpoint
is unreachable, tracing MUST be automatically disabled and the error MUST be
surfaced in the `/v1/tracing/status` response and as a warning banner in the
frontend UI.

### Export {#tracing-export}

<a id="tracing-batch-processor"></a>
Traces MUST be exported via OTLP HTTP to the configured endpoint using
`BatchSpanProcessor` and `OTLPSpanExporter`.

### Instrumentation {#tracing-instrumentation}

The following modules MUST be instrumented with span creation and attribute
recording:

- `scene.py` — Scene event processing spans.
- `agent.py` — Agent run spans with LLM call sub-spans, prompt/completion
  events.
- `character.py` — Character event handling spans.
- `memory/context.py` — Context assembly spans.
- `memory/tools.py` — Memory tool execution and embedding spans.
- `campaign.py` — Campaign import/export spans.

## Campaign Health {#campaign-health}

See [campaign#health](/specs/implementation/campaign.md#health) for the full health state
specification. Health state changes MUST be observable via logging and MAY
trigger callbacks.
