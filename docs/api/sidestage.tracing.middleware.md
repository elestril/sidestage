# `sidestage.tracing.middleware`

Convenience decorators and helpers for tracing instrumentation.

## Functions

### `add_trace_event(name: str, attributes: dict[str, Any] | None = None) -> None`

Add an event to the currently active span, respecting capture flags.

Checks TraceConfig capture flags to decide whether to record the event.
Truncates string attribute values exceeding max_attribute_length.

### `current_trace_id() -> str | None`

Get the current trace_id as a hex string, or None if no active span.

### `record_error(span: trace.Span, exception: Exception) -> None`

Set span status to ERROR and record the exception.

### `stamp_span_with_request_context(span: trace.Span) -> None`

Copy ambient :class:`RequestContext` fields onto a span as attributes.

Safe to call when there is no active request context (no-op).

### `trace_span(name: str, attributes: dict[str, Any] | None = None) -> Callable[[F], F]`

Decorator that wraps an async function in a span.
