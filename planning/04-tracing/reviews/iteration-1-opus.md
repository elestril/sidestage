# Opus Review

**Model:** claude-opus-4-6
**Generated:** 2026-02-08T05:25:00Z

---

# Implementation Plan Review: Tracing Support for Sidestage

## Overall Assessment

The plan is well-structured and demonstrates solid understanding of OpenTelemetry concepts and the Sidestage codebase. The architecture is appropriate for the project's scale. However, there are several significant issues ranging from architectural mismatches with the actual code to potential runtime failures that need to be addressed before implementation.

---

## 1. Critical: Storage Layer Mismatch -- SQLAlchemy Does Not Exist Here

**Section 3.6** states: "Use the existing SQLAlchemy engine from `Storage` (passed at init). Define the tables with SQLAlchemy Core (Table objects), not ORM models, to keep it lightweight."

This is factually wrong. The `Storage` class uses raw `sqlite3` connections directly -- there is no SQLAlchemy engine, no ORM, no Core tables. Every method does `sqlite3.connect(self.db_path)` and runs raw SQL.

While `sqlalchemy` is in `pyproject.toml` (presumably for FalkorDB or future use), the actual `Storage` class has zero SQLAlchemy usage. The plan should either:
- Use raw `sqlite3` to be consistent with the existing pattern (recommended for simplicity), or
- Explicitly acknowledge introducing SQLAlchemy Core for the tracing tables as a new pattern.

Additionally, the plan says to "pass the existing SQLAlchemy engine at init," but no such engine exists to pass. The SQLiteTraceExporter will need to receive a `db_path: Path` and manage its own connection.

---

## 2. Critical: `toggle_tracing()` Cannot Safely Swap Global TracerProvider

**Section 3.3** proposes: "`toggle_tracing(enabled)` swaps the global TracerProvider at runtime."

OpenTelemetry's `trace.set_tracer_provider()` is designed to be called once during initialization. The API documentation explicitly warns that setting it multiple times is not supported by all implementations. In the Python SDK, calling `set_tracer_provider()` after tracers have already been obtained via `trace.get_tracer()` will **not** update those existing tracer references -- they are bound to the original provider.

**Recommendation:** Instead of swapping providers, use a custom `SpanProcessor` that checks an `enabled` flag. When disabled, the processor's `on_end()` simply discards the span data. This avoids the provider-swap problem entirely while still achieving zero-useful-work when tracing is off. Alternatively, wrap the tracer access in a function that always calls `trace.get_tracer()` at invocation time rather than module-level, though this is less idiomatic.

---

## 3. Critical: NPC Reply Creates a Second Trace -- Plan Does Not Address This

The event processing flow is:

1. User message arrives at `_process_event` -> root span created (Trace A)
2. `_dispatch_to_npcs` is called within this span -> NPC generates reply
3. NPC reply is put back on the queue via `scene_logic.queue.put(reply)`
4. The EventQueue worker picks up the reply and calls `_process_event` again -> **a new root span is created (Trace B)**

This means a single user message generates at least two separate traces: one for the user message processing (which includes NPC agent execution) and one for each NPC reply message processing (persist + broadcast).

**Recommendation:** Either document this as intentional, use OTel span links, or propagate trace context onto reply messages.

---

## 4. Significant: `_process_event` Filters Non-ChatMessage Events

The root span should be placed **after** the `isinstance(event, ChatMessage)` check to avoid creating empty traces for non-ChatMessage events.

---

## 5. Significant: `LiteLLMAgent.arun` Does Not Expose Token Usage

The current code accesses `resp_obj.choices[0].message` but never accesses `resp_obj.usage`. The plan should note that accessing usage requires adding this extraction, and that `usage` may be `None` for some providers.

---

## 6. Significant: `SimpleSpanProcessor` Blocks the Event Loop

`SimpleSpanProcessor` calls `export()` synchronously in `on_end()`. The `SQLiteTraceExporter` performs SQLite INSERT operations in `export()`. Since this runs in the async event loop thread, synchronous SQLite I/O will block the event loop.

**Recommendation:** Use `BatchSpanProcessor` for the SQLite exporter only, or run SQLite writes in a thread pool.

---

## 7. Moderate: WebSocket Broadcast Has No Subscription Filtering

The existing `SyncManager` broadcasts to all connected clients. The plan says to filter by subscription but doesn't detail the changes needed.

**Recommendation:** Accept that trace messages broadcast to all clients and filter client-side.

---

## 8. Moderate: `trace_id` on ChatMessage Is a Schema-Breaking Change

Adding `trace_id` to the persisted model means every persisted message includes it. Consider including `trace_id` only in the WebSocket broadcast payload and HTTP response, not in the persisted data model.

---

## 9. Moderate: `trace_started` Message Missing from Plan

The spec lists `trace_started` as a WebSocket message type but the plan omits it.

---

## 10. Moderate: DmMemoryTools Has the Same _fire_embed Pattern

`DmMemoryTools` has an identical `_fire_embed` method that should also be instrumented.

---

## 11. Moderate: No Trace Cleanup / Retention Policy for SQLite

Add a retention policy -- either time-based or count-based -- configurable in TraceConfig.

---

## 12. Moderate: JavaScript Number Precision for Nanosecond Timestamps

Nanosecond timestamps exceed `Number.MAX_SAFE_INTEGER`. Convert to millisecond timestamps on the backend before sending to the frontend.

---

## 13. Missing: Error Span Status

The plan does not discuss setting span status to ERROR when exceptions occur. OTel best practice: `span.set_status(StatusCode.ERROR)` and `span.record_exception(exception)`.

---

## 14. Missing: TracerProvider Shutdown on Server Teardown

`provider.shutdown()` should be called during application teardown in the `_lifespan` context manager.

---

## 15. Missing: `scene_id` Optional on GET /v1/traces

Consider making `scene_id` optional to allow listing all recent traces across scenes.

---

## 16. Minor: Frontend Route vs Static File Mount Interaction

The SPA catch-all and StaticFiles mount interaction at `/sidestage/traces` should be tested.

---

## 17. Minor: Config Persistence Writes Tracing Defaults to YAML

First run after update will add `tracing:` section to config.yml. Consistent with existing behavior.

---

## 18. Minor: `trace_span` Decorator Must Be Async-Aware

The decorator should use `async def wrapper` for async functions.

---

## 19. Missing: In-Flight Background Embedding Spans on Shutdown

Background tasks via `asyncio.create_task` may be in-flight during shutdown. Need to flush pending spans.

---

## 20. Missing: `scene_id` Required on GET /v1/traces

No way to list all traces across all scenes. Consider making optional.

---

## Summary of Recommended Changes

1. **Fix Storage layer reference** -- use raw `sqlite3`, not SQLAlchemy (Critical)
2. **Redesign toggle mechanism** -- use a flag in a custom SpanProcessor instead of swapping providers (Critical)
3. **Address dual-trace problem** for user message vs. NPC reply processing (Critical)
4. **Move root span creation** after the `isinstance(event, ChatMessage)` check (Significant)
5. **Handle missing `usage` data** from LLM responses (Significant)
6. **Use `BatchSpanProcessor` for SQLite** or accept and document the blocking (Significant)
7. **Accept broadcast-to-all** for WebSocket trace messages, filter client-side (Moderate)
8. **Keep `trace_id` out of the persisted ChatMessage model** (Moderate)
9. **Add `trace_started` message or update spec** (Moderate)
10. **Instrument `DmMemoryTools._fire_embed` too** (Moderate)
11. **Add trace retention/cleanup policy** (Moderate)
12. **Convert nanosecond timestamps to milliseconds** before sending to frontend (Moderate)
13. **Add error status recording** to span instrumentation (Missing)
14. **Call `TracerProvider.shutdown()`** during application teardown (Missing)
15. **Consider making `scene_id` optional** on `GET /v1/traces` (Missing)
