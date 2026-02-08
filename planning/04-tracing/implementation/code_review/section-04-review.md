# Section 04: Backend Instrumentation — Code Review

## Critical Issues

### 1. Missing system prompt event in LLM span (agent.py)
The plan specifies TWO `gen_ai.prompt` events per LLM turn (system + user). Implementation only emitted the user prompt event. **Fixed.**

### 2. agent.run span never gets turn_count/token attributes on early error return (agent.py)
When LLM exceptions trigger early returns, parent span summary attributes were bypassed. **Fixed.**

### 3. _fire_embed swallows ALL exceptions including embed_and_update failures (tools.py)
The broad catch-all hid legitimate embed failures behind misleading "tracing error" log. Span showed OK status for failed operations. **Fixed.**

### 4. on_event exception swallowed, not re-raised (character.py)
Behavioral change from instrumentation: `_dispatch_to_npcs` catch-all would never trigger. **Fixed.**

## Medium Issues

### 5-7. Missing tests for trace events and capture flags
No tests for `add_trace_event` conditional logic or `capture_prompts`/`capture_memory_content` flags. **Deferred.**

### 8. otel_exporter fixture mutates private OTel internals
Fragile but necessary workaround. The `_reset_otel_provider` pattern is already established in conftest.py. **Accepted.**

### 9. Missing parent-child hierarchy tests
Tests verify span existence and attributes but not the span tree structure. **Deferred.**

## Minor Issues

### 10. Redundant `from typing import cast` inside hot loop (agent.py)
**Fixed** — moved to top-level import.

### 11. `event.actor_id or "unknown"` fallback (scene.py)
Reasonable defensive coding. **Accepted.**

### 12. tool.result gated by capture_tool_args (middleware.py)
Out of scope for this section. **Deferred.**
