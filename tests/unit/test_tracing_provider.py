"""Tests for tracing provider setup, FilteringSpanProcessor, and lifecycle functions."""

import pytest
from unittest.mock import MagicMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor

from sidestage.config import TraceConfig
from sidestage.tracing.provider import (
    FilteringSpanProcessor,
    init_tracing,
    toggle_tracing,
    shutdown_tracing,
)
from sidestage.tracing import provider as provider_module


class _StubExporter(SpanExporter):
    """Stub exporter that records exported spans."""

    def __init__(self):
        self.spans: list = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


class TestFilteringSpanProcessor:
    """Tests for the FilteringSpanProcessor wrapper."""

    def test_passes_spans_when_enabled(self):
        """When enabled, on_start and on_end delegate to the wrapped processor."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=True)
        span = MagicMock()
        fp.on_start(span, None)
        fp.on_end(span)
        inner.on_start.assert_called_once_with(span, None)
        inner.on_end.assert_called_once_with(span)

    def test_discards_spans_when_disabled(self):
        """When disabled, on_start and on_end are no-ops -- wrapped processor never called."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=False)
        span = MagicMock()
        fp.on_start(span, None)
        fp.on_end(span)
        inner.on_start.assert_not_called()
        inner.on_end.assert_not_called()

    def test_toggle_takes_effect_immediately(self):
        """Flipping .enabled changes behavior on the very next span."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=False)
        span = MagicMock()
        fp.on_end(span)
        inner.on_end.assert_not_called()

        fp.enabled = True
        fp.on_end(span)
        inner.on_end.assert_called_once_with(span)

    def test_toggle_disabled_to_enabled(self):
        """After toggling from disabled to enabled, new spans are captured."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=False)
        span = MagicMock()
        fp.on_end(span)
        assert inner.on_end.call_count == 0

        fp.enabled = True
        fp.on_end(span)
        assert inner.on_end.call_count == 1

    def test_toggle_enabled_to_disabled(self):
        """After toggling from enabled to disabled, new spans are discarded."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=True)
        span = MagicMock()
        fp.on_end(span)
        assert inner.on_end.call_count == 1

        fp.enabled = False
        fp.on_end(span)
        assert inner.on_end.call_count == 1  # still 1, not 2

    def test_shutdown_always_delegates(self):
        """shutdown() always delegates regardless of enabled state."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=False)
        fp.shutdown()
        inner.shutdown.assert_called_once()

    def test_force_flush_always_delegates(self):
        """force_flush() always delegates regardless of enabled state."""
        inner = MagicMock()
        fp = FilteringSpanProcessor(inner, enabled=False)
        fp.force_flush(5000)
        inner.force_flush.assert_called_once_with(5000)


class TestInitTracing:
    """Tests for init_tracing lifecycle function."""

    def _cleanup(self):
        """Reset module state after test."""
        provider_module._provider = None
        provider_module._filtering_processors = []

    def test_init_enabled_creates_provider(self, tmp_path):
        """init_tracing sets up a TracerProvider with FilteringSpanProcessors enabled."""
        try:
            config = TraceConfig(enabled=True)
            exporter = _StubExporter()
            provider = init_tracing(
                config, "test_campaign", tmp_path / "traces.db",
                in_memory_exporter=exporter,
            )
            assert isinstance(provider, TracerProvider)
            assert len(provider_module._filtering_processors) == 1
            assert provider_module._filtering_processors[0].enabled is True
        finally:
            self._cleanup()

    def test_init_disabled_creates_provider_disabled(self, tmp_path):
        """init_tracing with enabled=False creates provider but processors are disabled."""
        try:
            config = TraceConfig(enabled=False)
            exporter = _StubExporter()
            provider = init_tracing(
                config, "test_campaign", tmp_path / "traces.db",
                in_memory_exporter=exporter,
            )
            assert isinstance(provider, TracerProvider)
            assert len(provider_module._filtering_processors) == 1
            assert provider_module._filtering_processors[0].enabled is False
        finally:
            self._cleanup()

    def test_shutdown_tracing(self, tmp_path):
        """shutdown_tracing calls provider.shutdown() cleanly."""
        try:
            config = TraceConfig(enabled=True)
            exporter = _StubExporter()
            init_tracing(
                config, "test_campaign", tmp_path / "traces.db",
                in_memory_exporter=exporter,
            )
            assert provider_module._provider is not None
            shutdown_tracing()
            assert provider_module._provider is None
            assert provider_module._filtering_processors == []
        finally:
            self._cleanup()

    def test_toggle_tracing_via_function(self, tmp_path):
        """toggle_tracing flips enabled state on all filtering processors."""
        try:
            config = TraceConfig(enabled=True)
            exporter = _StubExporter()
            init_tracing(
                config, "test_campaign", tmp_path / "traces.db",
                in_memory_exporter=exporter,
            )
            assert provider_module._filtering_processors[0].enabled is True
            result = toggle_tracing(False)
            assert result is False
            assert provider_module._filtering_processors[0].enabled is False
            result = toggle_tracing(True)
            assert result is True
            assert provider_module._filtering_processors[0].enabled is True
        finally:
            self._cleanup()

    def test_init_idempotent(self, tmp_path):
        """Calling init_tracing again shuts down the previous provider first."""
        try:
            config = TraceConfig(enabled=True)
            exporter1 = _StubExporter()
            provider1 = init_tracing(
                config, "campaign1", tmp_path / "traces.db",
                in_memory_exporter=exporter1,
            )
            exporter2 = _StubExporter()
            provider2 = init_tracing(
                config, "campaign2", tmp_path / "traces.db",
                in_memory_exporter=exporter2,
            )
            assert provider2 is not provider1
            assert provider_module._provider is provider2
        finally:
            self._cleanup()
