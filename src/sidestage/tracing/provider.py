"""TracerProvider setup, FilteringSpanProcessor, and lifecycle functions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    SpanProcessor,
    SimpleSpanProcessor,
    BatchSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.context import Context

if TYPE_CHECKING:
    from sidestage.config import TraceConfig

logger = logging.getLogger(__name__)

_provider: TracerProvider | None = None
_filtering_processors: list["FilteringSpanProcessor"] = []
_in_memory_exporter: SpanExporter | None = None


class FilteringSpanProcessor(SpanProcessor):
    """SpanProcessor wrapper that can be toggled on/off at runtime."""

    def __init__(self, wrapped: SpanProcessor, enabled: bool = True):
        self._wrapped = wrapped
        self.enabled = enabled

    def on_start(self, span: ReadableSpan, parent_context: Context | None = None) -> None:
        if self.enabled:
            self._wrapped.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        if self.enabled:
            self._wrapped.on_end(span)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def init_tracing(
    config: "TraceConfig",
    campaign_name: str,
    db_path: Path,
    *,
    in_memory_exporter: SpanExporter | None = None,
    sqlite_exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Set up TracerProvider and exporters.

    Args:
        config: TraceConfig instance
        campaign_name: Used in the OTel Resource for service.name
        db_path: Path to the SQLite database for trace persistence
        in_memory_exporter: Optional exporter for in-memory traces (default: created from Section 03)
        sqlite_exporter: Optional exporter for SQLite persistence (default: created from Section 03)

    Returns:
        The configured TracerProvider
    """
    global _provider, _filtering_processors, _in_memory_exporter

    # Shutdown previous provider if re-initializing
    if _provider is not None:
        shutdown_tracing()

    resource = Resource.create({
        "service.name": "sidestage",
        "campaign.name": campaign_name,
    })

    provider = TracerProvider(resource=resource)
    _filtering_processors = []
    _in_memory_exporter = in_memory_exporter

    if in_memory_exporter is None and sqlite_exporter is None:
        logger.warning("No exporters provided -- all trace data will be lost")

    if in_memory_exporter is not None:
        mem_processor = SimpleSpanProcessor(in_memory_exporter)
        filtering_mem = FilteringSpanProcessor(mem_processor, enabled=config.enabled)
        provider.add_span_processor(filtering_mem)
        _filtering_processors.append(filtering_mem)

    if sqlite_exporter is not None:
        batch_processor = BatchSpanProcessor(sqlite_exporter)
        filtering_batch = FilteringSpanProcessor(batch_processor, enabled=config.enabled)
        provider.add_span_processor(filtering_batch)
        _filtering_processors.append(filtering_batch)

    trace.set_tracer_provider(provider)
    _provider = provider

    logger.info(
        "Tracing initialized (enabled=%s, campaign=%s)",
        config.enabled,
        campaign_name,
    )

    return provider


def get_in_memory_exporter() -> SpanExporter | None:
    """Return the in-memory exporter reference, or None if not initialized."""
    return _in_memory_exporter


def toggle_tracing(enabled: bool) -> bool:
    """Flip tracing on/off at runtime.

    Returns the new enabled state.
    """
    if not _filtering_processors:
        logger.warning("toggle_tracing called before init_tracing")
    for fp in _filtering_processors:
        fp.enabled = enabled
    logger.info("Tracing toggled: enabled=%s", enabled)
    return enabled


def shutdown_tracing() -> None:
    """Flush pending spans and shut down the provider."""
    global _provider, _filtering_processors

    if _provider is not None:
        _provider.shutdown()
        _provider = None
        _filtering_processors = []
        logger.info("Tracing shutdown complete")
