Now I have a comprehensive understanding of the codebase structure, testing patterns, and the full plan. Let me generate the section content.

# Section 02: Tracing Core

## Overview

This section implements the core tracing infrastructure: the `TracerProvider` setup, the custom `FilteringSpanProcessor`, the public lifecycle functions (`init_tracing`, `toggle_tracing`, `shutdown_tracing`), and the convenience instrumentation helpers (`trace_span`, `current_trace_id`, `add_trace_event`, `record_error`).

These components live in the `src/sidestage/tracing/` package (files `__init__.py`, `provider.py`, and `middleware.py`). The exporters are covered in Section 03, so this section uses stub/placeholder exporters where needed.

**Depends on:** Section 01 (TraceConfig model and `SidestageConfig.tracing` field must exist)

**Blocks:** Section 03 (Exporters), Section 04 (Backend Instrumentation)

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/sidestage/tracing/__init__.py` | Create -- public API surface |
| `src/sidestage/tracing/provider.py` | Create -- TracerProvider setup, FilteringSpanProcessor |
| `src/sidestage/tracing/middleware.py` | Create -- convenience decorators and helpers |
| `tests/unit/test_tracing_provider.py` | Create -- tests for provider lifecycle |
| `tests/unit/test_tracing_middleware.py` | Create -- tests for convenience helpers |

---

## Tests First

All tests use **pytest** with **pytest-anyio** for async tests, following the project convention of `conftest.py` fixtures and `_init_config(tmp_path)` for config setup.

### File: `/home/harald/src/sidestage/tests/unit/test_tracing_provider.py`

```python
"""Tests for tracing provider setup, FilteringSpanProcessor, and lifecycle functions."""

import pytest
from unittest.mock import MagicMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from sidestage.tracing.provider import (
    FilteringSpanProcessor,
    init_tracing,
    toggle_tracing,
    shutdown_tracing,
)


class TestFilteringSpanProcessor:
    """Tests for the FilteringSpanProcessor wrapper."""

    # Test: FilteringSpanProcessor passes spans to wrapped processor when enabled=True
    def test_passes_spans_when_enabled(self):
        """When enabled, on_start and on_end delegate to the wrapped processor."""

    # Test: FilteringSpanProcessor discards spans (no-op on_end) when enabled=False
    def test_discards_spans_when_disabled(self):
        """When disabled, on_start and on_end are no-ops -- wrapped processor never called."""

    # Test: toggle_tracing flips FilteringSpanProcessor.enabled and takes effect immediately
    def test_toggle_takes_effect_immediately(self):
        """Flipping .enabled changes behavior on the very next span."""

    # Test: toggle_tracing from disabled to enabled starts capturing new spans
    def test_toggle_disabled_to_enabled(self):
        """After toggling from disabled to enabled, new spans are captured."""

    # Test: toggle_tracing from enabled to disabled stops capturing
    def test_toggle_enabled_to_disabled(self):
        """After toggling from enabled to disabled, new spans are discarded."""


class TestInitTracing:
    """Tests for init_tracing lifecycle function."""

    # Test: init_tracing with enabled=True creates real TracerProvider with both processors
    def test_init_enabled_creates_provider(self, tmp_path):
        """init_tracing sets up a TracerProvider with FilteringSpanProcessors enabled."""

    # Test: init_tracing with enabled=False creates TracerProvider with disabled FilteringSpanProcessor
    def test_init_disabled_creates_provider_disabled(self, tmp_path):
        """init_tracing with enabled=False creates provider but processors are disabled."""

    # Test: shutdown_tracing calls provider.shutdown() without error
    def test_shutdown_tracing(self, tmp_path):
        """shutdown_tracing calls provider.shutdown() cleanly."""
```

### File: `/home/harald/src/sidestage/tests/unit/test_tracing_middleware.py`

```python
"""Tests for tracing convenience helpers: trace_span, current_trace_id, add_trace_event, record_error."""

import pytest
from unittest.mock import MagicMock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode

from sidestage.tracing.middleware import (
    trace_span,
    current_trace_id,
    add_trace_event,
    record_error,
)


class TestTraceSpan:
    """Tests for the trace_span async decorator."""

    # Test: trace_span decorator creates a span around an async function
    async def test_creates_span(self):
        """Decorated async function produces a span with the given name."""

    # Test: trace_span decorator preserves function name and signature (functools.wraps)
    def test_preserves_function_metadata(self):
        """The decorated function retains __name__ and __doc__ from the original."""


class TestCurrentTraceId:
    """Tests for current_trace_id helper."""

    # Test: current_trace_id returns hex string when inside a span
    def test_returns_hex_inside_span(self):
        """When there is an active span, returns the trace_id as a hex string."""

    # Test: current_trace_id returns None when no active span
    def test_returns_none_outside_span(self):
        """When no span is active, returns None."""


class TestAddTraceEvent:
    """Tests for add_trace_event helper."""

    # Test: add_trace_event adds event to current span with attributes
    def test_adds_event(self):
        """Adds a named event with the given attributes to the current span."""

    # Test: add_trace_event truncates strings exceeding max_attribute_length
    def test_truncates_long_strings(self):
        """String values longer than max_attribute_length are truncated with '[truncated]' suffix."""

    # Test: add_trace_event respects capture_prompts=False (skips gen_ai.prompt events)
    def test_skips_prompt_events_when_disabled(self):
        """When capture_prompts=False, events named 'gen_ai.prompt' are not added."""

    # Test: add_trace_event respects capture_tool_args=False (skips tool argument events)
    def test_skips_tool_events_when_disabled(self):
        """When capture_tool_args=False, events named 'tool.arguments' are not added."""

    # Test: add_trace_event respects capture_memory_content=False (skips memory content events)
    def test_skips_memory_events_when_disabled(self):
        """When capture_memory_content=False, events named 'memory.content' are not added."""


class TestRecordError:
    """Tests for record_error helper."""

    # Test: record_error sets span status to ERROR and records exception
    def test_records_error(self):
        """Sets span status to ERROR with the exception message and records the exception."""
```

---

## Implementation Details

### 1. Package Init: `src/sidestage/tracing/__init__.py`

This file serves as the public API surface for the tracing package. It re-exports the key functions so that consumers can write `from sidestage.tracing import init_tracing, toggle_tracing`.

```python
"""Sidestage tracing package -- OpenTelemetry-based trace capture.

Public API:
    init_tracing(config, campaign_name, db_path) -- set up TracerProvider and exporters
    toggle_tracing(enabled) -- flip tracing on/off at runtime
    shutdown_tracing() -- flush pending spans and shut down the provider
"""

from sidestage.tracing.provider import init_tracing, toggle_tracing, shutdown_tracing
```

The `__init__.py` intentionally does not import middleware helpers; those are imported directly by instrumentation code (`from sidestage.tracing.middleware import trace_span, ...`).

### 2. Provider Setup: `src/sidestage/tracing/provider.py`

This is the heart of the tracing core. It contains:

#### FilteringSpanProcessor

A custom `SpanProcessor` that wraps another processor and adds an `enabled` flag.

- Constructor takes `wrapped: SpanProcessor` and `enabled: bool = True`
- `on_start(span, parent_context)`: if `self.enabled`, delegates to `self._wrapped.on_start(span, parent_context)`. Otherwise, no-op.
- `on_end(span)`: if `self.enabled`, delegates to `self._wrapped.on_end(span)`. Otherwise, no-op.
- `shutdown()`: always delegates to `self._wrapped.shutdown()` (must flush regardless of enabled state).
- `force_flush(timeout_millis)`: always delegates to `self._wrapped.force_flush(timeout_millis)`.

The `enabled` attribute is a simple boolean. No locking is needed -- Python's GIL ensures atomic reads/writes of a boolean, and the worst case of a race is one extra span being captured or dropped during a toggle, which is acceptable.

#### Module-level state

The module maintains private references to the active components:

```python
_provider: TracerProvider | None = None
_filtering_processors: list[FilteringSpanProcessor] = []
```

These are set by `init_tracing` and used by `toggle_tracing` and `shutdown_tracing`.

#### init_tracing(config, campaign_name, db_path)

Parameters:
- `config`: A `TraceConfig` instance (from Section 01)
- `campaign_name`: `str` -- used in the OTel `Resource` for `service.name`
- `db_path`: `Path` -- path to the SQLite database for trace persistence

Steps:
1. Create an OTel `Resource` with attributes `{"service.name": "sidestage", "campaign.name": campaign_name}`.
2. Create a `TracerProvider(resource=resource)`.
3. Create the two exporter instances (InMemoryTraceExporter and SQLiteTraceExporter -- these come from Section 03). For now, the function signature accepts them or creates them internally.
4. Wrap `SimpleSpanProcessor(in_memory_exporter)` in a `FilteringSpanProcessor(enabled=config.enabled)`.
5. Wrap `BatchSpanProcessor(sqlite_exporter)` in a `FilteringSpanProcessor(enabled=config.enabled)`.
6. Add both FilteringSpanProcessors to the provider via `provider.add_span_processor(...)`.
7. Call `trace.set_tracer_provider(provider)` to register globally.
8. Store references in module-level `_provider` and `_filtering_processors`.
9. If the SQLite exporter supports it, load recent traces into the in-memory exporter and run retention cleanup (Section 03 concern, called here).
10. Return the provider (and optionally the exporter references, for API endpoints to query).

The function should be idempotent-safe: if called again, it shuts down the previous provider first.

#### toggle_tracing(enabled: bool)

Iterates over `_filtering_processors` and sets `fp.enabled = enabled` on each one. This takes effect immediately for subsequent spans.

Returns the new enabled state for confirmation.

#### shutdown_tracing()

Calls `_provider.shutdown()` if `_provider` is not None. This flushes any pending `BatchSpanProcessor` spans to SQLite. Resets module-level state to None.

Should be called from the `_lifespan` context manager's `finally` block in `SidestageOrchestrator`.

### 3. Convenience Helpers: `src/sidestage/tracing/middleware.py`

#### trace_span(name, attributes=None)

An async-function decorator. Implementation approach:

```python
def trace_span(name: str, attributes: dict | None = None):
    """Decorator that wraps an async function in a span."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("sidestage")
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                return await func(*args, **kwargs)
        return wrapper
    return decorator
```

Key points:
- Uses `functools.wraps` to preserve `__name__`, `__doc__`, `__module__`
- Gets a tracer via `trace.get_tracer("sidestage")` -- safe to call at decoration time or call time
- Only supports async functions (this is intentional per the plan)

#### current_trace_id() -> str | None

Returns the current trace ID as a 32-character hex string, or `None` if no span is active.

```python
def current_trace_id() -> str | None:
    """Get the current trace_id as a hex string, or None if no active span."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id != 0:
        return format(ctx.trace_id, '032x')
    return None
```

The check for `trace_id != 0` distinguishes a real span context from the invalid/default one.

#### add_trace_event(name, attributes=None)

Adds an event to the currently active span, respecting `TraceConfig` capture flags.

Logic:
1. Get the current span via `trace.get_current_span()`. If it is a `NonRecordingSpan` (no-op), return immediately.
2. Get the `TraceConfig` singleton (via `sidestage.config.get().tracing`).
3. Check capture flags:
   - If `name` starts with `"gen_ai.prompt"` or `"gen_ai.completion"` and `config.capture_prompts` is `False`, return.
   - If `name` starts with `"tool."` and `config.capture_tool_args` is `False`, return.
   - If `name` starts with `"memory."` and `config.capture_memory_content` is `False`, return.
4. If `attributes` is provided, iterate and truncate any string value exceeding `config.max_attribute_length`. Truncated strings get `"[truncated]"` appended.
5. Call `span.add_event(name, attributes=attributes)`.

Note: The function accesses config via `sidestage.config.get()` which requires the config singleton to be initialized. In tests, the `_init_config` autouse fixture handles this.

#### record_error(span, exception)

Sets the span status to ERROR and records the exception.

```python
def record_error(span, exception: Exception):
    """Set span status to ERROR and record the exception."""
    span.set_status(trace.StatusCode.ERROR, str(exception))
    span.record_exception(exception)
```

This is a thin convenience wrapper. The `span.record_exception()` call adds a span event with the exception type, message, and traceback.

---

## Integration with Application Lifecycle

After this section is implemented, the `_lifespan` method in `SidestageOrchestrator` (`/home/harald/src/sidestage/src/sidestage/orchestrator.py`) should be updated to call `init_tracing` on startup and `shutdown_tracing` on teardown. This integration is formally part of Section 04 (Backend Instrumentation) or Section 05 (API Endpoints), but the functions are designed to be called as follows:

```python
@asynccontextmanager
async def _lifespan(self, app: FastAPI):
    self._write_pid_file()
    # init_tracing(config.get().tracing, self.active_campaign_name, db_path)
    try:
        yield
    finally:
        # shutdown_tracing()
        self._remove_pid_file()
```

The actual wiring is deferred to later sections. This section just ensures the functions exist and work correctly in isolation.

---

## Key Design Decisions

1. **Single TracerProvider, globally registered.** `trace.set_tracer_provider()` is called exactly once at startup. Modules obtain tracers via `trace.get_tracer("sidestage.<module>")` at any time -- the tracer remains valid regardless of toggle state.

2. **Toggle via FilteringSpanProcessor, not provider swap.** Swapping the global provider at runtime is fraught with race conditions. Instead, the FilteringSpanProcessor's `enabled` flag controls whether spans are actually exported. Spans are always created (minimal overhead: a few object allocations) but discarded at the processor level when disabled.

3. **Two processors, two exporters.** The `SimpleSpanProcessor` wrapping the in-memory exporter is synchronous and never blocks (pure memory operations). The `BatchSpanProcessor` wrapping the SQLite exporter runs in a background thread, keeping synchronous SQLite I/O off the async event loop.

4. **Middleware helpers access config lazily.** The `add_trace_event` function reads `config.get().tracing` at call time, not at import time. This means the config singleton must be initialized before any traced code runs, which is guaranteed by the application startup order.

---

## Dependencies

- **Section 01 (TraceConfig):** The `TraceConfig` Pydantic model must exist on `SidestageConfig.tracing` before this section can be fully tested. Specifically, `add_trace_event` reads `config.get().tracing.capture_prompts`, `.capture_tool_args`, `.capture_memory_content`, and `.max_attribute_length`.

- **Section 03 (Exporters):** The `init_tracing` function creates exporter instances. For this section's tests, mock or stub exporters should be used. The real `InMemoryTraceExporter` and `SQLiteTraceExporter` are implemented in Section 03.

---

## OpenTelemetry SDK Imports Reference

The following imports are needed across the provider and middleware modules:

```python
# provider.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    SpanProcessor,
    SimpleSpanProcessor,
    BatchSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.resources import Resource

# middleware.py
from opentelemetry import trace, context
from opentelemetry.trace import StatusCode
```

These are all available from the `opentelemetry-api` and `opentelemetry-sdk` packages already declared in `pyproject.toml`.