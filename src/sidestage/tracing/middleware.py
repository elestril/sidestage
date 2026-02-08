"""Convenience decorators and helpers for tracing instrumentation."""

from __future__ import annotations

import functools
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from sidestage import config as sidestage_config


def trace_span(name: str, attributes: dict[str, Any] | None = None):
    """Decorator that wraps an async function in a span."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("sidestage")
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    record_error(span, exc)
                    raise
        return wrapper
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

    cfg = sidestage_config.get().tracing

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


def record_error(span, exception: Exception) -> None:
    """Set span status to ERROR and record the exception."""
    span.set_status(StatusCode.ERROR, str(exception))
    span.record_exception(exception)
