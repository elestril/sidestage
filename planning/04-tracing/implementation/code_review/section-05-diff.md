diff --git a/src/sidestage/orchestrator.py b/src/sidestage/orchestrator.py
index cfe4f53..89ed971 100644
--- a/src/sidestage/orchestrator.py
+++ b/src/sidestage/orchestrator.py
@@ -14,6 +14,13 @@ import asyncio
 from sidestage.campaign import Campaign
 from sidestage.sync import SyncManager
 from sidestage.health import HealthStatus
+from sidestage.tracing import (
+    toggle_tracing,
+    shutdown_tracing,
+    get_tracing_enabled,
+    get_in_memory_exporter,
+    get_sqlite_exporter,
+)
 from sidestage.migration.models import (
     MigrationImportRequest,
     MigrationImportResponse,
@@ -91,6 +98,7 @@ class SidestageOrchestrator:
         try:
             yield
         finally:
+            shutdown_tracing()
             self._remove_pid_file()
 
     def _write_pid_file(self) -> None:
@@ -385,6 +393,64 @@ class SidestageOrchestrator:
             
             return ChatResponse(user_message=user_msg)
 
+        # --- Tracing endpoints ---
+
+        @self.fastapi_app.get("/v1/traces")
+        async def list_traces(
+            scene_id: str | None = None,
+            event_id: str | None = None,
+            limit: int = 50,
+            offset: int = 0,
+        ):
+            """List trace summaries, optionally filtered."""
+            sqlite_exp = get_sqlite_exporter()
+            if sqlite_exp is None:
+                return []
+            return sqlite_exp.query_traces(
+                scene_id=scene_id, event_id=event_id, limit=limit, offset=offset,
+            )
+
+        @self.fastapi_app.get("/v1/traces/{trace_id}")
+        async def get_trace_detail(trace_id: str):
+            """Return full trace with all spans."""
+            # Try in-memory first
+            mem_exp = get_in_memory_exporter()
+            if mem_exp is not None:
+                spans = mem_exp.get_trace(trace_id)
+                if spans is not None:
+                    return {"trace_id": trace_id, "spans": spans}
+
+            # Fall back to SQLite
+            sqlite_exp = get_sqlite_exporter()
+            if sqlite_exp is not None:
+                spans = sqlite_exp.query_spans(trace_id)
+                if spans:
+                    return {"trace_id": trace_id, "spans": spans}
+
+            raise HTTPException(status_code=404, detail="Trace not found")
+
+        @self.fastapi_app.post("/v1/tracing/toggle")
+        async def toggle_tracing_endpoint(body: dict):
+            """Toggle tracing on or off."""
+            enabled = body.get("enabled", True)
+            result = toggle_tracing(enabled)
+            return {"tracing_enabled": result}
+
+        @self.fastapi_app.get("/v1/tracing/status")
+        async def get_tracing_status():
+            """Return current tracing status."""
+            from sidestage import config as sidestage_config
+            trace_config = sidestage_config.get().tracing
+
+            mem_exp = get_in_memory_exporter()
+            trace_count = len(mem_exp.get_traces()) if mem_exp is not None else 0
+
+            return {
+                "enabled": get_tracing_enabled(),
+                "config": trace_config.model_dump(),
+                "trace_count": trace_count,
+            }
+
         # Redirect root to /sidestage
         @self.fastapi_app.get("/")
         async def root_redirect():
diff --git a/src/sidestage/tracing/__init__.py b/src/sidestage/tracing/__init__.py
index 9cd3b81..015e6bd 100644
--- a/src/sidestage/tracing/__init__.py
+++ b/src/sidestage/tracing/__init__.py
@@ -4,6 +4,16 @@ Public API:
     init_tracing(config, campaign_name, db_path) -- set up TracerProvider and exporters
     toggle_tracing(enabled) -- flip tracing on/off at runtime
     shutdown_tracing() -- flush pending spans and shut down the provider
+    get_tracing_enabled() -- check current tracing state
+    get_in_memory_exporter() -- access the in-memory exporter
+    get_sqlite_exporter() -- access the SQLite exporter
 """
 
-from sidestage.tracing.provider import init_tracing, toggle_tracing, shutdown_tracing
+from sidestage.tracing.provider import (
+    init_tracing,
+    toggle_tracing,
+    shutdown_tracing,
+    get_tracing_enabled,
+    get_in_memory_exporter,
+    get_sqlite_exporter,
+)
diff --git a/src/sidestage/tracing/provider.py b/src/sidestage/tracing/provider.py
index f5f95e3..4192296 100644
--- a/src/sidestage/tracing/provider.py
+++ b/src/sidestage/tracing/provider.py
@@ -25,6 +25,7 @@ logger = logging.getLogger(__name__)
 _provider: TracerProvider | None = None
 _filtering_processors: list["FilteringSpanProcessor"] = []
 _in_memory_exporter: SpanExporter | None = None
+_sqlite_exporter: SpanExporter | None = None
 
 
 class FilteringSpanProcessor(SpanProcessor):
@@ -69,7 +70,7 @@ def init_tracing(
     Returns:
         The configured TracerProvider
     """
-    global _provider, _filtering_processors, _in_memory_exporter
+    global _provider, _filtering_processors, _in_memory_exporter, _sqlite_exporter
 
     # Shutdown previous provider if re-initializing
     if _provider is not None:
@@ -83,6 +84,7 @@ def init_tracing(
     provider = TracerProvider(resource=resource)
     _filtering_processors = []
     _in_memory_exporter = in_memory_exporter
+    _sqlite_exporter = sqlite_exporter
 
     if in_memory_exporter is None and sqlite_exporter is None:
         logger.warning("No exporters provided -- all trace data will be lost")
@@ -116,6 +118,18 @@ def get_in_memory_exporter() -> SpanExporter | None:
     return _in_memory_exporter
 
 
+def get_sqlite_exporter() -> SpanExporter | None:
+    """Return the SQLite exporter reference, or None if not initialized."""
+    return _sqlite_exporter
+
+
+def get_tracing_enabled() -> bool:
+    """Return current tracing enabled state."""
+    if not _filtering_processors:
+        return False
+    return _filtering_processors[0].enabled
+
+
 def toggle_tracing(enabled: bool) -> bool:
     """Flip tracing on/off at runtime.
 
