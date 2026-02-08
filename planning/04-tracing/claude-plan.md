# Implementation Plan: Tracing Support for Sidestage

## 1. Project Context

Sidestage is an AI-powered tabletop RPG co-author tool with a Python/FastAPI backend and React/TypeScript frontend. Users interact with NPC characters in "scenes" via chat. Each user message flows through an EventQueue, gets persisted, broadcast to WebSocket clients, and dispatched to NPC AgentActors. Each NPC assembles memory context, calls an LLM (via LiteLLM), potentially executes tools (memory writes, world updates), and posts a reply back to the queue.

This plan adds OpenTelemetry-based tracing to capture the full lifecycle of every event: LLM calls with prompts, tool executions, memory operations, and embedding generation. A custom trace viewer in the React frontend provides real-time visibility into these traces.

## 2. Architecture Overview

### 2.1 Backend Tracing Layer

The tracing system consists of four components:

1. **Tracing module** (`src/sidestage/tracing/`) - OTel initialization, configuration, custom exporters
2. **Instrumentation** - Manual span creation at 8 key points in the existing code
3. **Storage** - SQLite tables for trace/span persistence + in-memory ring buffer for live serving
4. **API endpoints** - REST endpoints for trace data + WebSocket messages for real-time updates

### 2.2 Frontend Trace Viewer

A custom React component at `/sidestage/traces` displays traces as a waterfall/timeline. Chat bubbles gain a debug mode with trace link icons.

### 2.3 Data Flow

```
ChatMessage event arrives at Scene EventQueue
  -> _process_event creates root span (trace_id generated)
  -> Nested spans for each operation (persist, broadcast, dispatch)
    -> Per-NPC spans (context assembly, LLM call, tool execution)
      -> Span events capture prompts/completions
  -> Spans exported via two processors:
     -> SimpleSpanProcessor -> InMemoryExporter (fires WebSocket broadcast)
     -> BatchSpanProcessor -> SQLiteExporter (persists to disk)
  -> API serves trace data to frontend
```

### 2.4 Trace Boundaries

Each event arriving at the EventQueue creates **one independent trace**. When an NPC generates a reply and puts it back on the queue, that reply event creates a second, separate trace. The user message trace is the "heavy" trace containing the full agent execution (LLM calls, tool calls, memory operations). The NPC reply trace is lightweight (just persist + broadcast). The NPC reply trace carries an `origin_trace_id` attribute linking it back to the user message trace for optional correlation.

## 3. Tracing Module

### 3.1 New Package Structure

```
src/sidestage/tracing/
  __init__.py        # Public API: init_tracing(), get_tracer(), toggle_tracing()
  config.py          # TraceConfig model
  provider.py        # TracerProvider setup, exporter registration, FilteringSpanProcessor
  exporters.py       # InMemoryTraceExporter, SQLiteTraceExporter
  middleware.py       # Convenience decorators/context managers for instrumentation
```

### 3.2 TraceConfig Model

Add a `tracing` section to `SidestageConfig` in `src/sidestage/config.py`:

```python
class TraceConfig(BaseModel):
    enabled: bool = False
    capture_prompts: bool = True
    capture_tool_args: bool = True
    capture_memory_content: bool = True
    max_attribute_length: int = 4096
    max_traces_in_memory: int = 500
    max_traces_stored: int = 5000
    max_trace_age_hours: int = 72
```

This becomes `SidestageConfig.tracing: TraceConfig`.

The config.yml gains:
```yaml
tracing:
  enabled: false
  capture_prompts: true
  capture_tool_args: true
```

### 3.3 TracerProvider Initialization

`tracing/provider.py` handles OTel setup.

**Always** create a real `TracerProvider` with a `Resource` identifying the service (`service.name: "sidestage"`, `campaign.name: <name>`). Register two span processors wrapping the exporters:

1. **`FilteringSpanProcessor(SimpleSpanProcessor(InMemoryTraceExporter(...)))`** - For in-memory storage and WebSocket broadcast. SimpleSpanProcessor is fine here (pure memory operations, no I/O blocking).
2. **`FilteringSpanProcessor(BatchSpanProcessor(SQLiteTraceExporter(...)))`** - For SQLite persistence. BatchSpanProcessor runs exports in a background thread, avoiding blocking the async event loop with synchronous SQLite I/O.

The **`FilteringSpanProcessor`** is a custom `SpanProcessor` wrapper that checks an `enabled` flag:
- When `enabled == True`: delegates to the wrapped processor normally
- When `enabled == False`: `on_start()` and `on_end()` are no-ops, discarding span data

This avoids the problem of swapping the global TracerProvider at runtime. `trace.set_tracer_provider()` is called once at startup. Toggling tracing on/off simply flips the `enabled` flag on the FilteringSpanProcessor instances. Tracers obtained via `trace.get_tracer()` remain valid regardless.

`init_tracing(config, campaign_name, db_path)` is called during campaign startup. It:
1. Creates the TracerProvider and registers it globally
2. Sets the initial `enabled` state from config
3. Loads recent traces from SQLite into the in-memory exporter
4. Runs trace retention cleanup (deletes traces older than `max_trace_age_hours`)

`toggle_tracing(enabled)` flips the FilteringSpanProcessor's `enabled` flag. Called by the API toggle endpoint.

**Provider shutdown:** `shutdown_tracing()` calls `provider.shutdown()` to flush pending BatchSpanProcessor spans. Called from the `_lifespan` context manager during application teardown.

### 3.4 Getting Tracers

Each module that needs tracing calls:
```python
tracer = trace.get_tracer("sidestage.<module_name>")
```

This can be done at module level. The tracer always creates real spans, but the FilteringSpanProcessor discards them when disabled. The overhead of creating spans that are immediately discarded is minimal (a few object allocations) and acceptable for this application.

### 3.5 InMemoryTraceExporter

A custom `SpanExporter` that maintains a bounded dict of recent traces:

- Keyed by `trace_id` (hex string)
- Each entry: list of serialized span dicts
- Ring-buffer semantics: evicts oldest trace when `max_traces_in_memory` exceeded
- Thread-safe via `threading.Lock`
- Provides `get_traces()`, `get_trace(trace_id)`, `get_traces_for_scene(scene_id)` query methods
- On each span export, fires a callback to the WebSocket broadcast system for real-time updates

The span serialization format (all timestamps in **milliseconds** for JavaScript compatibility):
```python
{
    "trace_id": str,
    "span_id": str,
    "parent_span_id": str | None,
    "name": str,
    "kind": str,
    "start_time_ms": float,    # milliseconds since epoch
    "end_time_ms": float,      # milliseconds since epoch
    "duration_ms": float,
    "status": {"code": str, "description": str | None},
    "attributes": dict,
    "events": [{"name": str, "timestamp_ms": float, "attributes": dict}],
    "scene_id": str | None,    # extracted from attributes for indexing
    "event_id": str | None,    # extracted from attributes for indexing
}
```

Nanosecond timestamps from OTel are converted to milliseconds during serialization. This avoids JavaScript `Number.MAX_SAFE_INTEGER` precision issues.

### 3.6 SQLiteTraceExporter

A custom `SpanExporter` that persists spans to SQLite using raw `sqlite3` (consistent with the existing `Storage` class pattern -- no SQLAlchemy).

The exporter receives a `db_path: Path` at init and manages its own `sqlite3` connection.

Two tables:
- **`traces`**: `trace_id TEXT PK, scene_id TEXT, event_id TEXT, event_type TEXT, start_time_ms REAL, end_time_ms REAL, root_span_name TEXT, span_count INTEGER, created_at TEXT`
- **`spans`**: `span_id TEXT PK, trace_id TEXT FK, parent_span_id TEXT, name TEXT, kind TEXT, start_time_ms REAL, end_time_ms REAL, status_code TEXT, attributes_json TEXT, events_json TEXT`

Indexes: `traces.scene_id`, `traces.event_id`, `traces.created_at`, `spans.trace_id`.

The exporter's `export()` method receives a batch of spans (from `BatchSpanProcessor`), serializes them, and writes them in a single transaction. It also upserts the `traces` summary row (incrementing `span_count`, updating `end_time_ms`).

**Retention cleanup:** On startup and periodically (e.g., every hour), delete traces older than `max_trace_age_hours` and enforce `max_traces_stored` by deleting the oldest traces.

On server startup, `init_tracing()` queries recent traces from SQLite and loads them into the in-memory exporter for immediate availability in the trace viewer.

### 3.7 Convenience Instrumentation Helpers

`tracing/middleware.py` provides:

```python
def trace_span(name: str, attributes: dict | None = None):
    """Decorator that wraps an async function in a span.

    Designed specifically for async functions. Uses functools.wraps
    and creates an async wrapper that properly propagates span context.
    """

def current_trace_id() -> str | None:
    """Get the current trace_id as a hex string, or None if no active span."""

def add_trace_event(name: str, attributes: dict | None = None):
    """Add an event to the current span, respecting TraceConfig settings.

    Checks capture_prompts/capture_tool_args/capture_memory_content flags.
    Truncates string values exceeding max_attribute_length with '[truncated]' suffix.
    """

def record_error(span, exception: Exception):
    """Set span status to ERROR and record the exception.

    Calls span.set_status(StatusCode.ERROR, str(exception)) and
    span.record_exception(exception).
    """
```

The `add_trace_event` helper accesses the `TraceConfig` singleton to check flags and truncate long strings.

## 4. Instrumentation Points

### 4.1 SceneLogic._process_event (Root Span)

**File:** `src/sidestage/scene.py`
**Method:** `_process_event(self, event)`

The existing method starts with `if not isinstance(event, ChatMessage): return`. The root span must be created **after** this check to avoid creating empty traces for non-ChatMessage events.

```python
async def _process_event(self, event):
    if not isinstance(event, ChatMessage):
        return
    with tracer.start_as_current_span("scene.process_event") as span:
        span.set_attribute("sidestage.scene.id", self.id)
        span.set_attribute("sidestage.event.id", event.id)
        span.set_attribute("sidestage.event.type", type(event).__name__)
        span.set_attribute("sidestage.actor.id", event.actor_id)
        try:
            # ... existing logic (persist, broadcast, dispatch)
        except Exception as exc:
            record_error(span, exc)
            raise
```

Capture the `trace_id` from the current span context using `current_trace_id()` and include it in the WebSocket broadcast payload (see Section 4.8).

### 4.2 SceneLogic._dispatch_to_npcs

**File:** `src/sidestage/scene.py`

Wrap the NPC dispatch loop in a span:

```python
async def _dispatch_to_npcs(self, event):
    with tracer.start_as_current_span("scene.dispatch_to_npcs") as span:
        span.set_attribute("sidestage.npc_count", len(self.characters))
        # Per-NPC dispatch happens in on_event which creates its own child span
```

### 4.3 AgentActor.on_event

**File:** `src/sidestage/character.py`
**Method:** `on_event(self, event)`

```python
async def on_event(self, event):
    with tracer.start_as_current_span("agent.on_event") as span:
        span.set_attribute("sidestage.character.id", self.data.id)
        span.set_attribute("sidestage.character.name", self.data.name)
        try:
            # ... existing logic (assemble context, run agent, post reply)
        except Exception as exc:
            record_error(span, exc)
            logger.exception(...)  # existing error handling
```

### 4.4 assemble_context

**File:** `src/sidestage/memory/context.py`

```python
async def assemble_context(...):
    with tracer.start_as_current_span("memory.assemble_context") as span:
        span.set_attribute("sidestage.owner_id", owner_id)
        span.set_attribute("sidestage.scene.id", scene_id)
        # ... existing logic
        span.set_attribute("memory.token_estimate", result.token_estimate)
        return result
```

### 4.5 LiteLLMAgent.arun

**File:** `src/sidestage/agent.py`

Wrap the entire agent run and each individual LLM call. The existing code does not extract `resp_obj.usage` -- this must be added with None-safety since some local LLM servers do not return usage statistics.

```python
async def arun(self, message, context):
    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("agent.name", self.name)
        span.set_attribute("gen_ai.request.model", self.model)

        turn = 0
        total_input_tokens = 0
        total_output_tokens = 0

        while turn < self.max_turns:
            turn += 1
            with tracer.start_as_current_span("llm.completion") as llm_span:
                llm_span.set_attribute("agent.turn", turn)
                # Add prompt events (if capture_prompts enabled)
                add_trace_event("gen_ai.prompt", {"role": "system", "content": system_msg})
                add_trace_event("gen_ai.prompt", {"role": "user", "content": user_msg})

                try:
                    response = await litellm.acompletion(...)
                except Exception as exc:
                    record_error(llm_span, exc)
                    raise

                # Add completion event
                add_trace_event("gen_ai.completion", {"content": response_text})

                # Extract token usage (may be None for some providers)
                usage = getattr(response, 'usage', None)
                if usage:
                    input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
                    output_tokens = getattr(usage, 'completion_tokens', 0) or 0
                    llm_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                    llm_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens

                llm_span.set_attribute("gen_ai.response.finish_reasons",
                    [choice.finish_reason for choice in response.choices])

                if tool_calls:
                    for tool_call in tool_calls:
                        with tracer.start_as_current_span("tool.execute") as tool_span:
                            tool_span.set_attribute("tool.name", tool_call.function.name)
                            if capture_tool_args:
                                add_trace_event("tool.arguments",
                                    {"args": tool_call.function.arguments})
                            try:
                                result = await execute_tool(...)
                                add_trace_event("tool.result", {"result": str(result)})
                            except Exception as exc:
                                record_error(tool_span, exc)

        span.set_attribute("agent.turn_count", turn)
        span.set_attribute("agent.total_input_tokens", total_input_tokens)
        span.set_attribute("agent.total_output_tokens", total_output_tokens)
```

### 4.6 Memory Tool Operations

**File:** `src/sidestage/memory/tools.py`

Instrument both `MemoryTools` and `DmMemoryTools` classes. Each memory tool method gets a span:
```python
async def update_scene_memory(self, content, gametime=None):
    with tracer.start_as_current_span("memory.update_scene_memory") as span:
        span.set_attribute("sidestage.owner_id", self.owner_id)
        span.set_attribute("sidestage.scene.id", self.scene_id)
        if capture_memory_content:
            add_trace_event("memory.content", {"content": content})
        try:
            # ... existing logic
        except Exception as exc:
            record_error(span, exc)
            # ... existing error handling
```

Similarly for `update_character_memory`, `update_common_memory`, `update_canonical_memory`, `add_world_fact`.

### 4.7 Background Embedding

**File:** `src/sidestage/memory/tools.py` and `src/sidestage/memory/embeddings.py`

Both `MemoryTools._fire_embed` and `DmMemoryTools._fire_embed` must propagate the current trace context to the background task:

```python
def _fire_embed(self, memory_id, content):
    if self.embed_config is not None:
        ctx = context.get_current()  # Capture current OTel context
        async def _embed_with_context():
            token = context.attach(ctx)  # Restore in background task
            try:
                with tracer.start_as_current_span("memory.embed") as span:
                    span.set_attribute("memory.id", memory_id)
                    await embed_and_update(...)
            except Exception as exc:
                # Log but don't propagate - background task
                logger.debug("Background embed tracing error: %s", exc)
            finally:
                context.detach(token)
        try:
            asyncio.create_task(_embed_with_context())
        except RuntimeError:
            logger.debug("No event loop for background embed task")
```

### 4.8 Trace Lookup via Event ID

Do **NOT** add `trace_id` to the `ChatMessage` model or the WebSocket broadcast payload. The `traces` table already stores `event_id` for each trace (set from the ChatMessage's `id` field in the root span attributes). This allows the frontend to look up the trace for any message by querying `GET /v1/traces?event_id=<message_id>`.

In `_process_event`, after the root span is created:
1. Set `span.set_attribute("sidestage.event.id", event.id)` (already done in 4.1)
2. The SQLiteTraceExporter extracts `event_id` from span attributes and stores it in the `traces` table
3. The frontend can resolve any message's trace via the existing event_id

This avoids polluting the data model or broadcast payload with trace metadata.

### 4.9 Entity Import Tracing

**File:** `src/sidestage/campaign.py`
**Method:** `reload_defaults(self)`

Entity imports from markdown (`data/campaign_defaults/markdown/`) should be traced and attributed to the `campaign_planning` scene:

```python
def reload_defaults(self):
    with tracer.start_as_current_span("campaign.reload_defaults") as span:
        span.set_attribute("sidestage.scene.id", "campaign_planning")
        # ... existing logic
        span.set_attribute("entities.loaded_count", count)
```

**TODO:** Imports will later be migrated to an assistant actor, at which point the hard-coded `campaign_planning` scene attribution becomes moot and should be replaced with the actor's scene context.

## 5. API Endpoints

### 5.1 New Routes

Add to `src/sidestage/orchestrator.py`:

**`GET /v1/traces`**
- Query params: `scene_id` (optional), `event_id` (optional), `limit` (default 50), `offset` (default 0)
- Returns: list of trace summaries `[{trace_id, scene_id, event_id, event_type, start_time, duration_ms, span_count, root_span_name}]`
- When `scene_id` is provided: filter by scene. When `event_id` is provided: return the trace for that specific event. When both omitted: return most recent traces across all scenes.
- Source: SQLite `traces` table (indexed on both `scene_id` and `event_id`)

**`GET /v1/traces/{trace_id}`**
- Returns: full trace with all spans `{trace_id, spans: [{span_id, parent_span_id, name, ...}]}`
- Source: in-memory exporter first, fall back to SQLite

**`POST /v1/tracing/toggle`**
- Body: `{"enabled": bool}`
- Calls `toggle_tracing(enabled)` to flip the FilteringSpanProcessor flag
- Returns: `{"tracing_enabled": bool}`

**`GET /v1/tracing/status`**
- Returns: `{"enabled": bool, "config": {capture_prompts, ...}, "trace_count": int}`

### 5.2 WebSocket Trace Messages

Broadcast trace events to all connected WebSocket clients via SyncManager. The frontend filters client-side by scene_id (no subscription mechanism needed -- this is a single-user tool).

Three message types:

- **`trace_started`**: Sent when a root span starts. Payload: `{trace_id, scene_id, event_type, start_time_ms}`. The InMemoryTraceExporter triggers this via a callback when it receives a span with no parent.
- **`span_completed`**: Sent when any span finishes. Payload: serialized span dict. Triggered by the InMemoryTraceExporter callback on each export.
- **`trace_completed`**: Sent when a root span finishes (indicating the entire trace is done). Payload: `{trace_id, scene_id, duration_ms}`.

## 6. Frontend: Trace Viewer Page

### 6.1 New Route

Add `/sidestage/traces` and `/sidestage/traces/:sceneId/:traceId` to the React Router config in `App.tsx`.

Note: The SPA catch-all route (`/sidestage/{full_path:path}`) in the backend serves `index.html` for non-file paths. The StaticFiles mount with `html=True` may interact with these routes -- test that direct navigation to `/sidestage/traces` works correctly and add appropriate fallback handling if needed.

### 6.2 Component Structure

```
TraceViewerPage
  |-- SceneSelector          (dropdown to pick a scene)
  |-- TraceList              (scrollable list of traces for selected scene)
  |     |-- TraceListItem    (summary row: event type, duration, timestamp)
  |-- TraceDetail            (main panel, shown when a trace is selected)
        |-- TraceTimeline    (waterfall view)
        |     |-- SpanRow    (one per span: name + duration bar)
        |-- SpanDetail       (side panel, shown when a span is clicked)
              |-- AttributeTable
              |-- EventList
              |     |-- PromptViewer  (collapsible, full content)
```

### 6.3 TraceTimeline (Waterfall View)

The core visualization component:

1. **Build span tree** from flat span list (parent_span_id -> children mapping)
2. **Flatten to ordered list** with depth (DFS traversal of tree)
3. **Render each span as a row** with two columns:
   - Left (fixed width ~300px): Span name, indented by depth (16px per level), with expand/collapse toggle for spans with children
   - Right (flexible): Duration bar positioned proportionally to trace start/end time

Duration bars are color-coded:
- LLM calls (`llm.completion`, `agent.run`): blue/purple
- Tool execution (`tool.execute`): green
- Memory operations (`memory.*`): orange
- Error spans (status.code == "ERROR"): red border/fill
- Other: gray

Each bar shows duration text (e.g., "234ms") on or near the bar.

### 6.4 SpanDetail Panel

When a span is clicked in the waterfall:
- Show all attributes as a key-value table
- Show events chronologically
- For `gen_ai.prompt` and `gen_ai.completion` events: render a dedicated PromptViewer component
- PromptViewer shows the full content **collapsed by default**, with a toggle to expand
- Use a monospace font for prompt/completion text
- Error spans show the exception details prominently (from `span.record_exception()` data)

### 6.5 Real-time Updates

The TraceViewerPage connects to the existing WebSocket (`/v1/ws`) and listens for `trace_started`, `span_completed`, and `trace_completed` messages.

- `trace_started`: Add a new entry to the trace list with a "running" indicator.
- `span_completed`: If the trace is currently being viewed, append the span to the display and re-render the waterfall. If the trace is in the list, update its span_count and duration.
- `trace_completed`: Mark the trace as complete in the list (stop the "running" indicator, show final duration).

The frontend filters all trace WebSocket messages client-side by the currently selected `scene_id`.

### 6.6 TypeScript Types

```typescript
interface TraceSpan {
  traceId: string;
  spanId: string;
  parentSpanId: string | null;
  name: string;
  kind: string;
  startTimeMs: number;     // milliseconds since epoch
  endTimeMs: number;       // milliseconds since epoch
  durationMs: number;
  status: { code: string; description?: string };
  attributes: Record<string, string | number | boolean>;
  events: SpanEvent[];
}

interface SpanEvent {
  name: string;
  timestampMs: number;     // milliseconds since epoch
  attributes: Record<string, string | number | boolean>;
}

interface TraceSummary {
  traceId: string;
  sceneId: string;
  eventType: string;
  startTime: string;
  durationMs: number;
  spanCount: number;
  rootSpanName: string;
}
```

## 7. Frontend: Chat Debug Mode

### 7.1 Debug Toggle

Add a toggle switch to the ChatWidget component header area. This toggles a `debugMode` state in AppContext.

When `debugMode` is true and a message has an associated `trace_id`:
- Render a small icon (e.g., Lucide `Activity` or `Bug` icon) next to the chat bubble
- The icon is a `<Link>` to `/sidestage/traces/<scene_id>/<trace_id>`
- Use a subtle style (muted color, small size) so it doesn't distract from the chat

### 7.2 Trace ID Flow

1. Each chat message has a unique `id` (e.g., `msg_abc123`)
2. The trace for that message is stored with `event_id = msg_abc123` in the `traces` table
3. When debug mode is on and a user clicks the trace icon on a chat bubble, the frontend calls `GET /v1/traces?event_id=<message_id>` to resolve the trace_id
4. Then navigates to `/sidestage/traces/<scene_id>/<trace_id>`
5. This works for both live and historical messages (as long as the trace is still in storage)

## 8. Implementation Order

The implementation should proceed in this order to enable incremental testing:

1. **TraceConfig + config.yml** - Add tracing config model and YAML support
2. **Tracing module core** - TracerProvider setup, FilteringSpanProcessor, init/toggle/shutdown
3. **InMemoryTraceExporter** - In-memory storage with ring buffer and span serialization
4. **SQLiteTraceExporter** - Persistence layer with raw sqlite3, tables, indexes, retention cleanup
5. **Backend instrumentation** - Add spans to all key points (scene, agent, memory, embedding)
6. **Entity import tracing** - Add tracing to reload_defaults with campaign_planning scene
7. **REST API endpoints** - /v1/traces, /v1/tracing/toggle, /v1/tracing/status
8. **WebSocket trace messages** - trace_started, span_completed, trace_completed via SyncManager
9. **Frontend TraceViewerPage** - Route, trace list, waterfall, span detail
10. **Frontend real-time updates** - WebSocket integration in trace viewer
11. **Frontend chat debug mode** - Toggle, trace link icons on chat bubbles

## 9. Testing Strategy

### 9.1 Unit Tests

- **TraceConfig**: Validate config parsing from YAML, defaults, field validation
- **FilteringSpanProcessor**: Verify enabled/disabled flag correctly passes/discards spans
- **InMemoryTraceExporter**: Export spans, ring buffer eviction, query by scene_id, thread safety
- **SQLiteTraceExporter**: Export spans, table creation, query traces/spans, retention cleanup, reload on init
- **Instrumentation helpers**: trace_span async decorator, current_trace_id, add_trace_event with config flags, record_error
- **Span serialization**: Verify the dict format matches the TypeScript types (millisecond timestamps)
- **Toggle**: Verify flipping FilteringSpanProcessor enabled flag works correctly

### 9.2 Integration Tests

- **Full event flow**: Send a chat message, verify a complete trace is created with expected span hierarchy
- **NPC response**: Verify agent.run span contains nested llm.completion and tool.execute spans
- **Memory operations**: Verify memory tool spans appear under the agent span
- **Embedding propagation**: Verify background embedding span appears under the parent trace
- **NPC reply trace**: Verify the reply creates a separate trace with origin_trace_id attribute
- **API endpoints**: GET /v1/traces returns correct data, POST toggle works
- **WebSocket**: Connect a WebSocket client, send a chat message, verify trace WebSocket messages arrive
- **Error recording**: Trigger an error in an instrumented path, verify span status is ERROR with exception details

### 9.3 Frontend Tests

- **TraceTimeline**: Given a list of spans, renders correct tree structure and bar positions
- **SpanDetail**: Given a span with events, renders attributes and expandable prompt content
- **Debug mode**: Toggle on, verify trace link icons appear on chat bubbles with trace_ids
- **Real-time**: Simulate WebSocket messages, verify trace list and waterfall update

## 10. Edge Cases and Error Handling

- **Tracing initialization failure**: If SQLite table creation fails, log a warning and continue with in-memory only. Tracing should never prevent the application from starting.
- **Span export failure**: Both exporters catch and log errors in `export()`, never propagating exceptions to the traced code.
- **Toggle during active traces**: When tracing is toggled off mid-trace, in-flight spans are discarded by the FilteringSpanProcessor. Partially-complete traces may exist in the in-memory buffer and SQLite. The trace viewer should handle traces with missing spans gracefully (show what exists, don't crash).
- **Large prompts**: The `max_attribute_length` config truncates event attribute values. The truncation adds a `[truncated]` suffix.
- **Missing trace_id on chat messages**: Frontend gracefully hides the debug icon when trace_id is absent (for historical messages or when tracing is disabled).
- **Context propagation in create_task**: If the asyncio event loop is not running (edge case in tests), the _fire_embed fallback handles RuntimeError. The tracing wrapper similarly degrades gracefully.
- **Server restart**: On startup, init_tracing loads recent traces from SQLite into the in-memory buffer so the trace viewer immediately has historical data.
- **Error spans**: All instrumented try/except blocks call `record_error(span, exc)` to set status to ERROR and record the exception. Error spans are visually distinct (red) in the trace viewer.
- **Provider shutdown**: `shutdown_tracing()` is called during `_lifespan` teardown to flush any pending BatchSpanProcessor spans to SQLite.

## 11. Performance Considerations

- **FilteringSpanProcessor when disabled**: Spans are still created (minimal object allocation) but immediately discarded in `on_end()`. This is very low overhead -- a few microseconds per span site.
- **SimpleSpanProcessor for in-memory**: Synchronous, no-I/O export. Negligible latency.
- **BatchSpanProcessor for SQLite**: Exports in a background thread, never blocking the async event loop. Default batch size and interval are appropriate for this low-volume application.
- **In-memory buffer size**: Default 500 traces. Each trace averages ~10 spans, each span ~2KB serialized = ~10MB total. Well within memory constraints.
- **SQLite retention**: Default 5000 traces, 72-hour max age. Cleanup runs on startup and periodically.
- **WebSocket broadcast of trace events**: Sent to all connected clients. Frontend filters client-side. At typical volumes (<100 spans per user message), this is negligible bandwidth.
