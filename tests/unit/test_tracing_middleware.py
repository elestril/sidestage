"""Tests for tracing convenience helpers: trace_span, current_trace_id, add_trace_event, record_error."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from sidestage.config import TraceConfig
from sidestage import config as sidestage_config
from sidestage.tracing.middleware import (
    trace_span,
    current_trace_id,
    add_trace_event,
    record_error,
)


class _CollectingExporter(SpanExporter):
    """Exporter that collects finished spans for inspection."""

    def __init__(self):
        self.spans: list = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def _setup_provider():
    """Create a TracerProvider with a collecting exporter for testing."""
    exporter = _CollectingExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider, exporter


class TestTraceSpan:
    """Tests for the trace_span async decorator."""

    @pytest.mark.anyio
    async def test_creates_span(self):
        """Decorated async function produces a span with the given name."""
        provider, exporter = _setup_provider()
        try:
            @trace_span("test.operation")
            async def my_func():
                return 42

            result = await my_func()
            assert result == 42
            provider.force_flush()
            span_names = [s.name for s in exporter.spans]
            assert "test.operation" in span_names
        finally:
            provider.shutdown()

    def test_preserves_function_metadata(self):
        """The decorated function retains __name__ and __doc__ from the original."""
        @trace_span("test.op")
        async def some_function():
            """Some docstring."""
            pass

        assert some_function.__name__ == "some_function"
        assert some_function.__doc__ == "Some docstring."


class TestCurrentTraceId:
    """Tests for current_trace_id helper."""

    def test_returns_hex_inside_span(self):
        """When there is an active span, returns the trace_id as a hex string."""
        provider, _ = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test_span"):
                tid = current_trace_id()
                assert tid is not None
                assert len(tid) == 32
                int(tid, 16)  # valid hex
        finally:
            provider.shutdown()

    def test_returns_none_outside_span(self):
        """When no span is active, returns None."""
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        try:
            tid = current_trace_id()
            assert tid is None
        finally:
            provider.shutdown()


class TestAddTraceEvent:
    """Tests for add_trace_event helper."""

    def test_adds_event(self):
        """Adds a named event with the given attributes to the current span."""
        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent"):
                add_trace_event("test.event", {"key": "value"})
            provider.force_flush()
            span = exporter.spans[0]
            event_names = [e.name for e in span.events]
            assert "test.event" in event_names
        finally:
            provider.shutdown()

    def test_truncates_long_strings(self):
        """String values longer than max_attribute_length are truncated with '[truncated]' suffix."""
        # Set a short max_attribute_length for testing
        cfg = sidestage_config.get()
        cfg.tracing.max_attribute_length = 10

        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent"):
                add_trace_event("test.event", {"data": "a" * 50})
            provider.force_flush()
            span = exporter.spans[0]
            event = [e for e in span.events if e.name == "test.event"][0]
            assert event.attributes["data"].endswith("[truncated]")
            assert len(event.attributes["data"]) == 10 + len("[truncated]")
        finally:
            provider.shutdown()

    def test_skips_prompt_events_when_disabled(self):
        """When capture_prompts=False, events named 'gen_ai.prompt' are not added."""
        cfg = sidestage_config.get()
        cfg.tracing.capture_prompts = False

        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent"):
                add_trace_event("gen_ai.prompt", {"text": "hello"})
            provider.force_flush()
            span = exporter.spans[0]
            event_names = [e.name for e in span.events]
            assert "gen_ai.prompt" not in event_names
        finally:
            provider.shutdown()

    def test_skips_tool_events_when_disabled(self):
        """When capture_tool_args=False, events named 'tool.arguments' are not added."""
        cfg = sidestage_config.get()
        cfg.tracing.capture_tool_args = False

        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent"):
                add_trace_event("tool.arguments", {"args": "test"})
            provider.force_flush()
            span = exporter.spans[0]
            event_names = [e.name for e in span.events]
            assert "tool.arguments" not in event_names
        finally:
            provider.shutdown()

    def test_skips_memory_events_when_disabled(self):
        """When capture_memory_content=False, events named 'memory.content' are not added."""
        cfg = sidestage_config.get()
        cfg.tracing.capture_memory_content = False

        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent"):
                add_trace_event("memory.content", {"content": "test"})
            provider.force_flush()
            span = exporter.spans[0]
            event_names = [e.name for e in span.events]
            assert "memory.content" not in event_names
        finally:
            provider.shutdown()


class TestRecordError:
    """Tests for record_error helper."""

    def test_records_error(self):
        """Sets span status to ERROR with the exception message and records the exception."""
        provider, exporter = _setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent") as span:
                exc = ValueError("something went wrong")
                record_error(span, exc)
            provider.force_flush()
            finished_span = exporter.spans[0]
            assert finished_span.status.status_code == StatusCode.ERROR
            assert "something went wrong" in finished_span.status.description
            exception_events = [e for e in finished_span.events if e.name == "exception"]
            assert len(exception_events) == 1
        finally:
            provider.shutdown()
