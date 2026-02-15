Now I have all the context I need. Let me generate the section content.

# Section 05: Tracing Integration

## Overview

This section adds OpenTelemetry tracing to the new Event/Actor/Scene architecture introduced in prior sections. The key pattern is **span context propagation through the event queue**: when an event is created (e.g., from an HTTP request or WebSocket message), the current span context is captured and carried through the asyncio queue. When the scene processes the event, a new root span is created and **linked** (not parented) to the original span context. Actor processing creates child spans under the scene's processing span.

This section depends on:
- **section-01-event-model** -- the `Event` wrapper class with `span_context` field, and the `EventModel` with `event_type`
- **section-04-scene-loop** -- the `Scene._process_event()`, `Scene._dispatch()`, and `NPCActor.process()` methods that need tracing instrumentation

## Files to Modify

| File | Change |
|------|--------|
| `src/sidestage/event.py` | `Event.from_model()` captures span context |
| `src/sidestage/scene.py` | `_process_event()` creates linked root span; `_dispatch()` spans |
| `src/sidestage/actors.py` | `NPCActor.process()` creates child span with character attributes |
| `tests/unit/test_tracing_instrumentation.py` | Update existing tests, add new span-linking tests |

## Background: Existing Tracing Infrastructure

Sidestage already has a full OpenTelemetry tracing subsystem:

- **`src/sidestage/tracing/provider.py`** -- `TracerProvider` setup with `FilteringSpanProcessor` and OTLP HTTP export. Runtime toggle via `toggle_tracing()`. Endpoint validation before enabling.
- **`src/sidestage/tracing/middleware.py`** -- Helper functions: `trace_span()` decorator, `current_trace_id()`, `add_trace_event()` (respects capture flags and truncation), `record_error()` (sets ERROR status and records exception).
- **Module-level tracers** -- Each instrumented module creates its own tracer: `tracer = trace.get_tracer("sidestage.scene")`, `tracer = trace.get_tracer("sidestage.character")`, etc.

The test infrastructure uses a `_SpanCollector` exporter and an `otel_exporter` fixture that replaces module-level tracers with real SDK tracers bound to a fresh provider (see existing `tests/unit/test_tracing_instrumentation.py`).

## Tracing Design

### Span Lifecycle for Events

1. **Event creation** (`Event.from_model()`): Captures the current span context via `trace.get_current_span().get_span_context()`. This happens when an event enters the system -- from an HTTP handler, WebSocket message handler, or from an NPCActor generating a response. The captured context travels through the asyncio queue as a field on the `Event` dataclass.

2. **Queue transit**: The `Event` object sits in the `asyncio.Queue[Event]` carrying its `span_context`. No tracing happens here -- it is just data in transit.

3. **Processing** (`Scene._process_event()`): Creates a **new root span** named `"scene.process_event"`. This is NOT a child span of the original context. Instead, it is **linked** to the original span context via `trace.Link(event.span_context)`. This linking pattern is deliberate: the event queue decouples the producer and consumer, so a parent-child relationship would be misleading. A link preserves the causal connection while keeping the traces independent.

4. **Dispatch** (`Scene._dispatch()`): Each `actor.process(event)` call runs within the scene's processing span. `NPCActor.process()` creates a **child span** named `"npc_actor.process"`, which in turn contains child spans for the LLM agent call (`agent.run` and `llm.completion` from the existing agent instrumentation).

### Span Hierarchy

```
HTTP/WebSocket request span (original context)
    [linked to]
scene.process_event (new root span)
    |-- sidestage.scene.id = "scene_01"
    |-- sidestage.event.type = "ChatMessage"
    |-- sidestage.event.id = "evt_abc123"
    |
    +-- npc_actor.process (child span)
        |-- sidestage.character.id = "char_npc1"
        |-- sidestage.character.name = "Gandalf"
        |
        +-- agent.run (child, from existing agent.py instrumentation)
            +-- llm.completion (child)
```

### Error Event Tracing

When `NPCActor.process()` catches an LLM error:
1. The error is recorded on the `npc_actor.process` span via `record_error(span, exc)`.
2. The NPCActor creates an ERROR event and enqueues it via `event.scene.process(error_event)`.
3. The error event's `Event.from_model()` call captures the current span context (which is the `npc_actor.process` span). This means the error event's subsequent processing trace will be linked back to the failed actor span.

---

## Tests

**Test file:** `tests/unit/test_tracing_instrumentation.py` (extend existing)

The existing test file already has the `otel_exporter` fixture with `_SpanCollector` and module-level tracer replacement. The tests below follow the same patterns. After sections 01 and 04 are implemented, the existing test helpers (`_make_chat_message`, etc.) will need updating for the new `EventModel` with `event_type`. The tracing tests below assume those updates are in place.

### Test: Event.from_model() captures span context from active tracer

```python
class TestEventSpanContext:
    def test_from_model_captures_span_context(self, otel_exporter):
        """Event.from_model() captures the current span context when a span is active."""
        from sidestage.event import Event
        from sidestage.models import EventModel, EventType

        model = _make_event_model(event_type=EventType.CHAT_MESSAGE)
        tracer = trace.get_tracer("test")

        with tracer.start_as_current_span("test_span") as span:
            expected_ctx = span.get_span_context()
            event = Event.from_model(model)

        assert event.span_context is not None
        assert event.span_context.trace_id == expected_ctx.trace_id
        assert event.span_context.span_id == expected_ctx.span_id
```

### Test: Event.from_model() sets span_context=None when no active span

```python
    def test_from_model_no_active_span(self):
        """Event.from_model() sets span_context to None when no tracing is active."""
        from sidestage.event import Event
        from sidestage.models import EventModel, EventType

        model = _make_event_model(event_type=EventType.CHAT_MESSAGE)
        event = Event.from_model(model)

        # When no real span is active, span_context is either None
        # or an INVALID_SPAN_CONTEXT (trace_id == 0). Both are acceptable.
        if event.span_context is not None:
            assert event.span_context.trace_id == 0
```

### Test: Scene._process_event() creates new root span with link to event.span_context

```python
class TestSceneProcessEventTracing:
    @pytest.mark.anyio
    async def test_creates_linked_root_span(self, otel_exporter):
        """_process_event() creates a new root span linked to the event's span context."""
        from sidestage.scene import Scene
        from sidestage.event import Event
        from sidestage.models import EventType

        scene = _make_test_scene()  # Helper that creates a Scene with mocked dependencies
        model = _make_event_model(event_type=EventType.CHAT_MESSAGE)

        # Create event with a known span context
        test_tracer = trace.get_tracer("test")
        with test_tracer.start_as_current_span("origin_span") as origin:
            origin_ctx = origin.get_span_context()
            event = Event.from_model(model)

        # Process the event (outside the original span)
        await scene._process_event(event)

        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 1

        process_span = spans[0]
        # Verify it has a link to the origin span
        assert len(process_span.links) == 1
        link = process_span.links[0]
        assert link.context.trace_id == origin_ctx.trace_id
        assert link.context.span_id == origin_ctx.span_id

        # Verify it is a NEW root (not a child of origin)
        assert process_span.parent is None or process_span.parent.trace_id != origin_ctx.trace_id
```

### Test: Scene._process_event() sets span attributes

```python
    @pytest.mark.anyio
    async def test_span_attributes(self, otel_exporter):
        """_process_event() sets scene.id and event.type as span attributes."""
        from sidestage.scene import Scene
        from sidestage.event import Event
        from sidestage.models import EventType

        scene = _make_test_scene(scene_id="scene_42")
        model = _make_event_model(event_type=EventType.CHAT_MESSAGE, id="evt_test99")
        event = Event.from_model(model)

        await scene._process_event(event)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert span.attributes["sidestage.scene.id"] == "scene_42"
        assert span.attributes["sidestage.event.type"] == "ChatMessage"
```

### Test: Scene._process_event() handles event with no span_context (no link created)

```python
    @pytest.mark.anyio
    async def test_no_span_context_no_link(self, otel_exporter):
        """When event.span_context is None, the processing span has no links."""
        from sidestage.scene import Scene
        from sidestage.event import Event
        from sidestage.models import EventType

        scene = _make_test_scene()
        model = _make_event_model(event_type=EventType.CHAT_MESSAGE)
        event = Event(model=model, span_context=None)

        await scene._process_event(event)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert len(span.links) == 0
```

### Test: NPCActor.process() creates child span under scene's processing span

```python
class TestNPCActorTracing:
    @pytest.mark.anyio
    async def test_creates_child_span(self, otel_exporter):
        """NPCActor.process() creates a child span named 'npc_actor.process'."""
        from sidestage.actors import NPCActor
        from sidestage.event import Event
        from sidestage.models import EventType

        actor = _make_npc_actor(character_id="char_npc1", character_name="Gandalf")
        # Mock the LLM agent to return no content
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content=None))

        model = _make_event_model(event_type=EventType.CHAT_MESSAGE, actor_id="user")
        event = Event.from_model(model)
        event.scene = _make_mock_scene()

        # Run within a parent span to verify child relationship
        test_tracer = trace.get_tracer("test")
        with test_tracer.start_as_current_span("parent_span"):
            await actor.process(event)

        spans = _find_spans(otel_exporter, "npc_actor.process")
        assert len(spans) == 1

        npc_span = spans[0]
        assert npc_span.attributes["sidestage.character.id"] == "char_npc1"
        assert npc_span.attributes["sidestage.character.name"] == "Gandalf"
```

### Test: NPCActor error records on span and error event gets span context

```python
    @pytest.mark.anyio
    async def test_llm_error_records_on_span(self, otel_exporter):
        """When the LLM agent raises, the error is recorded on the npc_actor.process span."""
        from sidestage.actors import NPCActor
        from sidestage.event import Event
        from sidestage.models import EventType

        actor = _make_npc_actor()
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        model = _make_event_model(event_type=EventType.CHAT_MESSAGE, actor_id="user")
        event = Event.from_model(model)
        event.scene = _make_mock_scene()

        await actor.process(event)

        spans = _find_spans(otel_exporter, "npc_actor.process")
        assert len(spans) == 1
        assert spans[0].status.status_code.name == "ERROR"
```

### Helper: _make_event_model factory

This helper replaces `_make_chat_message` for the new EventModel structure. It should be added to the test file alongside the existing helpers.

```python
def _make_event_model(**overrides) -> "EventModel":
    """Create an EventModel with sensible defaults for testing."""
    from sidestage.models import EventModel, EventType, Visibility
    defaults = dict(
        id="evt_test1",
        name="Test Event",
        body="Hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_01",
        gametime=0,
        walltime="2025-01-01T00:00:00",
        actor_id="user",
        character_id="user",
        visibility=Visibility.PUBLIC,
    )
    defaults.update(overrides)
    return EventModel(**defaults)
```

---

## Implementation Details

### Event.from_model() -- Span Context Capture

**File:** `src/sidestage/event.py`

The `Event.from_model()` class method (or static factory) captures the current span context at creation time. This is the only place where span context enters the Event system.

```python
from opentelemetry import trace
from opentelemetry.trace import SpanContext

class Event:
    """Runtime event wrapper carrying model data and tracing context."""
    model: EventModel
    span_context: SpanContext | None = None
    scene: "Scene | None" = None

    @classmethod
    def from_model(cls, model: EventModel) -> "Event":
        """Create an Event, capturing current span context if tracing is active."""
        span = trace.get_current_span()
        ctx = span.get_span_context()
        # Only store valid span contexts (trace_id != 0)
        span_context = ctx if ctx and ctx.trace_id != 0 else None
        return cls(model=model, span_context=span_context)
```

The key detail is checking `ctx.trace_id != 0`. When no span is active, OpenTelemetry returns an `INVALID_SPAN_CONTEXT` with `trace_id == 0`. We normalize this to `None` to simplify downstream checks.

### Scene._process_event() -- Linked Root Span

**File:** `src/sidestage/scene.py`

The `_process_event` method is the queue worker callback. It creates a new root span with a link to the incoming event's span context. The module-level tracer is already defined: `tracer = trace.get_tracer("sidestage.scene")`.

```python
async def _process_event(self, event: Event) -> None:
    """Queue worker handler. Persist, dispatch to all actors."""
    links = []
    if event.span_context:
        links.append(trace.Link(event.span_context))

    with tracer.start_as_current_span("scene.process_event", links=links) as span:
        span.set_attribute("sidestage.scene.id", self.id)
        span.set_attribute("sidestage.event.type", event.model.event_type.value)
        span.set_attribute("sidestage.event.id", event.model.id)
        try:
            # Persist event to storage and graph
            # ... (persistence logic from section-04)

            # Dispatch to all present actors
            await self._dispatch(event)
        except Exception as exc:
            record_error(span, exc)
            raise
```

Key points:
- `links=links` creates a link to the original span context without making the processing span a child of it. This is the correct pattern for async queue consumers.
- `trace.Link(event.span_context)` creates a link from the `SpanContext` object stored on the Event.
- The span is created even when `event.span_context` is None -- it just has no links in that case.
- `event.model.event_type.value` gives the string value (e.g., `"ChatMessage"`) since `EventType` is a `str` enum.

### NPCActor.process() -- Child Span

**File:** `src/sidestage/actors.py`

The NPCActor creates a child span within the scene's processing span context. The module needs its own tracer: `tracer = trace.get_tracer("sidestage.actors")`.

```python
from opentelemetry import trace
from sidestage.tracing.middleware import record_error

tracer = trace.get_tracer("sidestage.actors")

class NPCActor(Actor):
    async def process(self, event: Event) -> None:
        """React to user chat messages by generating LLM responses."""
        # Guard: only react to CHAT_MESSAGE from User actors
        # ... (guard logic from section-02)

        with tracer.start_as_current_span("npc_actor.process") as span:
            span.set_attribute("sidestage.character.id", self.character_id)
            span.set_attribute("sidestage.character.name", self.character_name)
            try:
                # Assemble context, call LLM, enqueue response
                # ... (actor logic from section-02)
                pass
            except Exception as exc:
                record_error(span, exc)
                # Create ERROR event and enqueue it
                # Event.from_model() here captures THIS span's context,
                # linking the error event's processing trace back to this failure
                error_event = Event.from_model(error_model)
                await event.scene.process(error_event)
```

The `npc_actor.process` span is automatically a child of the current span (which is `scene.process_event` because `_dispatch` is called within that span's context). The existing `agent.run` and `llm.completion` spans from `agent.py` become grandchildren in the hierarchy.

### otel_exporter Fixture Update

**File:** `tests/unit/test_tracing_instrumentation.py`

The `otel_exporter` fixture needs to include the new `sidestage.actors` module tracer. Add this line alongside the existing module tracer replacements:

```python
import sidestage.actors as _actors
_actors.tracer = provider.get_tracer("sidestage.actors")
```

If `event.py` also has a module-level tracer (for `Event.from_model()` if it were instrumented with spans), add it too. However, `Event.from_model()` only reads the current span context -- it does not create any spans, so no tracer is needed in `event.py`.

### Existing Test Updates

The following existing test classes in `tests/unit/test_tracing_instrumentation.py` need updating for the new architecture:

1. **`TestProcessEvent`** -- Update to use `Event` wrapper instead of raw `ChatMessageModel`. The span name stays `"scene.process_event"` but now the test verifies link presence. The `test_non_chatmessage_no_span` test changes: all event types now get spans (the guard for ChatMessage-only is removed in the new architecture). Update `_make_chat_message` calls to `_make_event_model`.

2. **`TestDispatchToNpcs`** -- Rename to `TestDispatch` and update for the new `_dispatch()` method signature which takes `Event` not `ChatMessageModel` and dispatches to all actors (not just NPCs). The span name changes from `"scene.dispatch_to_npcs"` to the scene's processing span (dispatch happens within it, not as a separate span).

3. **`TestAgentOnEvent`** -- Rename to `TestNPCActorProcess` and update for `NPCActor.process()` instead of `AgentActor.on_event()`. The span name changes from `"agent.on_event"` to `"npc_actor.process"`. Character attribute assertions stay the same.

### Attribute Conventions

All custom span attributes use the `sidestage.` prefix for namespace isolation:

| Attribute | Type | Example | Set By |
|-----------|------|---------|--------|
| `sidestage.scene.id` | string | `"scene_01"` | `Scene._process_event()` |
| `sidestage.event.type` | string | `"ChatMessage"` | `Scene._process_event()` |
| `sidestage.event.id` | string | `"evt_abc123"` | `Scene._process_event()` |
| `sidestage.character.id` | string | `"char_npc1"` | `NPCActor.process()` |
| `sidestage.character.name` | string | `"Gandalf"` | `NPCActor.process()` |

### LLM Call Data in Traces

The existing `add_trace_event()` function in `src/sidestage/tracing/middleware.py` already handles recording LLM prompts, completions, and tool calls as span events with capture flag checks. NPCActor does not need to add new instrumentation for this -- it inherits it from the `LiteLLMAgent.arun()` call which already creates `agent.run` and `llm.completion` spans and records `gen_ai.prompt`/`gen_ai.completion` events.

The only new tracing code in actors is the `npc_actor.process` span wrapper and the `record_error` call on failure.