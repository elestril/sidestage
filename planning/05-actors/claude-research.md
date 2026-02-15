# Research Findings: Actor Restructuring (05-actors)

## Codebase Research

### 1. Current Actor/Agent Architecture

**File:** `src/sidestage/character.py`

- **`AgentActor` class (lines 20-156)**: Manages the LLM "brain" of a Character
  - One `AgentActor` per `Character` that can speak in the scene
  - Manages LiteLLMAgent instance associated with character
  - Processes events dispatched by Scene's EventQueue worker
  - Generates responses via LLM and puts them back on queue
  - Has a unique `actor_id` format: `f"agent:{character.id}"`
  - `_update_prompt()` loads prompt templates based on `unseen` status
  - `async on_event(event: EventModel)` handles ChatMessageModel events
  - Calls `assemble_context()` from memory system before agent runs
  - Calls `scene_logic.create_message()` to generate reply

- **`Character` class (lines 158-210)**: Runtime wrapper for Character entity
  - Manages lifecycle of character's AgentActor ("brain")
  - Wraps CharacterModel (the data)
  - `async activate()` and `async deactivate()` methods
  - Optional `AgentActor` in its `actor` field

### 2. Current EventModel Hierarchy

**File:** `src/sidestage/models.py` (lines 51-126)

| Class | Entity Type | Key Fields | Purpose |
|-------|-------------|-----------|---------|
| `EventModel` (base) | "Event" | `scene_id`, `gametime`, `walltime` | Base event class |
| `ChatMessageModel` | "ChatMessage" | + `character_id`, `actor_id`, `message`, `widget` | Chat messages |
| `JoinEventModel` | "JoinEvent" | + `actor_id` | Actor joins scene |
| `LeaveEventModel` | "LeaveEvent" | + `actor_id` | Actor leaves scene |
| `FastForwardEventModel` | "FastForwardEvent" | + `duration_str` | Time advancement (unused) |

ChatMessageModel has `backfill_legacy_fields()` validator for legacy migration, `message` field for chat text, optional `widget` field. Note: both `body` (inherited) and `message` fields store text (redundant).

### 3. SceneModel and Event Flow

**File:** `src/sidestage/scene.py`

SceneModel fields:
- `current_gametime: Optional[int]`
- `location_id: Optional[str]`
- `events: List[str]` — event IDs only
- `messages: List[ChatMessageModel]` — full objects (TO BE REMOVED per spec)

Current event flow:
1. Event added to EventQueue via `scene.queue.put(event)`
2. Queue worker calls `Scene._process_event(event)`
3. `_process_event()`: persists to SQLite, creates graph node/edges, broadcasts to WebSocket, for user events calls `_dispatch_to_npcs(event)`
4. `_dispatch_to_npcs()` sends event to each active character's AgentActor via `actor.on_event(event)`

### 4. WebSocket Management (No User Concept)

**File:** `src/sidestage/sync.py`

- `SyncManager` class: simple WebSocket connection manager
- Maintains `active_connections: List[WebSocket]`
- All connected clients treated equally — no user identification
- Broadcasts to all or excluding sender

**File:** `src/sidestage/orchestrator.py` (lines 249-257)

WebSocket endpoint: connects anonymously, no user concept.

### 5. Chat Message Creation and Persistence

**File:** `src/sidestage/scene.py` (lines 182-213)

`Scene.create_message()` creates ChatMessageModel with redundant `body` and `message` fields.

Persistence: appends to `SceneModel.messages` list, writes entire SceneModel to SQLite via `Storage.update_scene()`.

### 6. Current Tracing Infrastructure

**Provider:** `src/sidestage/tracing/provider.py`
- Global tracer provider with OTLP exporter and `FilteringSpanProcessor`
- `init_tracing(config, campaign_name)` validates endpoint reachability
- Runtime toggle support

**Instrumentation points:**
- `scene.py`: `scene.process_event` span, `scene.dispatch_to_npcs` span
- `character.py`: `agent.on_event` span in AgentActor
- `campaign.py`: `campaign.reload_defaults` span
- Memory system: context assembly and tool execution spans

**Utilities:** `src/sidestage/tracing/middleware.py`
- `trace_span(name, attributes)`: decorator for async functions
- `current_trace_id()`: get current trace ID as hex string
- `add_trace_event(name, attributes)`: add event with capture flag checks
- `record_error(span, exc)`: record exception in span

**Config:** `TraceConfig` in `config.py` — enabled, otlp_endpoint, capture flags, max_attribute_length

**API endpoints:** `GET /v1/tracing/status`, `POST /v1/tracing/toggle`

### 7. Campaign and User Model

- `Campaign` class in `campaign.py`: represents single campaign, no explicit User concept
- `Orchestrator` manages campaigns, single active at a time, no user associations
- **NO User class exists yet** — this is introduced by the spec

### 8. Testing Setup

- **Framework:** pytest
- **Fixtures:** `conftest.py` with `_init_config`, `_reset_otel_provider`, `llm_base_url`
- **Organization:** `tests/unit/` and `tests/integration/`
- **Markers:** `@pytest.mark.llm` for LLM-dependent tests (auto-skipped if unreachable)
- **Patterns:** Direct model instantiation, async test functions

---

## Web Research

### Python asyncio.Queue Patterns

**Source:** [Python docs - asyncio Queue](https://docs.python.org/3/library/asyncio-queue.html)

Key patterns for the Scene event loop:

**Producer-Consumer with graceful shutdown:**
```python
async def worker(name, queue):
    while True:
        item = await queue.get()
        # process item...
        queue.task_done()

async def main():
    queue = asyncio.Queue()
    # Create workers
    tasks = [asyncio.create_task(worker(f'w-{i}', queue)) for i in range(3)]
    # Add work...
    await queue.join()  # Wait for all items processed
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
```

**Shutdown pattern (Python 3.13+):**
```python
await queue.shutdown(immediate=False)  # Stop accepting new items, drain existing
await queue.shutdown(immediate=True)   # Drain immediately, unblock waiters
```
- `QueueShutDown` exception raised on `get()`/`put()` after shutdown
- `join()` may unblock without work done on immediate shutdown

**Recommendations for Scene.process():**
- Use `asyncio.Queue` (not thread-safe — designed for async/await)
- `task_done()` + `join()` for coordinated completion
- Consider bounded queue (`maxsize > 0`) to prevent overload
- Use `asyncio.create_task()` for background worker
- Handle `QueueShutDown` or `asyncio.CancelledError` for graceful shutdown

### OpenTelemetry Span Links

**Sources:**
- [OpenTelemetry Python Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [Span Links Practical Guide](https://dev.to/clericcoder/mastering-trace-analysis-with-span-links-using-opentelemetry-and-signoz-a-practical-guide-52hm)

**Creating span links in Python:**
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Capture context from original span
with tracer.start_as_current_span("original-span") as original:
    ctx = original.get_span_context()
    link = trace.Link(ctx)

# Create new root span that links back (NOT a child)
with tracer.start_as_current_span("new-root-span", links=[link]):
    pass  # This span links to but is not a child of original
```

**When to use links vs parent-child:**
- **Parent-child:** Direct causality, synchronous call chains
- **Span links:** Correlation without direct causation — "these are related but one didn't directly cause the other"

**Key use cases matching our spec:**
1. **Async queue processing:** User request creates event -> event enqueued -> queue worker processes with new root span linked to original
2. **Batch processing:** Multiple events in a scene dispatch, each NPC response linked to triggering event
3. **Background jobs:** LLM agent processing linked to user message that triggered it

**Best practices:**
- Add links at span creation time (samplers can only consider info present at creation)
- Use selectively — only link spans with meaningful relationships
- Verify spans are active when capturing context
- Creating a new root span: just don't pass a parent context, but DO pass `links=[...]`

**Pattern for Scene.process() tracing:**
```python
# When event enters queue, capture its span context
incoming_ctx = trace.get_current_span().get_span_context()
link = trace.Link(incoming_ctx)

# In queue worker, create NEW root span with link to original
with tracer.start_as_current_span("scene.process_event", links=[link]):
    # Process event in new trace, linked to original
    pass
```

This matches the spec requirement: "The Scene.process() method replaces the spans of the incoming event with a new root span, but links the two spans."
