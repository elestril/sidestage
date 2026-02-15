"""Convenience decorators and helpers for tracing instrumentation."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar
from collections.abc import Coroutine

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from sidestage import config as sidestage_config

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Callable[[F], F]:
    """Decorator that wraps an async function in a span."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer("sidestage")
            with tracer.start_as_current_span(name) as span:
                stamp_span_with_request_context(span)
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    record_error(span, exc)
                    raise
        return wrapper  # type: ignore[return-value]
    return decorator


def current_trace_id() -> str | None:
    """Get the current trace_id as a hex string, or None if no active span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id != 0:
        return format(ctx.trace_id, '032x')
    return None


def add_trace_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the currently active span, respecting capture flags.

    Checks TraceConfig capture flags to decide whether to record the event.
    Truncates string attribute values exceeding max_attribute_length.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return

    cfg = sidestage_config.get_config().tracing

    # Check capture flags
    if name.startswith(("gen_ai.prompt", "gen_ai.completion")) and not cfg.capture_prompts:
        return
    if name.startswith("tool.") and not cfg.capture_tool_args:
        return
    if name.startswith("memory.") and not cfg.capture_memory_content:
        return

    # Truncate long string attributes
    if attributes:
        truncated = {}
        for k, v in attributes.items():
            if isinstance(v, str) and len(v) > cfg.max_attribute_length:
                truncated[k] = v[:cfg.max_attribute_length] + "[truncated]"
            else:
                truncated[k] = v
        attributes = truncated

    span.add_event(name, attributes=attributes)


def stamp_span_with_request_context(span: trace.Span) -> None:
    """Copy ambient :class:`RequestContext` fields onto a span as attributes.

    Safe to call when there is no active request context (no-op).
    """
    from sidestage.request_context import get_request_context

    if not span.is_recording():
        return
    ctx = get_request_context()
    if ctx is None:
        return
    span.set_attribute("sidestage.request_id", ctx.request_id)
    span.set_attribute("sidestage.user", ctx.user)
    span.set_attribute("sidestage.origin", ctx.origin)
    for k, v in ctx.annotations.items():
        span.set_attribute(f"sidestage.annotation.{k}", v)


def record_error(span: trace.Span, exception: Exception) -> None:
    """Set span status to ERROR and record the exception."""
    span.set_status(StatusCode.ERROR, str(exception))
    span.record_exception(exception)
