diff --git a/src/sidestage/tracing/__init__.py b/src/sidestage/tracing/__init__.py
new file mode 100644
index 0000000..9cd3b81
--- /dev/null
+++ b/src/sidestage/tracing/__init__.py
@@ -0,0 +1,9 @@
+"""Sidestage tracing package -- OpenTelemetry-based trace capture.
+
+Public API:
+    init_tracing(config, campaign_name, db_path) -- set up TracerProvider and exporters
+    toggle_tracing(enabled) -- flip tracing on/off at runtime
+    shutdown_tracing() -- flush pending spans and shut down the provider
+"""
+
+from sidestage.tracing.provider import init_tracing, toggle_tracing, shutdown_tracing
diff --git a/src/sidestage/tracing/middleware.py b/src/sidestage/tracing/middleware.py
new file mode 100644
index 0000000..6483e4b
--- /dev/null
+++ b/src/sidestage/tracing/middleware.py
@@ -0,0 +1,74 @@
+"""Convenience decorators and helpers for tracing instrumentation."""
+
+from __future__ import annotations
+
+import functools
+from typing import Any
+
+from opentelemetry import trace
+from opentelemetry.trace import StatusCode
+
+from sidestage import config as sidestage_config
+
+
+def trace_span(name: str, attributes: dict[str, Any] | None = None):
+    """Decorator that wraps an async function in a span."""
+    def decorator(func):
+        @functools.wraps(func)
+        async def wrapper(*args, **kwargs):
+            tracer = trace.get_tracer("sidestage")
+            with tracer.start_as_current_span(name) as span:
+                if attributes:
+                    for k, v in attributes.items():
+                        span.set_attribute(k, v)
+                return await func(*args, **kwargs)
+        return wrapper
+    return decorator
+
+
+def current_trace_id() -> str | None:
+    """Get the current trace_id as a hex string, or None if no active span."""
+    span = trace.get_current_span()
+    ctx = span.get_span_context()
+    if ctx and ctx.trace_id != 0:
+        return format(ctx.trace_id, '032x')
+    return None
+
+
+def add_trace_event(name: str, attributes: dict[str, Any] | None = None) -> None:
+    """Add an event to the currently active span, respecting capture flags.
+
+    Checks TraceConfig capture flags to decide whether to record the event.
+    Truncates string attribute values exceeding max_attribute_length.
+    """
+    span = trace.get_current_span()
+    if not span.is_recording():
+        return
+
+    cfg = sidestage_config.get().tracing
+
+    # Check capture flags
+    if name.startswith(("gen_ai.prompt", "gen_ai.completion")) and not cfg.capture_prompts:
+        return
+    if name.startswith("tool.") and not cfg.capture_tool_args:
+        return
+    if name.startswith("memory.") and not cfg.capture_memory_content:
+        return
+
+    # Truncate long string attributes
+    if attributes:
+        truncated = {}
+        for k, v in attributes.items():
+            if isinstance(v, str) and len(v) > cfg.max_attribute_length:
+                truncated[k] = v[:cfg.max_attribute_length] + "[truncated]"
+            else:
+                truncated[k] = v
+        attributes = truncated
+
+    span.add_event(name, attributes=attributes)
+
+
+def record_error(span, exception: Exception) -> None:
+    """Set span status to ERROR and record the exception."""
+    span.set_status(StatusCode.ERROR, str(exception))
+    span.record_exception(exception)
diff --git a/src/sidestage/tracing/provider.py b/src/sidestage/tracing/provider.py
new file mode 100644
index 0000000..e0b50ab
--- /dev/null
+++ b/src/sidestage/tracing/provider.py
@@ -0,0 +1,128 @@
+"""TracerProvider setup, FilteringSpanProcessor, and lifecycle functions."""
+
+from __future__ import annotations
+
+import logging
+from pathlib import Path
+from typing import TYPE_CHECKING
+
+from opentelemetry import trace
+from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
+from opentelemetry.sdk.trace.export import (
+    SpanProcessor,
+    SimpleSpanProcessor,
+    BatchSpanProcessor,
+    SpanExporter,
+)
+from opentelemetry.sdk.resources import Resource
+from opentelemetry.context import Context
+
+if TYPE_CHECKING:
+    from sidestage.config import TraceConfig
+
+logger = logging.getLogger(__name__)
+
+_provider: TracerProvider | None = None
+_filtering_processors: list["FilteringSpanProcessor"] = []
+
+
+class FilteringSpanProcessor(SpanProcessor):
+    """SpanProcessor wrapper that can be toggled on/off at runtime."""
+
+    def __init__(self, wrapped: SpanProcessor, enabled: bool = True):
+        self._wrapped = wrapped
+        self.enabled = enabled
+
+    def on_start(self, span: ReadableSpan, parent_context: Context | None = None) -> None:
+        if self.enabled:
+            self._wrapped.on_start(span, parent_context)
+
+    def on_end(self, span: ReadableSpan) -> None:
+        if self.enabled:
+            self._wrapped.on_end(span)
+
+    def shutdown(self) -> None:
+        self._wrapped.shutdown()
+
+    def force_flush(self, timeout_millis: int = 30000) -> bool:
+        return self._wrapped.force_flush(timeout_millis)
+
+
+def init_tracing(
+    config: "TraceConfig",
+    campaign_name: str,
+    db_path: Path,
+    *,
+    in_memory_exporter: SpanExporter | None = None,
+    sqlite_exporter: SpanExporter | None = None,
+) -> TracerProvider:
+    """Set up TracerProvider and exporters.
+
+    Args:
+        config: TraceConfig instance
+        campaign_name: Used in the OTel Resource for service.name
+        db_path: Path to the SQLite database for trace persistence
+        in_memory_exporter: Optional exporter for in-memory traces (default: created from Section 03)
+        sqlite_exporter: Optional exporter for SQLite persistence (default: created from Section 03)
+
+    Returns:
+        The configured TracerProvider
+    """
+    global _provider, _filtering_processors
+
+    # Shutdown previous provider if re-initializing
+    if _provider is not None:
+        shutdown_tracing()
+
+    resource = Resource.create({
+        "service.name": "sidestage",
+        "campaign.name": campaign_name,
+    })
+
+    provider = TracerProvider(resource=resource)
+    _filtering_processors = []
+
+    if in_memory_exporter is not None:
+        mem_processor = SimpleSpanProcessor(in_memory_exporter)
+        filtering_mem = FilteringSpanProcessor(mem_processor, enabled=config.enabled)
+        provider.add_span_processor(filtering_mem)
+        _filtering_processors.append(filtering_mem)
+
+    if sqlite_exporter is not None:
+        batch_processor = BatchSpanProcessor(sqlite_exporter)
+        filtering_batch = FilteringSpanProcessor(batch_processor, enabled=config.enabled)
+        provider.add_span_processor(filtering_batch)
+        _filtering_processors.append(filtering_batch)
+
+    trace.set_tracer_provider(provider)
+    _provider = provider
+
+    logger.info(
+        "Tracing initialized (enabled=%s, campaign=%s)",
+        config.enabled,
+        campaign_name,
+    )
+
+    return provider
+
+
+def toggle_tracing(enabled: bool) -> bool:
+    """Flip tracing on/off at runtime.
+
+    Returns the new enabled state.
+    """
+    for fp in _filtering_processors:
+        fp.enabled = enabled
+    logger.info("Tracing toggled: enabled=%s", enabled)
+    return enabled
+
+
+def shutdown_tracing() -> None:
+    """Flush pending spans and shut down the provider."""
+    global _provider, _filtering_processors
+
+    if _provider is not None:
+        _provider.shutdown()
+        _provider = None
+        _filtering_processors = []
+        logger.info("Tracing shutdown complete")
diff --git a/tests/conftest.py b/tests/conftest.py
index 4a16583..15e2dd1 100644
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -3,6 +3,7 @@ import pytest
 import httpx
 from pathlib import Path
 from sidestage import config as sidestage_config
+from opentelemetry import trace
 
 DEFAULT_LLM_BASE_URL = "http://localhost:8080/v1"
 
@@ -38,6 +39,15 @@ def _init_config(tmp_path: Path):
     sidestage_config._instance = None
 
 
+@pytest.fixture(autouse=True)
+def _reset_otel_provider():
+    """Reset the global OTel TracerProvider between tests."""
+    yield
+    # Reset OTel global state so tests can set their own provider
+    trace._TRACER_PROVIDER_SET_ONCE._done = False
+    trace._TRACER_PROVIDER = None
+
+
 @pytest.fixture
 def llm_base_url():
     """Base URL of the LLM server for tests."""
diff --git a/tests/unit/test_tracing_middleware.py b/tests/unit/test_tracing_middleware.py
new file mode 100644
index 0000000..e0ac229
--- /dev/null
+++ b/tests/unit/test_tracing_middleware.py
@@ -0,0 +1,206 @@
+"""Tests for tracing convenience helpers: trace_span, current_trace_id, add_trace_event, record_error."""
+
+import pytest
+from opentelemetry import trace
+from opentelemetry.sdk.trace import TracerProvider
+from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
+from opentelemetry.trace import StatusCode
+
+from sidestage.config import TraceConfig
+from sidestage import config as sidestage_config
+from sidestage.tracing.middleware import (
+    trace_span,
+    current_trace_id,
+    add_trace_event,
+    record_error,
+)
+
+
+class _CollectingExporter(SpanExporter):
+    """Exporter that collects finished spans for inspection."""
+
+    def __init__(self):
+        self.spans: list = []
+
+    def export(self, spans):
+        self.spans.extend(spans)
+        return SpanExportResult.SUCCESS
+
+    def shutdown(self):
+        pass
+
+
+def _setup_provider():
+    """Create a TracerProvider with a collecting exporter for testing."""
+    exporter = _CollectingExporter()
+    provider = TracerProvider()
+    provider.add_span_processor(SimpleSpanProcessor(exporter))
+    trace.set_tracer_provider(provider)
+    return provider, exporter
+
+
+class TestTraceSpan:
+    """Tests for the trace_span async decorator."""
+
+    @pytest.mark.anyio
+    async def test_creates_span(self):
+        """Decorated async function produces a span with the given name."""
+        provider, exporter = _setup_provider()
+        try:
+            @trace_span("test.operation")
+            async def my_func():
+                return 42
+
+            result = await my_func()
+            assert result == 42
+            provider.force_flush()
+            span_names = [s.name for s in exporter.spans]
+            assert "test.operation" in span_names
+        finally:
+            provider.shutdown()
+
+    def test_preserves_function_metadata(self):
+        """The decorated function retains __name__ and __doc__ from the original."""
+        @trace_span("test.op")
+        async def some_function():
+            """Some docstring."""
+            pass
+
+        assert some_function.__name__ == "some_function"
+        assert some_function.__doc__ == "Some docstring."
+
+
+class TestCurrentTraceId:
+    """Tests for current_trace_id helper."""
+
+    def test_returns_hex_inside_span(self):
+        """When there is an active span, returns the trace_id as a hex string."""
+        provider, _ = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("test_span"):
+                tid = current_trace_id()
+                assert tid is not None
+                assert len(tid) == 32
+                int(tid, 16)  # valid hex
+        finally:
+            provider.shutdown()
+
+    def test_returns_none_outside_span(self):
+        """When no span is active, returns None."""
+        provider = TracerProvider()
+        trace.set_tracer_provider(provider)
+        try:
+            tid = current_trace_id()
+            assert tid is None
+        finally:
+            provider.shutdown()
+
+
+class TestAddTraceEvent:
+    """Tests for add_trace_event helper."""
+
+    def test_adds_event(self):
+        """Adds a named event with the given attributes to the current span."""
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent"):
+                add_trace_event("test.event", {"key": "value"})
+            provider.force_flush()
+            span = exporter.spans[0]
+            event_names = [e.name for e in span.events]
+            assert "test.event" in event_names
+        finally:
+            provider.shutdown()
+
+    def test_truncates_long_strings(self):
+        """String values longer than max_attribute_length are truncated with '[truncated]' suffix."""
+        # Set a short max_attribute_length for testing
+        cfg = sidestage_config.get()
+        cfg.tracing.max_attribute_length = 10
+
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent"):
+                add_trace_event("test.event", {"data": "a" * 50})
+            provider.force_flush()
+            span = exporter.spans[0]
+            event = [e for e in span.events if e.name == "test.event"][0]
+            assert event.attributes["data"].endswith("[truncated]")
+            assert len(event.attributes["data"]) == 10 + len("[truncated]")
+        finally:
+            provider.shutdown()
+
+    def test_skips_prompt_events_when_disabled(self):
+        """When capture_prompts=False, events named 'gen_ai.prompt' are not added."""
+        cfg = sidestage_config.get()
+        cfg.tracing.capture_prompts = False
+
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent"):
+                add_trace_event("gen_ai.prompt", {"text": "hello"})
+            provider.force_flush()
+            span = exporter.spans[0]
+            event_names = [e.name for e in span.events]
+            assert "gen_ai.prompt" not in event_names
+        finally:
+            provider.shutdown()
+
+    def test_skips_tool_events_when_disabled(self):
+        """When capture_tool_args=False, events named 'tool.arguments' are not added."""
+        cfg = sidestage_config.get()
+        cfg.tracing.capture_tool_args = False
+
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent"):
+                add_trace_event("tool.arguments", {"args": "test"})
+            provider.force_flush()
+            span = exporter.spans[0]
+            event_names = [e.name for e in span.events]
+            assert "tool.arguments" not in event_names
+        finally:
+            provider.shutdown()
+
+    def test_skips_memory_events_when_disabled(self):
+        """When capture_memory_content=False, events named 'memory.content' are not added."""
+        cfg = sidestage_config.get()
+        cfg.tracing.capture_memory_content = False
+
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent"):
+                add_trace_event("memory.content", {"content": "test"})
+            provider.force_flush()
+            span = exporter.spans[0]
+            event_names = [e.name for e in span.events]
+            assert "memory.content" not in event_names
+        finally:
+            provider.shutdown()
+
+
+class TestRecordError:
+    """Tests for record_error helper."""
+
+    def test_records_error(self):
+        """Sets span status to ERROR with the exception message and records the exception."""
+        provider, exporter = _setup_provider()
+        try:
+            tracer = trace.get_tracer("test")
+            with tracer.start_as_current_span("parent") as span:
+                exc = ValueError("something went wrong")
+                record_error(span, exc)
+            provider.force_flush()
+            finished_span = exporter.spans[0]
+            assert finished_span.status.status_code == StatusCode.ERROR
+            assert "something went wrong" in finished_span.status.description
+            exception_events = [e for e in finished_span.events if e.name == "exception"]
+            assert len(exception_events) == 1
+        finally:
+            provider.shutdown()
diff --git a/tests/unit/test_tracing_provider.py b/tests/unit/test_tracing_provider.py
new file mode 100644
index 0000000..94e264b
--- /dev/null
+++ b/tests/unit/test_tracing_provider.py
@@ -0,0 +1,197 @@
+"""Tests for tracing provider setup, FilteringSpanProcessor, and lifecycle functions."""
+
+import pytest
+from unittest.mock import MagicMock, patch
+from opentelemetry import trace
+from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
+from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor
+
+from sidestage.config import TraceConfig
+from sidestage.tracing.provider import (
+    FilteringSpanProcessor,
+    init_tracing,
+    toggle_tracing,
+    shutdown_tracing,
+)
+from sidestage.tracing import provider as provider_module
+
+
+class _StubExporter(SpanExporter):
+    """Stub exporter that records exported spans."""
+
+    def __init__(self):
+        self.spans: list = []
+
+    def export(self, spans):
+        self.spans.extend(spans)
+        return SpanExportResult.SUCCESS
+
+    def shutdown(self):
+        pass
+
+
+class TestFilteringSpanProcessor:
+    """Tests for the FilteringSpanProcessor wrapper."""
+
+    def test_passes_spans_when_enabled(self):
+        """When enabled, on_start and on_end delegate to the wrapped processor."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=True)
+        span = MagicMock()
+        fp.on_start(span, None)
+        fp.on_end(span)
+        inner.on_start.assert_called_once_with(span, None)
+        inner.on_end.assert_called_once_with(span)
+
+    def test_discards_spans_when_disabled(self):
+        """When disabled, on_start and on_end are no-ops -- wrapped processor never called."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=False)
+        span = MagicMock()
+        fp.on_start(span, None)
+        fp.on_end(span)
+        inner.on_start.assert_not_called()
+        inner.on_end.assert_not_called()
+
+    def test_toggle_takes_effect_immediately(self):
+        """Flipping .enabled changes behavior on the very next span."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=False)
+        span = MagicMock()
+        fp.on_end(span)
+        inner.on_end.assert_not_called()
+
+        fp.enabled = True
+        fp.on_end(span)
+        inner.on_end.assert_called_once_with(span)
+
+    def test_toggle_disabled_to_enabled(self):
+        """After toggling from disabled to enabled, new spans are captured."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=False)
+        span = MagicMock()
+        fp.on_end(span)
+        assert inner.on_end.call_count == 0
+
+        fp.enabled = True
+        fp.on_end(span)
+        assert inner.on_end.call_count == 1
+
+    def test_toggle_enabled_to_disabled(self):
+        """After toggling from enabled to disabled, new spans are discarded."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=True)
+        span = MagicMock()
+        fp.on_end(span)
+        assert inner.on_end.call_count == 1
+
+        fp.enabled = False
+        fp.on_end(span)
+        assert inner.on_end.call_count == 1  # still 1, not 2
+
+    def test_shutdown_always_delegates(self):
+        """shutdown() always delegates regardless of enabled state."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=False)
+        fp.shutdown()
+        inner.shutdown.assert_called_once()
+
+    def test_force_flush_always_delegates(self):
+        """force_flush() always delegates regardless of enabled state."""
+        inner = MagicMock()
+        fp = FilteringSpanProcessor(inner, enabled=False)
+        fp.force_flush(5000)
+        inner.force_flush.assert_called_once_with(5000)
+
+
+class TestInitTracing:
+    """Tests for init_tracing lifecycle function."""
+
+    def _cleanup(self):
+        """Reset module state after test."""
+        provider_module._provider = None
+        provider_module._filtering_processors = []
+
+    def test_init_enabled_creates_provider(self, tmp_path):
+        """init_tracing sets up a TracerProvider with FilteringSpanProcessors enabled."""
+        try:
+            config = TraceConfig(enabled=True)
+            exporter = _StubExporter()
+            provider = init_tracing(
+                config, "test_campaign", tmp_path / "traces.db",
+                in_memory_exporter=exporter,
+            )
+            assert isinstance(provider, TracerProvider)
+            assert len(provider_module._filtering_processors) == 1
+            assert provider_module._filtering_processors[0].enabled is True
+        finally:
+            self._cleanup()
+
+    def test_init_disabled_creates_provider_disabled(self, tmp_path):
+        """init_tracing with enabled=False creates provider but processors are disabled."""
+        try:
+            config = TraceConfig(enabled=False)
+            exporter = _StubExporter()
+            provider = init_tracing(
+                config, "test_campaign", tmp_path / "traces.db",
+                in_memory_exporter=exporter,
+            )
+            assert isinstance(provider, TracerProvider)
+            assert len(provider_module._filtering_processors) == 1
+            assert provider_module._filtering_processors[0].enabled is False
+        finally:
+            self._cleanup()
+
+    def test_shutdown_tracing(self, tmp_path):
+        """shutdown_tracing calls provider.shutdown() cleanly."""
+        try:
+            config = TraceConfig(enabled=True)
+            exporter = _StubExporter()
+            init_tracing(
+                config, "test_campaign", tmp_path / "traces.db",
+                in_memory_exporter=exporter,
+            )
+            assert provider_module._provider is not None
+            shutdown_tracing()
+            assert provider_module._provider is None
+            assert provider_module._filtering_processors == []
+        finally:
+            self._cleanup()
+
+    def test_toggle_tracing_via_function(self, tmp_path):
+        """toggle_tracing flips enabled state on all filtering processors."""
+        try:
+            config = TraceConfig(enabled=True)
+            exporter = _StubExporter()
+            init_tracing(
+                config, "test_campaign", tmp_path / "traces.db",
+                in_memory_exporter=exporter,
+            )
+            assert provider_module._filtering_processors[0].enabled is True
+            result = toggle_tracing(False)
+            assert result is False
+            assert provider_module._filtering_processors[0].enabled is False
+            result = toggle_tracing(True)
+            assert result is True
+            assert provider_module._filtering_processors[0].enabled is True
+        finally:
+            self._cleanup()
+
+    def test_init_idempotent(self, tmp_path):
+        """Calling init_tracing again shuts down the previous provider first."""
+        try:
+            config = TraceConfig(enabled=True)
+            exporter1 = _StubExporter()
+            provider1 = init_tracing(
+                config, "campaign1", tmp_path / "traces.db",
+                in_memory_exporter=exporter1,
+            )
+            exporter2 = _StubExporter()
+            provider2 = init_tracing(
+                config, "campaign2", tmp_path / "traces.db",
+                in_memory_exporter=exporter2,
+            )
+            assert provider2 is not provider1
+            assert provider_module._provider is provider2
+        finally:
+            self._cleanup()
