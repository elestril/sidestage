# `sidestage.tracing.provider`

TracerProvider setup, FilteringSpanProcessor, and lifecycle functions.

## Classes

### `FilteringSpanProcessor(SpanProcessor)`

SpanProcessor wrapper that can be toggled on/off at runtime.

#### `__init__(wrapped: SpanProcessor, enabled: bool = True)`

#### `force_flush(timeout_millis: int = 30000) -> bool`

Export all ended spans to the configured Exporter that have not yet
been exported.

Args:
    timeout_millis: The maximum amount of time to wait for spans to be
        exported.

Returns:
    False if the timeout is exceeded, True otherwise.

#### `on_end(span: ReadableSpan) -> None`

Called when a :class:`opentelemetry.trace.Span` is ended.

This method is called synchronously on the thread that ends the
span, therefore it should not block or throw an exception.

Args:
    span: The :class:`opentelemetry.trace.Span` that just ended.

#### `on_start(span: Span, parent_context: Context | None = None) -> None`

Called when a :class:`opentelemetry.trace.Span` is started.

This method is called synchronously on the thread that starts the
span, therefore it should not block or throw an exception.

Args:
    span: The :class:`opentelemetry.trace.Span` that just started.
    parent_context: The parent context of the span that just started.

#### `shutdown() -> None`

Called when a :class:`opentelemetry.sdk.trace.TracerProvider` is shutdown.

## Functions

### `check_otlp_endpoint(endpoint: str, timeout: float = 2.0) -> tuple[bool, str | None]`

Check whether the OTLP endpoint is reachable via TCP connect.

Args:
    endpoint: Base OTLP HTTP endpoint URL (e.g. ``http://localhost:4318``)
    timeout: Connection timeout in seconds

Returns:
    ``(True, None)`` if reachable, ``(False, error_message)`` otherwise.

### `get_tracing_enabled() -> bool`

Return current tracing enabled state.

### `get_tracing_error() -> str | None`

Return the current tracing error, or ``None`` if tracing is healthy.

### `init_tracing(config: 'TraceConfig', campaign_name: str) -> TracerProvider`

Set up TracerProvider with OTLP exporter.

If ``config.enabled`` is True but the OTLP endpoint is unreachable,
the provider is created with tracing *disabled* and the error is
stored (retrievable via :func:`get_tracing_error`).

Args:
    config: TraceConfig instance
    campaign_name: Used in the OTel Resource for service.name

Returns:
    The configured TracerProvider

### `shutdown_tracing() -> None`

Flush pending spans and shut down the provider.

### `toggle_tracing(enabled: bool) -> tuple[bool, str | None]`

Flip tracing on/off at runtime.

When enabling, validates the OTLP endpoint is reachable first.

Returns:
    ``(new_enabled_state, error_message_or_none)``
