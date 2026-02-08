diff --git a/sidestage.dev/config.yml b/sidestage.dev/config.yml
index e8e5816..f218283 100644
--- a/sidestage.dev/config.yml
+++ b/sidestage.dev/config.yml
@@ -21,3 +21,12 @@ llms:
     model: embed
     provider: llama_cpp
 loglevel: DEBUG
+tracing:
+  capture_memory_content: true
+  capture_prompts: true
+  capture_tool_args: true
+  enabled: false
+  max_attribute_length: 4096
+  max_trace_age_hours: 72
+  max_traces_in_memory: 500
+  max_traces_stored: 5000
diff --git a/src/sidestage/config.py b/src/sidestage/config.py
index aaaa0a1..d769696 100644
--- a/src/sidestage/config.py
+++ b/src/sidestage/config.py
@@ -19,6 +19,18 @@ class LLMConfig(BaseModel):
     memory_token_budget: int | None = Field(default=None, ge=1, description="Tokens allocated for memory context (optional override)")
 
 
+class TraceConfig(BaseModel):
+    """Configuration for the tracing subsystem."""
+    enabled: bool = False
+    capture_prompts: bool = True
+    capture_tool_args: bool = True
+    capture_memory_content: bool = True
+    max_attribute_length: int = Field(default=4096, ge=1)
+    max_traces_in_memory: int = Field(default=500, ge=1)
+    max_traces_stored: int = Field(default=5000, ge=1)
+    max_trace_age_hours: int = Field(default=72, ge=1)
+
+
 class SidestageConfig(BaseModel):
     """Configuration model for Sidestage settings."""
     loglevel: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@@ -31,6 +43,9 @@ class SidestageConfig(BaseModel):
     # Graph Database Configuration
     graph: GraphConfig = Field(default_factory=GraphConfig, description="FalkorDB graph database configuration")
 
+    # Tracing Configuration
+    tracing: TraceConfig = Field(default_factory=TraceConfig, description="Tracing configuration")
+
 
 _instance: Optional[SidestageConfig] = None
 
diff --git a/tests/unit/test_trace_config.py b/tests/unit/test_trace_config.py
new file mode 100644
index 0000000..58ee891
--- /dev/null
+++ b/tests/unit/test_trace_config.py
@@ -0,0 +1,149 @@
+"""Tests for TraceConfig model and its integration with SidestageConfig."""
+
+import pytest
+import yaml
+from pathlib import Path
+
+from sidestage.config import SidestageConfig, TraceConfig
+from sidestage import config as sidestage_config
+
+
+class TestTraceConfigDefaults:
+    """TraceConfig defaults are correct."""
+
+    def test_enabled_defaults_false(self):
+        tc = TraceConfig()
+        assert tc.enabled is False
+
+    def test_capture_prompts_defaults_true(self):
+        tc = TraceConfig()
+        assert tc.capture_prompts is True
+
+    def test_capture_tool_args_defaults_true(self):
+        tc = TraceConfig()
+        assert tc.capture_tool_args is True
+
+    def test_capture_memory_content_defaults_true(self):
+        tc = TraceConfig()
+        assert tc.capture_memory_content is True
+
+    def test_max_attribute_length_defaults_4096(self):
+        tc = TraceConfig()
+        assert tc.max_attribute_length == 4096
+
+    def test_max_traces_in_memory_defaults_500(self):
+        tc = TraceConfig()
+        assert tc.max_traces_in_memory == 500
+
+    def test_max_traces_stored_defaults_5000(self):
+        tc = TraceConfig()
+        assert tc.max_traces_stored == 5000
+
+    def test_max_trace_age_hours_defaults_72(self):
+        tc = TraceConfig()
+        assert tc.max_trace_age_hours == 72
+
+
+class TestTraceConfigFromDict:
+    """TraceConfig loads from a YAML-style dict with overrides."""
+
+    def test_overrides_enabled(self):
+        tc = TraceConfig(enabled=True)
+        assert tc.enabled is True
+
+    def test_overrides_capture_flags(self):
+        tc = TraceConfig(capture_prompts=False, capture_tool_args=False)
+        assert tc.capture_prompts is False
+        assert tc.capture_tool_args is False
+
+    def test_overrides_numeric_limits(self):
+        tc = TraceConfig(max_traces_in_memory=100, max_trace_age_hours=24)
+        assert tc.max_traces_in_memory == 100
+        assert tc.max_trace_age_hours == 24
+
+    def test_partial_overrides_keep_other_defaults(self):
+        tc = TraceConfig(enabled=True)
+        assert tc.capture_prompts is True
+        assert tc.capture_tool_args is True
+        assert tc.capture_memory_content is True
+        assert tc.max_attribute_length == 4096
+        assert tc.max_traces_in_memory == 500
+        assert tc.max_traces_stored == 5000
+        assert tc.max_trace_age_hours == 72
+
+
+class TestTraceConfigValidation:
+    """Validation constraints on TraceConfig fields."""
+
+    def test_max_traces_in_memory_must_be_positive(self):
+        with pytest.raises(Exception):
+            TraceConfig(max_traces_in_memory=0)
+        with pytest.raises(Exception):
+            TraceConfig(max_traces_in_memory=-1)
+
+    def test_max_trace_age_hours_must_be_positive(self):
+        with pytest.raises(Exception):
+            TraceConfig(max_trace_age_hours=0)
+        with pytest.raises(Exception):
+            TraceConfig(max_trace_age_hours=-1)
+
+    def test_max_traces_stored_must_be_positive(self):
+        with pytest.raises(Exception):
+            TraceConfig(max_traces_stored=0)
+        with pytest.raises(Exception):
+            TraceConfig(max_traces_stored=-1)
+
+    def test_max_attribute_length_must_be_positive(self):
+        with pytest.raises(Exception):
+            TraceConfig(max_attribute_length=0)
+        with pytest.raises(Exception):
+            TraceConfig(max_attribute_length=-1)
+
+
+class TestSidestageConfigTracingIntegration:
+    """SidestageConfig includes tracing section properly."""
+
+    def test_sidestage_config_has_tracing_field(self):
+        sc = SidestageConfig()
+        assert hasattr(sc, "tracing")
+        assert isinstance(sc.tracing, TraceConfig)
+
+    def test_sidestage_config_tracing_default(self):
+        sc = SidestageConfig()
+        assert sc.tracing.enabled is False
+        assert sc.tracing.capture_prompts is True
+        assert sc.tracing.max_traces_in_memory == 500
+
+    def test_sidestage_config_serializes_tracing(self):
+        sc = SidestageConfig()
+        dumped = sc.model_dump()
+        assert "tracing" in dumped
+        assert dumped["tracing"]["enabled"] is False
+        assert dumped["tracing"]["capture_prompts"] is True
+        assert dumped["tracing"]["max_attribute_length"] == 4096
+
+    def test_sidestage_config_from_dict_with_tracing(self):
+        data = {"tracing": {"enabled": True, "max_traces_in_memory": 200}}
+        sc = SidestageConfig(**data)
+        assert sc.tracing.enabled is True
+        assert sc.tracing.max_traces_in_memory == 200
+        assert sc.tracing.capture_prompts is True  # default preserved
+
+    def test_backward_compat_no_tracing_section(self):
+        data = {"loglevel": "DEBUG"}
+        sc = SidestageConfig(**data)
+        assert sc.tracing.enabled is False
+        assert sc.tracing.max_traces_in_memory == 500
+
+    def test_config_yml_roundtrip(self, tmp_path: Path):
+        # Write config with tracing enabled
+        config_path = tmp_path / "config.yml"
+        sc = SidestageConfig(tracing=TraceConfig(enabled=True, max_traces_in_memory=200))
+        with open(config_path, "w") as f:
+            yaml.dump(sc.model_dump(), f, default_flow_style=False)
+
+        # Use init to read it back
+        loaded = sidestage_config.init(tmp_path)
+        assert loaded.tracing.enabled is True
+        assert loaded.tracing.max_traces_in_memory == 200
+        assert loaded.tracing.capture_prompts is True
