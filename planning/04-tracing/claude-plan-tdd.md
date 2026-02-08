# TDD Plan: Tracing Support for Sidestage

Testing framework: **pytest** with **pytest-anyio** for async tests. Tests go in `tests/unit/` and `tests/integration/`. Existing conventions: `conftest.py` fixtures, `_init_config(tmp_path)` for config setup, `@pytest.mark.llm` for tests requiring live LLM.

---

## 3. Tracing Module

### 3.2 TraceConfig Model

```python
# Test: TraceConfig defaults are correct (enabled=False, capture_prompts=True, etc.)
# Test: TraceConfig loads from YAML dict with overrides
# Test: SidestageConfig includes tracing section and serializes to YAML
# Test: config.yml without tracing section uses defaults (backward compatibility)
# Test: max_traces_in_memory and max_trace_age_hours validate as positive integers
```

### 3.3 TracerProvider / FilteringSpanProcessor

```python
# Test: init_tracing with enabled=True creates real TracerProvider with both processors
# Test: init_tracing with enabled=False creates TracerProvider with disabled FilteringSpanProcessor
# Test: FilteringSpanProcessor passes spans to wrapped processor when enabled=True
# Test: FilteringSpanProcessor discards spans (no-op on_end) when enabled=False
# Test: toggle_tracing flips FilteringSpanProcessor.enabled and takes effect immediately
# Test: shutdown_tracing calls provider.shutdown() without error
# Test: toggle_tracing from disabled to enabled starts capturing new spans
# Test: toggle_tracing from enabled to disabled stops capturing (in-flight spans may complete)
```

### 3.5 InMemoryTraceExporter

```python
# Test: export single span, retrieve by trace_id
# Test: export multiple spans for same trace, all returned together
# Test: ring buffer evicts oldest trace when max_traces_in_memory exceeded
# Test: get_traces_for_scene returns only traces with matching scene_id
# Test: get_traces returns all traces ordered by time
# Test: thread safety - concurrent export and get_trace calls don't crash
# Test: callback fires on each export (mock callback, verify called with span data)
# Test: span serialization produces correct dict format (ms timestamps, all fields)
# Test: nanosecond-to-millisecond timestamp conversion is accurate
```

### 3.6 SQLiteTraceExporter

```python
# Test: export creates traces and spans tables if they don't exist
# Test: export single span creates trace summary row and span row
# Test: export multiple spans for same trace increments span_count
# Test: query traces by scene_id returns correct results
# Test: query traces by event_id returns correct results
# Test: query all traces (no filter) returns recent traces
# Test: retention cleanup deletes traces older than max_trace_age_hours
# Test: retention cleanup enforces max_traces_stored limit
# Test: reload_into_memory loads recent traces into InMemoryTraceExporter
# Test: export handles sqlite3 errors gracefully (logs, doesn't raise)
# Test: concurrent exports don't corrupt data (serialized via lock or WAL mode)
```

### 3.7 Convenience Helpers

```python
# Test: trace_span decorator creates a span around an async function
# Test: trace_span decorator preserves function name and signature (functools.wraps)
# Test: current_trace_id returns hex string when inside a span
# Test: current_trace_id returns None when no active span
# Test: add_trace_event adds event to current span with attributes
# Test: add_trace_event truncates strings exceeding max_attribute_length
# Test: add_trace_event respects capture_prompts=False (skips gen_ai.prompt events)
# Test: add_trace_event respects capture_tool_args=False (skips tool argument events)
# Test: add_trace_event respects capture_memory_content=False (skips memory content events)
# Test: record_error sets span status to ERROR and records exception
```

## 4. Instrumentation Points

### 4.1 SceneLogic._process_event

```python
# Test: processing a ChatMessage creates a root span named "scene.process_event"
# Test: root span has attributes: scene.id, event.id, event.type, actor.id
# Test: processing a non-ChatMessage event does NOT create a span (isinstance check)
# Test: exception during processing sets span status to ERROR
# Test: root span contains child spans for persist, broadcast, dispatch
```

### 4.2 SceneLogic._dispatch_to_npcs

```python
# Test: dispatch creates span named "scene.dispatch_to_npcs"
# Test: span has npc_count attribute matching number of characters
# Test: per-NPC on_event spans appear as children of dispatch span
```

### 4.3 AgentActor.on_event

```python
# Test: on_event creates span named "agent.on_event"
# Test: span has character.id and character.name attributes
# Test: exception during on_event sets span status to ERROR
# Test: child spans (assemble_context, agent.run) are nested correctly
```

### 4.4 assemble_context

```python
# Test: assemble_context creates span named "memory.assemble_context"
# Test: span has owner_id, scene.id, and token_estimate attributes
```

### 4.5 LiteLLMAgent.arun

```python
# Test: arun creates parent span "agent.run" with model attribute
# Test: each LLM call creates child span "llm.completion" with turn number
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

### 4.6 Memory Tool Operations

```python
# Test: MemoryTools.update_scene_memory creates span "memory.update_scene_memory"
# Test: MemoryTools.update_character_memory creates span "memory.update_character_memory"
# Test: DmMemoryTools.update_common_memory creates span "memory.update_common_memory"
# Test: DmMemoryTools.update_canonical_memory creates span "memory.update_canonical_memory"
# Test: DmMemoryTools.add_world_fact creates span "memory.add_world_fact"
# Test: memory content is added as event when capture_memory_content=True
# Test: memory content is NOT added when capture_memory_content=False
# Test: exception sets span status to ERROR
```

### 4.7 Background Embedding

```python
# Test: _fire_embed propagates trace context to background task
# Test: background embedding span "memory.embed" appears under parent trace
# Test: embedding span has memory.id attribute
# Test: both MemoryTools and DmMemoryTools _fire_embed are instrumented
# Test: RuntimeError from missing event loop is handled gracefully
```

### 4.9 Entity Import Tracing

```python
# Test: reload_defaults creates span "campaign.reload_defaults"
# Test: span has scene.id attribute set to "campaign_planning"
# Test: span has entities.loaded_count attribute
```

## 5. API Endpoints

```python
# Test: GET /v1/traces returns list of trace summaries
# Test: GET /v1/traces?scene_id=X filters by scene
# Test: GET /v1/traces?event_id=X returns trace for specific event
# Test: GET /v1/traces with no filters returns recent traces across all scenes
# Test: GET /v1/traces respects limit and offset params
# Test: GET /v1/traces/{trace_id} returns full trace with all spans
# Test: GET /v1/traces/{trace_id} for nonexistent trace returns 404
# Test: POST /v1/tracing/toggle with enabled=true enables tracing
# Test: POST /v1/tracing/toggle with enabled=false disables tracing
# Test: GET /v1/tracing/status returns current enabled state and config
# Test: GET /v1/tracing/status includes trace_count
```

## 5.2 WebSocket Trace Messages

```python
# Test: trace_started message sent when root span starts (span with no parent)
# Test: span_completed message sent when any span finishes
# Test: trace_completed message sent when root span finishes
# Test: WebSocket messages include correct payload format
# Test: messages are broadcast to all connected clients
```

## 6. Frontend: Trace Viewer Page

### 6.3 TraceTimeline

```typescript
// Test: builds correct tree structure from flat span list
// Test: spans with no parent are treated as roots
// Test: orphan spans (parent not in list) are treated as roots
// Test: DFS flattening produces correct depth values
// Test: duration bars have correct left offset and width proportional to trace duration
// Test: color coding matches span name patterns (llm=blue, tool=green, memory=orange)
// Test: error spans have red styling
// Test: expand/collapse toggle hides/shows child spans
// Test: clicking a span selects it and shows SpanDetail
```

### 6.4 SpanDetail

```typescript
// Test: renders all attributes as key-value table
// Test: renders events in chronological order
// Test: gen_ai.prompt events use PromptViewer component
// Test: PromptViewer is collapsed by default
// Test: PromptViewer expands on click to show full content
// Test: error span shows exception details prominently
```

### 6.5 Real-time Updates

```typescript
// Test: trace_started adds new entry to trace list with "running" indicator
// Test: span_completed updates span count and duration for existing trace
// Test: span_completed appends span to currently-viewed trace waterfall
// Test: trace_completed removes "running" indicator and shows final duration
// Test: messages for different scene_id are filtered out
```

## 7. Frontend: Chat Debug Mode

```typescript
// Test: debug toggle switch is rendered in ChatWidget header
// Test: toggling debug mode updates AppContext debugMode state
// Test: when debugMode=true, trace icon appears on messages
// Test: when debugMode=false, no trace icons shown
// Test: clicking trace icon navigates to /sidestage/traces/<sceneId>/<traceId>
// Test: trace icon calls GET /v1/traces?event_id=<messageId> to resolve traceId
// Test: messages with no associated trace show no icon even in debug mode
```

## Integration Tests

```python
# Test: full event flow - send chat, verify complete trace hierarchy
#   Root: scene.process_event
#     -> scene.dispatch_to_npcs
#       -> agent.on_event (per NPC)
#         -> memory.assemble_context
#         -> agent.run
#           -> llm.completion (per turn)
#             -> tool.execute (if tools called)
#           -> memory.embed (background, linked to parent)
# Test: NPC reply creates separate lightweight trace (persist + broadcast only)
# Test: NPC reply trace has origin_trace_id attribute linking to user message trace
# Test: traces are persisted to SQLite and survive exporter restart
# Test: traces load from SQLite into in-memory buffer on init
# Test: disabling tracing via toggle stops new traces from being captured
# Test: re-enabling tracing via toggle resumes trace capture
# Test: WebSocket clients receive trace events in real time during chat
# Test: entity import creates trace attributed to campaign_planning scene
```
