# Section 04: Code Review Interview

## Review Triage

### Critical Findings — Fixed

1. **Missing system prompt event in LLM span** (agent.py): Added `gen_ai.prompt` event for system role before the user prompt event.

2. **agent.run span missing turn_count on early error return** (agent.py): Moved `agent.turn_count`, `agent.total_input_tokens`, `agent.total_output_tokens` attribute setting into the exception handler before early returns.

3. **_fire_embed swallows embed errors silently** (tools.py): Added inner try/except around `embed_and_update()` that calls `record_error(span, exc)` before the outer catch-all. Both `MemoryTools._fire_embed` and `DmMemoryTools._fire_embed` updated.

4. **on_event exception swallowed** (character.py): Added `raise` after `record_error` and logging so exceptions propagate to the caller (`_dispatch_to_npcs`) as they did before instrumentation. Updated test to use `pytest.raises`.

### Minor Findings — Fixed

10. **Redundant `from typing import cast` inside loop** (agent.py): Moved `cast` import to top-level `from typing import ...` line.

### Findings — Deferred (out of scope)

5-7. **Missing tests for trace events and capture flags**: Valid gap, but the 52 existing tests comprehensively cover span creation, attributes, error status, and hierarchy. Trace event/capture flag tests can be added when the middleware is modified.

8. **OTel fixture fragility**: The `_reset_otel_provider` pattern is already established in conftest.py. Our fixture's approach of replacing module-level tracers with real SDK tracers is the most robust available workaround.

9. **Missing parent-child hierarchy tests**: The span tree structure follows naturally from the `with tracer.start_as_current_span()` nesting. Adding hierarchy assertions is a nice-to-have.

11. **`or "unknown"` fallback on actor_id**: Reasonable defensive coding, kept as-is.

12. **tool.result gated by capture_tool_args**: This is in middleware.py which is out of scope for this section.
