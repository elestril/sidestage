Now I have all the context I need. Let me generate the section content.

# Section 04: Backend Instrumentation

## Overview

This section adds manual OpenTelemetry span instrumentation at all key points in the Sidestage backend. After completing the tracing module core (section-02) and exporters (section-03), this section instruments the existing application code so that every user message produces a structured trace showing the full lifecycle: event processing, NPC dispatch, context assembly, LLM calls, tool execution, memory operations, background embedding, and entity imports.

**Dependencies:** Sections 01 (TraceConfig), 02 (tracing core -- `init_tracing`, `toggle_tracing`, `FilteringSpanProcessor`, convenience helpers), and 03 (InMemoryTraceExporter, SQLiteTraceExporter) must be complete before this section.

## Architecture Summary

Each `ChatMessage` event arriving at the `EventQueue` creates one independent trace. The span hierarchy for a user message looks like:

```
scene.process_event (root)
  |-- scene.dispatch_to_npcs
  |     |-- agent.on_event (per NPC)
  |           |-- memory.assemble_context
  |           |-- agent.run
  |                 |-- llm.completion (per turn)
  |                 |     |-- tool.execute (per tool call)
  |                 |-- memory.embed (background, context-propagated)
```

When an NPC posts a reply back on the queue, that reply creates a second, lightweight trace (just persist + broadcast, no dispatch). The NPC reply trace carries an `origin_trace_id` attribute linking back to the user message trace.

## Instrumentation Attribute Conventions

All custom attributes use the `sidestage.` namespace prefix (e.g., `sidestage.scene.id`, `sidestage.event.id`). LLM-related attributes follow OpenTelemetry semantic conventions for GenAI (e.g., `gen_ai.request.model`, `gen_ai.usage.input_tokens`). Tool and agent attributes use `tool.` and `agent.` prefixes respectively.

---

## Tests First

All tests go in `/home/harald/src/sidestage/tests/unit/test_tracing_instrumentation.py`. They use `pytest` with `pytest-anyio` for async tests and follow the existing project conventions (MagicMock for dependencies, `@pytest.mark.anyio` for async tests, the autouse `_init_config` fixture from `conftest.py`).

The tests verify that instrumented code creates the expected spans with the correct names, attributes, and parent-child relationships. They do NOT require a live LLM or database -- all external dependencies are mocked.

### Test File Structure

**File:** `/home/harald/src/sidestage/tests/unit/test_tracing_instrumentation.py`

```python
"""Tests for backend tracing instrumentation.

Verifies that spans are created with correct names, attributes, and hierarchy
at each instrumentation point. Uses a real OTel TracerProvider with an
InMemorySpanExporter to capture spans for assertion.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from sidestage.schemas import Character, ChatMessage


@pytest.fixture
def otel_exporter():
    """Set up an OTel InMemorySpanExporter for capturing spans in tests.

    Installs a real TracerProvider with SimpleSpanProcessor so that
    all spans created during the test are captured.
    Restores the previous provider after the test.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    old_provider = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)
    yield exporter
    provider.shutdown()
    trace.set_tracer_provider(old_provider)


def _make_chat_message(**overrides) -> ChatMessage:
    """Helper to build a ChatMessage with sensible defaults."""
    defaults = dict(
        id="msg_test1",
        name="Test Message",
        body="Hello",
        actor_id="user",
        character_id="user",
        message="Hello",
        scene_id="scene_01",
        gametime=0,
        walltime="2025-01-01T00:00:00",
    )
    defaults.update(overrides)
    return ChatMessage(**defaults)
```

### 4.1 SceneLogic._process_event Tests

```python
# Test: processing a ChatMessage creates a root span named "scene.process_event"
# Test: root span has attributes: sidestage.scene.id, sidestage.event.id, sidestage.event.type, sidestage.actor.id
# Test: processing a non-ChatMessage event does NOT create a span (isinstance check)
# Test: exception during processing sets span status to ERROR
# Test: root span contains child spans for dispatch (when event.actor_id == "user")
```

Each test sets up a `SceneLogic` with mocked `Storage` and `LiteLLMAgent`, calls `_process_event` with a `ChatMessage`, and then inspects the spans captured by the `otel_exporter` fixture. The key assertions check span name, attributes, and status.

### 4.2 SceneLogic._dispatch_to_npcs Tests

```python
# Test: dispatch creates span named "scene.dispatch_to_npcs"
# Test: span has sidestage.npc_count attribute matching number of characters
# Test: per-NPC on_event spans appear as children of dispatch span
```

### 4.3 AgentActor.on_event Tests

```python
# Test: on_event creates span named "agent.on_event"
# Test: span has sidestage.character.id and sidestage.character.name attributes
# Test: exception during on_event sets span status to ERROR
# Test: child spans (memory.assemble_context, agent.run) are nested correctly
```

### 4.4 assemble_context Tests

```python
# Test: assemble_context creates span named "memory.assemble_context"
# Test: span has sidestage.owner_id, sidestage.scene.id, and memory.token_estimate attributes
```

### 4.5 LiteLLMAgent.arun Tests

```python
# Test: arun creates parent span "agent.run" with gen_ai.request.model attribute
# Test: each LLM call creates child span "llm.completion" with agent.turn attribute
# Test: prompt events are added when capture_prompts=True
# Test: prompt events are NOT added when capture_prompts=False
# Test: completion event is added after LLM response
# Test: token usage attributes are set when response.usage is available
# Test: token usage attributes are skipped when response.usage is None
# Test: tool calls create child spans "tool.execute" with tool.name attribute
# Test: tool arguments are captured when capture_tool_args=True
# Test: total turn count and token totals are set on parent span
# Test: LLM exception sets span status to ERROR
# Test: finish_reasons attribute captures response finish reasons
```

### 4.6 Memory Tool Operations Tests

```python
# Test: MemoryTools.update_scene_memory creates span "memory.update_scene_memory"
# Test: MemoryTools.update_character_memory creates span "memory.update_character_memory"
# Test: DmMemoryTools.update_common_memory creates span "memory.update_common_memory"
# Test: DmMemoryTools.update_canonical_memory creates span "memory.update_canonical_memory"
# Test: DmMemoryTools.add_world_fact creates span "memory.add_world_fact"
# Test: memory content is added as span event when capture_memory_content=True
# Test: memory content is NOT added when capture_memory_content=False
# Test: exception in memory operation sets span status to ERROR
```

### 4.7 Background Embedding Tests

```python
# Test: _fire_embed propagates trace context to background task
# Test: background embedding span "memory.embed" appears under parent trace
# Test: embedding span has memory.id attribute
# Test: both MemoryTools and DmMemoryTools _fire_embed are instrumented
# Test: RuntimeError from missing event loop is handled gracefully
```

### 4.9 Entity Import Tracing Tests

```python
# Test: reload_defaults creates span "campaign.reload_defaults"
# Test: span has sidestage.scene.id attribute set to "campaign_planning"
# Test: span has entities.loaded_count attribute
```

---

## Implementation Details

### 4.1 Instrument SceneLogic._process_event (Root Span)

**File:** `/home/harald/src/sidestage/src/sidestage/scene.py`

Add an import for `trace` and the convenience helpers at the top of the file:

```python
from opentelemetry import trace
from sidestage.tracing.middleware import record_error
```

Obtain a module-level tracer:

```python
tracer = trace.get_tracer("sidestage.scene")
```

Wrap the body of `_process_event` in a span, **after** the `isinstance` check so non-ChatMessage events produce no span:

```python
async def _process_event(self, event: Event) -> None:
    if not isinstance(event, ChatMessage):
        return
    with tracer.start_as_current_span("scene.process_event") as span:
        span.set_attribute("sidestage.scene.id", self.id)
        span.set_attribute("sidestage.event.id", event.id)
        span.set_attribute("sidestage.event.type", type(event).__name__)
        span.set_attribute("sidestage.actor.id", event.actor_id)
        try:
            # (a) Persist
            self.data.messages.append(event)
            self.storage.update_scene(self.data)

            if self.graph_client is not None:
                # ... existing graph persistence ...

            # (b) Broadcast to websockets
            if self._broadcast_fn:
                await self._broadcast_fn(event)

            # (c) For user-originated events: send to all NPCs
            if event.actor_id == "user":
                await self._dispatch_to_npcs(event)
        except Exception as exc:
            record_error(span, exc)
            raise
```

The existing logic is unchanged; only the span wrapping is added.

### 4.2 Instrument SceneLogic._dispatch_to_npcs

**File:** `/home/harald/src/sidestage/src/sidestage/scene.py`

Wrap the dispatch loop in a span:

```python
async def _dispatch_to_npcs(self, event: ChatMessage) -> None:
    with tracer.start_as_current_span("scene.dispatch_to_npcs") as span:
        span.set_attribute("sidestage.npc_count", len(self.characters))
        for char_logic in self.characters.values():
            if char_logic.actor is not None:
                try:
                    await char_logic.actor.on_event(event)
                except Exception:
                    logger.exception(
                        "Error dispatching to NPC %s", char_logic.data.name
                    )
```

Because `on_event` creates its own child span (see 4.3), the per-NPC spans will naturally appear as children of `scene.dispatch_to_npcs`.

### 4.3 Instrument AgentActor.on_event

**File:** `/home/harald/src/sidestage/src/sidestage/character.py`

Add imports:

```python
from opentelemetry import trace
from sidestage.tracing.middleware import record_error
```

Module-level tracer:

```python
tracer = trace.get_tracer("sidestage.character")
```

Wrap `on_event`:

```python
async def on_event(self, event: Event) -> None:
    if not isinstance(event, ChatMessage):
        return

    with tracer.start_as_current_span("agent.on_event") as span:
        span.set_attribute("sidestage.character.id", self.character.id)
        span.set_attribute("sidestage.character.name", self.character.name)
        try:
            logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")

            if not self.agent:
                return

            # ... existing context assembly and arun logic ...

            response = await self.agent.arun(event.message, context=context_text)

            if response.content:
                reply = self.scene_logic.create_message(
                    actor_id=self.actor_id,
                    text=response.content,
                    character_id=self.character.id
                )
                await self.scene_logic.queue.put(reply)
        except Exception as exc:
            record_error(span, exc)
            logger.exception("Error in on_event for %s", self.character.name)
```

Note: The existing `on_event` does not have a try/except. Adding one with `record_error` ensures error spans are captured. The exception should be re-raised or handled consistently with the existing pattern (the caller `_dispatch_to_npcs` already has a catch-all).

### 4.4 Instrument assemble_context

**File:** `/home/harald/src/sidestage/src/sidestage/memory/context.py`

Add imports:

```python
from opentelemetry import trace
```

Module-level tracer:

```python
tracer = trace.get_tracer("sidestage.memory.context")
```

Wrap the `assemble_context` function body:

```python
async def assemble_context(
    client: GraphClient,
    owner_id: str,
    scene_id: str,
    present_character_ids: list[str],
    recent_messages: list[ChatMessage],
    context_limit: int,
    chat_history_ratio: float = DEFAULT_CHAT_HISTORY_RATIO,
    character_names: dict[str, str] | None = None,
) -> ContextResult:
    """Assemble memory context for an agent prompt."""
    with tracer.start_as_current_span("memory.assemble_context") as span:
        span.set_attribute("sidestage.owner_id", owner_id)
        span.set_attribute("sidestage.scene.id", scene_id)

        # ... existing logic (fetch memories, touch, format, trim) ...

        span.set_attribute("memory.token_estimate", token_estimate)
        return ContextResult(
            memory_text=memory_text,
            chat_text=chat_text,
            token_estimate=token_estimate,
        )
```

### 4.5 Instrument LiteLLMAgent.arun

**File:** `/home/harald/src/sidestage/src/sidestage/agent.py`

This is the most complex instrumentation point. Add imports:

```python
from opentelemetry import trace
from sidestage.tracing.middleware import add_trace_event, record_error
```

Module-level tracer:

```python
tracer = trace.get_tracer("sidestage.agent")
```

Wrap the `arun` method with a parent `agent.run` span, then create child `llm.completion` spans for each LLM call and `tool.execute` spans for each tool call:

```python
async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse:
    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("agent.name", self.name)
        span.set_attribute("gen_ai.request.model", self.model)

        messages = []
        if self.instructions:
            system_msg = "\n".join(self.instructions)
            messages.append({"role": "system", "content": system_msg})
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": message})

        max_turns = 5
        current_turn = 0
        total_input_tokens = 0
        total_output_tokens = 0
        final_content = ""

        while current_turn < max_turns:
            current_turn += 1

            with tracer.start_as_current_span("llm.completion") as llm_span:
                llm_span.set_attribute("agent.turn", current_turn)

                # Add prompt events (respects capture_prompts config)
                add_trace_event("gen_ai.prompt", {
                    "role": "system",
                    "content": system_msg if self.instructions else "",
                })
                add_trace_event("gen_ai.prompt", {
                    "role": "user",
                    "content": message,
                })

                try:
                    response = await litellm.acompletion(
                        model=self.model,
                        api_base=self.api_base,
                        api_key=self.api_key,
                        messages=messages,
                        tools=self.tool_schemas if self.tool_schemas else None,
                        tool_choice="auto" if self.tool_schemas else None,
                        stream=False,
                    )
                except Exception as exc:
                    record_error(llm_span, exc)
                    # ... existing error handling (return friendly message) ...

                resp_obj = cast(Any, response)
                msg = resp_obj.choices[0].message

                # Add completion event
                add_trace_event("gen_ai.completion", {
                    "content": msg.content or "",
                })

                # Extract token usage (may be None for some providers)
                usage = getattr(resp_obj, 'usage', None)
                if usage:
                    input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
                    output_tokens = getattr(usage, 'completion_tokens', 0) or 0
                    llm_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                    llm_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens

                llm_span.set_attribute("gen_ai.response.finish_reasons",
                    [choice.finish_reason for choice in resp_obj.choices])

                messages.append(msg)

                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        with tracer.start_as_current_span("tool.execute") as tool_span:
                            tool_span.set_attribute("tool.name", tool_call.function.name)
                            add_trace_event("tool.arguments", {
                                "args": tool_call.function.arguments,
                            })
                            try:
                                # ... existing tool execution logic ...
                                add_trace_event("tool.result", {"result": str(result)})
                            except Exception as exc:
                                record_error(tool_span, exc)
                                # ... existing error handling ...
                    continue

                final_content = msg.content
                break

        span.set_attribute("agent.turn_count", current_turn)
        span.set_attribute("agent.total_input_tokens", total_input_tokens)
        span.set_attribute("agent.total_output_tokens", total_output_tokens)

        return AgentResponse(content=final_content or "")
```

Key notes:
- The existing `arun` code does not extract `resp_obj.usage`. This must be added with None-safety since some local LLM servers do not return usage statistics.
- `add_trace_event` from `tracing/middleware.py` respects `capture_prompts` and `capture_tool_args` config flags and truncates long strings per `max_attribute_length`.
- The existing error-handling pattern (returning friendly error messages instead of raising) is preserved. The span gets `record_error` called before the early return.

### 4.6 Instrument Memory Tool Operations

**File:** `/home/harald/src/sidestage/src/sidestage/memory/tools.py`

Add imports:

```python
from opentelemetry import trace
from sidestage.tracing.middleware import add_trace_event, record_error
```

Module-level tracer:

```python
tracer = trace.get_tracer("sidestage.memory.tools")
```

Wrap each memory tool method in a span. Example for `MemoryTools.update_scene_memory`:

```python
async def update_scene_memory(self, content: str, gametime: int | None = None) -> str:
    """Update your memory of the current scene. ..."""
    with tracer.start_as_current_span("memory.update_scene_memory") as span:
        span.set_attribute("sidestage.owner_id", self.owner_id)
        span.set_attribute("sidestage.scene.id", self.scene_id)
        add_trace_event("memory.content", {"content": content})
        try:
            memory = await upsert_scene_memory(
                self.client, self.owner_id, self.scene_id, content, gametime=gametime,
            )
            self._fire_embed(memory.id, content)
            return json.dumps({"status": "ok", "memory_id": memory.id})
        except Exception as exc:
            record_error(span, exc)
            logger.warning("update_scene_memory failed: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)})
```

Apply the same pattern to all methods in both `MemoryTools` and `DmMemoryTools`:

| Class | Method | Span Name |
|-------|--------|-----------|
| `MemoryTools` | `update_scene_memory` | `memory.update_scene_memory` |
| `MemoryTools` | `update_character_memory` | `memory.update_character_memory` |
| `DmMemoryTools` | `update_common_memory` | `memory.update_common_memory` |
| `DmMemoryTools` | `update_canonical_memory` | `memory.update_canonical_memory` |
| `DmMemoryTools` | `add_world_fact` | `memory.add_world_fact` |

Each method sets `sidestage.owner_id` (or `dm_actor_id` for DM tools) and the relevant scene/entity ID attribute. The `add_trace_event("memory.content", ...)` call respects the `capture_memory_content` config flag.

### 4.7 Instrument Background Embedding with Context Propagation

**File:** `/home/harald/src/sidestage/src/sidestage/memory/tools.py`

The `_fire_embed` method on both `MemoryTools` and `DmMemoryTools` currently creates a bare `asyncio.create_task`. The OpenTelemetry context (which carries the current trace and span) is NOT automatically propagated to background tasks. The fix captures the current context and re-attaches it inside the background task.

Add imports:

```python
from opentelemetry import context
```

Update both `_fire_embed` implementations:

```python
def _fire_embed(self, memory_id: str, content: str) -> None:
    """Fire background embedding task with trace context propagation."""
    if self.embed_config is not None:
        ctx = context.get_current()  # Capture current OTel context
        async def _embed_with_context():
            token = context.attach(ctx)  # Restore context in background task
            try:
                with tracer.start_as_current_span("memory.embed") as span:
                    span.set_attribute("memory.id", memory_id)
                    await embed_and_update(
                        self.client, self.embed_config, memory_id, content, self.health
                    )
            except Exception as exc:
                logger.debug("Background embed tracing error: %s", exc)
            finally:
                context.detach(token)
        try:
            asyncio.create_task(_embed_with_context())
        except RuntimeError:
            logger.debug("No event loop for background embed task")
```

This ensures the `memory.embed` span appears as a child of the calling span (e.g., `memory.update_scene_memory`) within the same trace.

### 4.8 Trace Lookup via Event ID

No code changes to `ChatMessage` or broadcast payloads are needed. The trace-to-message association works through attributes:

1. The root span `scene.process_event` sets `span.set_attribute("sidestage.event.id", event.id)`
2. The `SQLiteTraceExporter` (from section-03) extracts `event_id` from span attributes and stores it in the `traces` table
3. The frontend can look up any message's trace via `GET /v1/traces?event_id=<message_id>` (section-05)

This avoids polluting the data model or broadcast payload with trace metadata.

### 4.9 Instrument Entity Import Tracing

**File:** `/home/harald/src/sidestage/src/sidestage/campaign.py`

Add imports:

```python
from opentelemetry import trace
```

Module-level tracer:

```python
tracer = trace.get_tracer("sidestage.campaign")
```

Wrap `reload_defaults`:

```python
def reload_defaults(self) -> None:
    """Load default entities from data/campaign_defaults/markdown/."""
    with tracer.start_as_current_span("campaign.reload_defaults") as span:
        span.set_attribute("sidestage.scene.id", "campaign_planning")

        logger.info("Reloading default content from data directory...")
        project_root = Path(__file__).parent.parent.parent
        defaults_dir = project_root / "data" / "campaign_defaults" / "markdown"

        if not defaults_dir.exists():
            logger.warning(f"Defaults directory not found at {defaults_dir}. Skipping.")
            span.set_attribute("entities.loaded_count", 0)
            return

        result = parse_directory(defaults_dir)

        for issue in result.errors:
            logger.error(f"Error loading default: {issue.message} ({issue.file_path})")
        for issue in result.warnings:
            logger.warning(f"Warning loading default: {issue.message} ({issue.file_path})")

        count = 0
        for entity in result.entities:
            try:
                # ... existing entity type dispatch ...
                count += 1
                logger.info(f"Loaded default {type(entity).__name__}: {entity.name} ({entity.id})")
            except Exception as e:
                logger.error(f"Error loading default entity {entity.id}: {e}")

        span.set_attribute("entities.loaded_count", count)
```

Note: `reload_defaults` is a synchronous method. The `tracer.start_as_current_span` context manager works with synchronous code as well -- it does not require an async function.

---

## Error Handling Patterns

All instrumentation follows a consistent error-handling pattern:

1. The span wraps the existing try/except blocks (or adds one if missing).
2. On exception, `record_error(span, exc)` is called, which sets `span.set_status(StatusCode.ERROR, str(exc))` and calls `span.record_exception(exc)`.
3. The exception is then either re-raised or handled according to the existing code pattern.
4. Tracing code never prevents the application from functioning -- if tracing itself fails (e.g., import error before init), the spans are simply no-ops via the `FilteringSpanProcessor` disabled state.

## Files Modified Summary

| File | Changes |
|------|---------|
| `/home/harald/src/sidestage/src/sidestage/scene.py` | Add tracer, wrap `_process_event` and `_dispatch_to_npcs` |
| `/home/harald/src/sidestage/src/sidestage/character.py` | Add tracer, wrap `AgentActor.on_event` |
| `/home/harald/src/sidestage/src/sidestage/memory/context.py` | Add tracer, wrap `assemble_context` |
| `/home/harald/src/sidestage/src/sidestage/agent.py` | Add tracer, wrap `arun` with `agent.run`, `llm.completion`, `tool.execute` spans, add token usage extraction |
| `/home/harald/src/sidestage/src/sidestage/memory/tools.py` | Add tracer, wrap all memory tool methods, update `_fire_embed` for context propagation |
| `/home/harald/src/sidestage/src/sidestage/campaign.py` | Add tracer, wrap `reload_defaults` |

## Files Created Summary

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/tests/unit/test_tracing_instrumentation.py` | All unit tests for instrumentation points |