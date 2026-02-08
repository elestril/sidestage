"""TracerProvider setup, FilteringSpanProcessor, and lifecycle functions."""

from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

if TYPE_CHECKING:
    from sidestage.config import TraceConfig

logger = logging.getLogger(__name__)

_provider: TracerProvider | None = None
_filtering_processors: list["FilteringSpanProcessor"] = []
_init_error: str | None = None
_otlp_endpoint: str | None = None


class FilteringSpanProcessor(SpanProcessor):
    """SpanProcessor wrapper that can be toggled on/off at runtime."""

    def __init__(self, wrapped: SpanProcessor, enabled: bool = True):
        self._wrapped = wrapped
        self.enabled = enabled

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        if self.enabled:
            self._wrapped.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        if self.enabled:
            self._wrapped.on_end(span)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def check_otlp_endpoint(endpoint: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    """Check whether the OTLP endpoint is reachable via TCP connect.

    Args:
        endpoint: Base OTLP HTTP endpoint URL (e.g. ``http://localhost:4318``)
        timeout: Connection timeout in seconds

    Returns:
        ``(True, None)`` if reachable, ``(False, error_message)`` otherwise.
    """
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except OSError as exc:
        msg = f"OTLP endpoint unreachable at {endpoint}: {exc}"
        return False, msg


def init_tracing(
    config: "TraceConfig",
    campaign_name: str,
) -> TracerProvider:
    """Set up TracerProvider with OTLP exporter.

    If ``config.enabled`` is True but the OTLP endpoint is unreachable,
    the provider is created with tracing *disabled* and the error is
    stored (retrievable via :func:`get_tracing_error`).

    Args:
        config: TraceConfig instance
        campaign_name: Used in the OTel Resource for service.name

    Returns:
        The configured TracerProvider
    """
    global _provider, _filtering_processors, _init_error, _otlp_endpoint

    # Shutdown previous provider if re-initializing
    if _provider is not None:
        shutdown_tracing()

    _otlp_endpoint = config.otlp_endpoint
    _init_error = None

    enabled = config.enabled
    if enabled:
        reachable, err = check_otlp_endpoint(config.otlp_endpoint)
        if not reachable:
            _init_error = err
            enabled = False
            logger.error("Tracing disabled: %s", err)

    resource = Resource.create({
        "service.name": "sidestage",
        "campaign.name": campaign_name,
    })

    provider = TracerProvider(resource=resource)
    _filtering_processors = []

    otlp_exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint + "/v1/traces")
    batch_processor = BatchSpanProcessor(otlp_exporter)
    filtering = FilteringSpanProcessor(batch_processor, enabled=enabled)
    provider.add_span_processor(filtering)
    _filtering_processors.append(filtering)

    trace.set_tracer_provider(provider)
    _provider = provider

    logger.info(
        "Tracing initialized (enabled=%s, campaign=%s, endpoint=%s)",
        enabled,
        campaign_name,
        config.otlp_endpoint,
    )

    return provider


def get_tracing_enabled() -> bool:
    """Return current tracing enabled state."""
    if not _filtering_processors:
        return False
    return _filtering_processors[0].enabled


def get_tracing_error() -> str | None:
    """Return the current tracing error, or ``None`` if tracing is healthy."""
    return _init_error


def toggle_tracing(enabled: bool) -> tuple[bool, str | None]:
    """Flip tracing on/off at runtime.

    When enabling, validates the OTLP endpoint is reachable first.

    Returns:
        ``(new_enabled_state, error_message_or_none)``
    """
    global _init_error

    if not _filtering_processors:
        logger.warning("toggle_tracing called before init_tracing")
        return False, "Tracing not initialized"

    if enabled and _otlp_endpoint:
        reachable, err = check_otlp_endpoint(_otlp_endpoint)
        if not reachable:
            logger.error("Cannot enable tracing: %s", err)
            return False, err

    for fp in _filtering_processors:
        fp.enabled = enabled
    _init_error = None
    logger.info("Tracing toggled: enabled=%s", enabled)
    return enabled, None


def shutdown_tracing() -> None:
    """Flush pending spans and shut down the provider."""
    global _provider, _filtering_processors, _init_error, _otlp_endpoint

    if _provider is not None:
        _provider.shutdown()
        _provider = None
        _filtering_processors = []
        _init_error = None
        _otlp_endpoint = None
        logger.info("Tracing shutdown complete")
