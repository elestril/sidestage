"""Tests for tracing provider setup, FilteringSpanProcessor, and lifecycle functions."""

from typing import Any

import pytest
from unittest.mock import MagicMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor

from sidestage.config import TraceConfig
from sidestage.tracing.provider import (
    FilteringSpanProcessor,
    check_otlp_endpoint,
    init_tracing,
    toggle_tracing,
    shutdown_tracing,
    get_tracing_error,
)
from sidestage.tracing import provider as provider_module


# Patch check_otlp_endpoint to report reachable for tests that don't care
_REACHABLE = patch(
    "sidestage.tracing.provider.check_otlp_endpoint",
    return_value=(True, None),
)


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


class TestCheckOtlpEndpoint:
    """Tests for the OTLP endpoint reachability check."""

    def test_reachable_endpoint(self):
        """Returns (True, None) when the endpoint is reachable."""
        with patch("sidestage.tracing.provider.socket.create_connection"):
            reachable, error = check_otlp_endpoint("http://localhost:4318")
            assert reachable is True
            assert error is None

    def test_unreachable_endpoint(self):
        """Returns (False, message) when connection is refused."""
        with patch(
            "sidestage.tracing.provider.socket.create_connection",
            side_effect=ConnectionRefusedError("[Errno 111] Connection refused"),
        ):
            reachable, error = check_otlp_endpoint("http://localhost:4318")
            assert reachable is False
            assert error is not None
            assert "unreachable" in error
            assert "localhost:4318" in error

    def test_parses_custom_port(self):
        """Parses port from the endpoint URL."""
        with patch("sidestage.tracing.provider.socket.create_connection") as mock_conn:
            check_otlp_endpoint("http://collector.example.com:9999")
            mock_conn.assert_called_once()
            addr = mock_conn.call_args[0][0]
            assert addr == ("collector.example.com", 9999)


class TestInitTracing:
    """Tests for init_tracing lifecycle function."""

    def _cleanup(self):
        """Reset module state after test."""
        provider_module._provider = None
        provider_module._filtering_processors = []
        provider_module._init_error = None
        provider_module._otlp_endpoint = None

    @_REACHABLE
    def test_init_enabled_creates_provider(self, _mock: Any):
        """init_tracing sets up a TracerProvider with FilteringSpanProcessor enabled."""
        try:
            config = TraceConfig(enabled=True)
            provider = init_tracing(config, "test_campaign")
            assert isinstance(provider, TracerProvider)
            assert len(provider_module._filtering_processors) == 1
            assert provider_module._filtering_processors[0].enabled is True
            assert get_tracing_error() is None
        finally:
            self._cleanup()

    def test_init_disabled_creates_provider_disabled(self):
        """init_tracing with enabled=False creates provider but processor is disabled."""
        try:
            config = TraceConfig(enabled=False)
            provider = init_tracing(config, "test_campaign")
            assert isinstance(provider, TracerProvider)
            assert len(provider_module._filtering_processors) == 1
            assert provider_module._filtering_processors[0].enabled is False
            assert get_tracing_error() is None
        finally:
            self._cleanup()

    def test_init_enabled_unreachable_disables_tracing(self):
        """When enabled=True but endpoint unreachable, processor is disabled and error stored."""
        with patch(
            "sidestage.tracing.provider.check_otlp_endpoint",
            return_value=(False, "OTLP endpoint unreachable at http://localhost:4318: conn refused"),
        ):
            try:
                config = TraceConfig(enabled=True)
                provider = init_tracing(config, "test_campaign")
                assert isinstance(provider, TracerProvider)
                assert provider_module._filtering_processors[0].enabled is False
                err = get_tracing_error()
                assert err is not None
                assert "unreachable" in err
            finally:
                self._cleanup()

    @_REACHABLE
    def test_shutdown_tracing(self, _mock: Any):
        """shutdown_tracing calls provider.shutdown() cleanly."""
        try:
            config = TraceConfig(enabled=True)
            init_tracing(config, "test_campaign")
            assert provider_module._provider is not None
            shutdown_tracing()
            assert provider_module._provider is None
            assert provider_module._filtering_processors == []
            assert get_tracing_error() is None
        finally:
            self._cleanup()

    @_REACHABLE
    def test_toggle_tracing_via_function(self, _mock: Any):
        """toggle_tracing flips enabled state on all filtering processors."""
        try:
            config = TraceConfig(enabled=True)
            init_tracing(config, "test_campaign")
            assert provider_module._filtering_processors[0].enabled is True
            enabled, error = toggle_tracing(False)
            assert enabled is False
            assert error is None
            assert provider_module._filtering_processors[0].enabled is False
            enabled, error = toggle_tracing(True)
            assert enabled is True
            assert error is None
            assert provider_module._filtering_processors[0].enabled is True
        finally:
            self._cleanup()

    def test_toggle_enable_unreachable_returns_error(self):
        """toggle_tracing(True) returns error when endpoint is unreachable."""
        with patch(
            "sidestage.tracing.provider.check_otlp_endpoint",
            return_value=(False, "OTLP endpoint unreachable at http://localhost:4318: conn refused"),
        ):
            try:
                config = TraceConfig(enabled=False)
                init_tracing(config, "test_campaign")
                enabled, error = toggle_tracing(True)
                assert enabled is False
                assert error is not None
                assert "unreachable" in error
                assert provider_module._filtering_processors[0].enabled is False
            finally:
                self._cleanup()

    def test_toggle_disable_always_succeeds(self):
        """toggle_tracing(False) always succeeds regardless of endpoint."""
        try:
            config = TraceConfig(enabled=False)
            init_tracing(config, "test_campaign")
            enabled, error = toggle_tracing(False)
            assert enabled is False
            assert error is None
        finally:
            self._cleanup()

    @_REACHABLE
    def test_init_idempotent(self, _mock: Any):
        """Calling init_tracing again shuts down the previous provider first."""
        try:
            config = TraceConfig(enabled=True)
            provider1 = init_tracing(config, "campaign1")
            provider2 = init_tracing(config, "campaign2")
            assert provider2 is not provider1
            assert provider_module._provider is provider2
        finally:
            self._cleanup()
