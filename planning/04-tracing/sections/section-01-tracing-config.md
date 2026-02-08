Now I have all the context I need. Let me produce the section content.

# Section 01: TraceConfig Model and Configuration

## Overview

This section adds the `TraceConfig` Pydantic model and integrates it into the existing `SidestageConfig` as a `tracing` field. This is the foundational section that all other tracing sections depend on. It involves modifying two existing files and creating a new test file. No other sections need to be completed first.

## Background

Sidestage uses a Pydantic-based configuration system defined in `/home/harald/src/sidestage/src/sidestage/config.py`. The `SidestageConfig` model is loaded from a `config.yml` file via the `config.init(sidestage_dir)` function, which reads YAML, constructs the model, and persists defaults back to disk. A global singleton pattern (`_instance`) provides access via `config.get()`.

The project already depends on `opentelemetry-api` and `opentelemetry-sdk` (see `pyproject.toml`), so no new dependencies are needed.

The existing config pattern for nested models (e.g., `GraphConfig`, `LLMConfig`) is to define a model class, add it as a field on `SidestageConfig` with a `default_factory`, and let Pydantic handle serialization/deserialization.

The existing `conftest.py` at `/home/harald/src/sidestage/tests/conftest.py` provides an `_init_config` autouse fixture that initializes a fresh `SidestageConfig` singleton in a `tmp_path` directory for every test, then clears it after.

## Tests First

Create the test file at `/home/harald/src/sidestage/tests/unit/test_trace_config.py`.

The tests validate:

```python
"""Tests for TraceConfig model and its integration with SidestageConfig."""

import pytest
import yaml
from pathlib import Path

from sidestage.config import SidestageConfig, TraceConfig
from sidestage import config as sidestage_config


class TestTraceConfigDefaults:
    """TraceConfig defaults are correct."""

    def test_enabled_defaults_false(self):
        """enabled field defaults to False."""

    def test_capture_prompts_defaults_true(self):
        """capture_prompts field defaults to True."""

    def test_capture_tool_args_defaults_true(self):
        """capture_tool_args field defaults to True."""

    def test_capture_memory_content_defaults_true(self):
        """capture_memory_content field defaults to True."""

    def test_max_attribute_length_defaults_4096(self):
        """max_attribute_length defaults to 4096."""

    def test_max_traces_in_memory_defaults_500(self):
        """max_traces_in_memory defaults to 500."""

    def test_max_traces_stored_defaults_5000(self):
        """max_traces_stored defaults to 5000."""

    def test_max_trace_age_hours_defaults_72(self):
        """max_trace_age_hours defaults to 72."""


class TestTraceConfigFromDict:
    """TraceConfig loads from a YAML-style dict with overrides."""

    def test_overrides_enabled(self):
        """Construct TraceConfig with enabled=True override."""

    def test_overrides_capture_flags(self):
        """Construct with capture_prompts=False and capture_tool_args=False."""

    def test_overrides_numeric_limits(self):
        """Construct with custom max_traces_in_memory and max_trace_age_hours."""

    def test_partial_overrides_keep_other_defaults(self):
        """Providing only 'enabled' keeps all other fields at defaults."""


class TestTraceConfigValidation:
    """Validation constraints on TraceConfig fields."""

    def test_max_traces_in_memory_must_be_positive(self):
        """max_traces_in_memory rejects zero or negative values."""

    def test_max_trace_age_hours_must_be_positive(self):
        """max_trace_age_hours rejects zero or negative values."""

    def test_max_traces_stored_must_be_positive(self):
        """max_traces_stored rejects zero or negative values."""

    def test_max_attribute_length_must_be_positive(self):
        """max_attribute_length rejects zero or negative values."""


class TestSidestageConfigTracingIntegration:
    """SidestageConfig includes tracing section properly."""

    def test_sidestage_config_has_tracing_field(self):
        """SidestageConfig has a 'tracing' field of type TraceConfig."""

    def test_sidestage_config_tracing_default(self):
        """Default SidestageConfig().tracing is a TraceConfig with defaults."""

    def test_sidestage_config_serializes_tracing(self):
        """model_dump() includes the tracing section with all fields."""

    def test_sidestage_config_from_dict_with_tracing(self):
        """Construct SidestageConfig from a dict containing a tracing section."""

    def test_backward_compat_no_tracing_section(self):
        """config.yml without a 'tracing' key still loads, using TraceConfig defaults."""

    def test_config_yml_roundtrip(self, tmp_path: Path):
        """Write config.yml with tracing section, read it back, values preserved.

        Uses sidestage_config.init(tmp_path) to write, then reads back the YAML
        and verifies the tracing section is present with expected values.
        """
```

## Implementation

### File: `/home/harald/src/sidestage/src/sidestage/config.py`

**Modify this existing file.** Add the `TraceConfig` model class and a new `tracing` field to `SidestageConfig`.

The `TraceConfig` class is a Pydantic `BaseModel` with the following fields:

```python
class TraceConfig(BaseModel):
    """Configuration for the tracing subsystem."""
    enabled: bool = False
    capture_prompts: bool = True
    capture_tool_args: bool = True
    capture_memory_content: bool = True
    max_attribute_length: int = Field(default=4096, ge=1)
    max_traces_in_memory: int = Field(default=500, ge=1)
    max_traces_stored: int = Field(default=5000, ge=1)
    max_trace_age_hours: int = Field(default=72, ge=1)
```

Key design decisions:

- All numeric fields use `ge=1` validation to enforce positive integers. This prevents misconfiguration (e.g., zero-size ring buffers).
- Capture flags (`capture_prompts`, `capture_tool_args`, `capture_memory_content`) default to `True` so that when tracing is turned on, full detail is captured by default. Users can disable individual capture categories for privacy or performance.
- `enabled` defaults to `False` so tracing is opt-in.

Add the field to `SidestageConfig`:

```python
class SidestageConfig(BaseModel):
    # ... existing fields ...
    tracing: TraceConfig = Field(default_factory=TraceConfig, description="Tracing configuration")
```

This follows the same pattern as the existing `graph: GraphConfig` field.

### File: `config.yml` (user-facing)

After this change, running `config.init()` will persist the new `tracing` section to `config.yml` automatically (the existing `init` function writes `config.model_dump()` back to YAML). An existing `config.yml` without a `tracing` section will gain one with all defaults on next startup.

The resulting YAML section will look like:

```yaml
tracing:
  enabled: false
  capture_prompts: true
  capture_tool_args: true
  capture_memory_content: true
  max_attribute_length: 4096
  max_traces_in_memory: 500
  max_traces_stored: 5000
  max_trace_age_hours: 72
```

### Export from config module

Ensure `TraceConfig` is importable from `sidestage.config`:

```python
from sidestage.config import SidestageConfig, TraceConfig
```

This is natural since it is defined in the same `config.py` file.

## Dependencies

- **None.** This is the first section and has no dependencies on other sections.

## Blocked By This Section

- **Section 02 (Tracing Core):** Needs `TraceConfig` to configure the `TracerProvider`, `FilteringSpanProcessor` enabled state, and pass settings to exporters.
- **Section 03 (Exporters):** Needs `max_traces_in_memory`, `max_traces_stored`, `max_trace_age_hours`, and `max_attribute_length` from `TraceConfig`.
- **Section 04 (Backend Instrumentation):** Needs capture flags (`capture_prompts`, `capture_tool_args`, `capture_memory_content`) and `max_attribute_length` from `TraceConfig`.
- **Section 05 (API Endpoints):** Needs `TraceConfig` to return config in the status endpoint.

## Files Summary

| File | Action |
|------|--------|
| `/home/harald/src/sidestage/src/sidestage/config.py` | Modify: add `TraceConfig` class, add `tracing` field to `SidestageConfig` |
| `/home/harald/src/sidestage/tests/unit/test_trace_config.py` | Create: all tests for `TraceConfig` and its integration with `SidestageConfig` |