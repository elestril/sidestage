"""Tests for TraceConfig model and its integration with SidestageConfig."""

from typing import Any

import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from sidestage.config import SidestageConfig, TraceConfig
from sidestage import config as sidestage_config


class TestTraceConfigDefaults:
    """TraceConfig defaults are correct."""

    def test_enabled_defaults_false(self):
        tc = TraceConfig()
        assert tc.enabled is False

    def test_otlp_endpoint_defaults(self):
        tc = TraceConfig()
        assert tc.otlp_endpoint == "http://localhost:4318"

    def test_capture_prompts_defaults_true(self):
        tc = TraceConfig()
        assert tc.capture_prompts is True

    def test_capture_tool_args_defaults_true(self):
        tc = TraceConfig()
        assert tc.capture_tool_args is True

    def test_capture_memory_content_defaults_true(self):
        tc = TraceConfig()
        assert tc.capture_memory_content is True

    def test_max_attribute_length_defaults_4096(self):
        tc = TraceConfig()
        assert tc.max_attribute_length == 4096


class TestTraceConfigFromDict:
    """TraceConfig loads from a YAML-style dict with overrides."""

    def test_overrides_enabled(self):
        tc = TraceConfig(enabled=True)
        assert tc.enabled is True

    def test_overrides_otlp_endpoint(self):
        tc = TraceConfig(otlp_endpoint="http://custom:4318")
        assert tc.otlp_endpoint == "http://custom:4318"

    def test_overrides_capture_flags(self):
        tc = TraceConfig(capture_prompts=False, capture_tool_args=False)
        assert tc.capture_prompts is False
        assert tc.capture_tool_args is False

    def test_partial_overrides_keep_other_defaults(self):
        tc = TraceConfig(enabled=True)
        assert tc.capture_prompts is True
        assert tc.capture_tool_args is True
        assert tc.capture_memory_content is True
        assert tc.max_attribute_length == 4096
        assert tc.otlp_endpoint == "http://localhost:4318"


class TestTraceConfigValidation:
    """Validation constraints on TraceConfig fields."""

    def test_max_attribute_length_must_be_positive(self):
        with pytest.raises(ValidationError):
            TraceConfig(max_attribute_length=0)
        with pytest.raises(ValidationError):
            TraceConfig(max_attribute_length=-1)


class TestSidestageConfigTracingIntegration:
    """SidestageConfig includes tracing section properly."""

    def test_sidestage_config_has_tracing_field(self):
        sc = SidestageConfig()
        assert hasattr(sc, "tracing")
        assert isinstance(sc.tracing, TraceConfig)

    def test_sidestage_config_tracing_default(self):
        sc = SidestageConfig()
        assert sc.tracing.enabled is False
        assert sc.tracing.capture_prompts is True
        assert sc.tracing.otlp_endpoint == "http://localhost:4318"

    def test_sidestage_config_serializes_tracing(self):
        sc = SidestageConfig()
        dumped = sc.model_dump()
        assert "tracing" in dumped
        assert dumped["tracing"]["enabled"] is False
        assert dumped["tracing"]["capture_prompts"] is True
        assert dumped["tracing"]["max_attribute_length"] == 4096
        assert dumped["tracing"]["otlp_endpoint"] == "http://localhost:4318"

    def test_sidestage_config_from_dict_with_tracing(self):
        data: dict[str, Any] = {"tracing": {"enabled": True, "otlp_endpoint": "http://viewer:4318"}}
        sc = SidestageConfig(**data)
        assert sc.tracing.enabled is True
        assert sc.tracing.otlp_endpoint == "http://viewer:4318"
        assert sc.tracing.capture_prompts is True  # default preserved

    def test_backward_compat_no_tracing_section(self):
        data: dict[str, Any] = {"loglevel": "DEBUG"}
        sc = SidestageConfig(**data)
        assert sc.tracing.enabled is False
        assert sc.tracing.otlp_endpoint == "http://localhost:4318"

    def test_config_yml_roundtrip(self, tmp_path: Path):
        # Write config with tracing enabled
        config_path = tmp_path / "config.yml"
        sc = SidestageConfig(tracing=TraceConfig(enabled=True, otlp_endpoint="http://viewer:4318"))
        with open(config_path, "w") as f:
            yaml.dump(sc.model_dump(), f, default_flow_style=False)

        # Use init to read it back
        loaded = sidestage_config.init(tmp_path)
        assert loaded.tracing.enabled is True
        assert loaded.tracing.otlp_endpoint == "http://viewer:4318"
        assert loaded.tracing.capture_prompts is True
