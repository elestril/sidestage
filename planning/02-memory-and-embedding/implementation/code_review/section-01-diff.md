diff --git a/src/sidestage/campaign.py b/src/sidestage/campaign.py
index 5f783d9..36a38a4 100644
--- a/src/sidestage/campaign.py
+++ b/src/sidestage/campaign.py
@@ -26,6 +26,8 @@ class LLMConfig(BaseModel):
     base_url: str = Field(default="http://localhost:8080/v1", description="Base URL for OpenAI-compatible API")
     api_key: str = Field(default="sk-no-key-required", description="API key")
     model: str = Field(default="default", description="Model name to request")
+    context_limit: int | None = Field(default=None, description="Max context tokens (validated at startup)")
+    memory_token_budget: int | None = Field(default=None, description="Tokens allocated for memory context (optional override)")
 
 class SidestageConfig(BaseModel):
     """Configuration model for Sidestage settings."""
diff --git a/src/sidestage/graph/client.py b/src/sidestage/graph/client.py
index d19dcda..329eaae 100644
--- a/src/sidestage/graph/client.py
+++ b/src/sidestage/graph/client.py
@@ -23,6 +23,7 @@ class GraphConfig:
     password: str | None = None
     max_connections: int = 16
     graph_name: str | None = None
+    vector_dimension: int | None = None
 
 
 class GraphClient:
diff --git a/src/sidestage/health.py b/src/sidestage/health.py
new file mode 100644
index 0000000..379db16
--- /dev/null
+++ b/src/sidestage/health.py
@@ -0,0 +1,42 @@
+"""Campaign health status tracking with transition callbacks."""
+
+from __future__ import annotations
+
+from collections.abc import Awaitable, Callable
+from enum import Enum
+
+
+class HealthStatus(str, Enum):
+    HEALTHY = "healthy"
+    DEGRADED = "degraded"
+    UNHEALTHY = "unhealthy"
+
+
+class CampaignHealth:
+    """Manages campaign health status with transition logic."""
+
+    def __init__(
+        self,
+        on_change: Callable[[HealthStatus, str], Awaitable[None]] | None = None,
+    ):
+        self.status = HealthStatus.HEALTHY
+        self.reason = ""
+        self._on_change = on_change
+
+    async def set_status(self, status: HealthStatus, reason: str) -> None:
+        """Transition to a new status, firing on_change if status actually changed."""
+        changed = status != self.status
+        self.status = status
+        self.reason = reason
+        if changed and self._on_change is not None:
+            await self._on_change(status, reason)
+
+    @property
+    def is_accepting_chat(self) -> bool:
+        """True if HEALTHY or DEGRADED."""
+        return self.status != HealthStatus.UNHEALTHY
+
+    @property
+    def is_embedding_available(self) -> bool:
+        """True only if HEALTHY."""
+        return self.status == HealthStatus.HEALTHY
diff --git a/src/sidestage/memory/__init__.py b/src/sidestage/memory/__init__.py
new file mode 100644
index 0000000..00a818f
--- /dev/null
+++ b/src/sidestage/memory/__init__.py
@@ -0,0 +1,3 @@
+"""Sidestage memory system -- living text documents stored as graph nodes."""
+
+from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
diff --git a/src/sidestage/memory/models.py b/src/sidestage/memory/models.py
new file mode 100644
index 0000000..3c439fd
--- /dev/null
+++ b/src/sidestage/memory/models.py
@@ -0,0 +1,41 @@
+"""Core memory data types for the sidestage memory system."""
+
+from __future__ import annotations
+
+from enum import Enum
+
+from pydantic import BaseModel
+
+
+class MemoryType(str, Enum):
+    SCENE = "scene"
+    CHARACTER = "character"
+    WORLD_FACT = "world_fact"
+
+
+class Memory(BaseModel):
+    id: str
+    content: str
+    memory_type: MemoryType
+    visibility: str
+    embedding: list[float] | None
+    owner_id: str | None
+    target_id: str
+    created_at: float
+    updated_at: float
+    gametime: int | None
+    access_count: int
+    last_accessed_at: float | None
+
+
+class ContextResult(BaseModel):
+    memory_text: str
+    chat_text: str
+    token_estimate: int
+
+
+class ContextMemories(BaseModel):
+    common_scene_memory: Memory | None
+    private_scene_memory: Memory | None
+    character_memories: dict[str, Memory]
+    world_facts: list[Memory]
diff --git a/tests/unit/test_campaign_config.py b/tests/unit/test_campaign_config.py
new file mode 100644
index 0000000..7fafc1c
--- /dev/null
+++ b/tests/unit/test_campaign_config.py
@@ -0,0 +1,53 @@
+"""Tests for LLMConfig and GraphConfig extensions."""
+
+import pytest
+
+from sidestage.campaign import LLMConfig, SidestageConfig
+from sidestage.graph.client import GraphConfig
+
+
+class TestLLMConfigExtensions:
+    def test_accepts_context_limit(self):
+        cfg = LLMConfig(context_limit=16384)
+        assert cfg.context_limit == 16384
+
+    def test_accepts_memory_token_budget(self):
+        cfg = LLMConfig(memory_token_budget=2000)
+        assert cfg.memory_token_budget == 2000
+
+    def test_defaults_to_none(self):
+        cfg = LLMConfig()
+        assert cfg.context_limit is None
+        assert cfg.memory_token_budget is None
+
+
+class TestGraphConfigExtensions:
+    def test_accepts_vector_dimension(self):
+        cfg = GraphConfig(vector_dimension=384)
+        assert cfg.vector_dimension == 384
+
+    def test_defaults_to_none(self):
+        cfg = GraphConfig()
+        assert cfg.vector_dimension is None
+
+
+class TestSidestageConfigSerialization:
+    def test_includes_new_fields(self):
+        config = SidestageConfig(
+            llms={"default": LLMConfig(context_limit=16384, memory_token_budget=2000)},
+            graph=GraphConfig(vector_dimension=384),
+        )
+        dumped = config.model_dump()
+        assert dumped["llms"]["default"]["context_limit"] == 16384
+        assert dumped["llms"]["default"]["memory_token_budget"] == 2000
+        assert dumped["graph"]["vector_dimension"] == 384
+
+    def test_backwards_compat_no_new_fields(self):
+        data = {
+            "llms": {"default": {"provider": "llama_cpp"}},
+            "graph": {"host": "localhost"},
+        }
+        config = SidestageConfig(**data)
+        assert config.llms["default"].context_limit is None
+        assert config.llms["default"].memory_token_budget is None
+        assert config.graph.vector_dimension is None
diff --git a/tests/unit/test_health.py b/tests/unit/test_health.py
new file mode 100644
index 0000000..c0b7718
--- /dev/null
+++ b/tests/unit/test_health.py
@@ -0,0 +1,78 @@
+"""Tests for CampaignHealth and HealthStatus."""
+
+import pytest
+from unittest.mock import AsyncMock
+
+from sidestage.health import HealthStatus, CampaignHealth
+
+
+class TestHealthStatus:
+    def test_enum_values(self):
+        assert HealthStatus.HEALTHY == "healthy"
+        assert HealthStatus.DEGRADED == "degraded"
+        assert HealthStatus.UNHEALTHY == "unhealthy"
+
+
+class TestCampaignHealth:
+    def test_initializes_healthy(self):
+        health = CampaignHealth()
+        assert health.status == HealthStatus.HEALTHY
+
+    @pytest.mark.anyio
+    async def test_set_status_transitions(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.DEGRADED, "embed down")
+        assert health.status == HealthStatus.DEGRADED
+        assert health.reason == "embed down"
+
+    @pytest.mark.anyio
+    async def test_set_status_fires_on_change(self):
+        callback = AsyncMock()
+        health = CampaignHealth(on_change=callback)
+        await health.set_status(HealthStatus.DEGRADED, "embed down")
+        callback.assert_awaited_once_with(HealthStatus.DEGRADED, "embed down")
+
+    @pytest.mark.anyio
+    async def test_set_status_no_fire_when_unchanged(self):
+        callback = AsyncMock()
+        health = CampaignHealth(on_change=callback)
+        await health.set_status(HealthStatus.HEALTHY, "still fine")
+        callback.assert_not_awaited()
+
+    @pytest.mark.anyio
+    async def test_set_status_works_without_callback(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.DEGRADED, "no callback")
+        assert health.status == HealthStatus.DEGRADED
+
+    def test_is_accepting_chat_healthy(self):
+        health = CampaignHealth()
+        assert health.is_accepting_chat is True
+
+    @pytest.mark.anyio
+    async def test_is_accepting_chat_degraded(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.DEGRADED, "degraded")
+        assert health.is_accepting_chat is True
+
+    @pytest.mark.anyio
+    async def test_is_accepting_chat_unhealthy(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.UNHEALTHY, "db down")
+        assert health.is_accepting_chat is False
+
+    def test_is_embedding_available_healthy(self):
+        health = CampaignHealth()
+        assert health.is_embedding_available is True
+
+    @pytest.mark.anyio
+    async def test_is_embedding_available_degraded(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.DEGRADED, "degraded")
+        assert health.is_embedding_available is False
+
+    @pytest.mark.anyio
+    async def test_is_embedding_available_unhealthy(self):
+        health = CampaignHealth()
+        await health.set_status(HealthStatus.UNHEALTHY, "db down")
+        assert health.is_embedding_available is False
diff --git a/tests/unit/test_memory_models.py b/tests/unit/test_memory_models.py
new file mode 100644
index 0000000..ac84d9f
--- /dev/null
+++ b/tests/unit/test_memory_models.py
@@ -0,0 +1,125 @@
+"""Tests for memory models: Memory, MemoryType, ContextResult, ContextMemories."""
+
+import time
+import uuid
+
+import pytest
+
+from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
+
+
+class TestMemoryType:
+    def test_enum_values(self):
+        assert MemoryType.SCENE == "scene"
+        assert MemoryType.CHARACTER == "character"
+        assert MemoryType.WORLD_FACT == "world_fact"
+
+
+class TestMemory:
+    def _make_memory(self, **overrides):
+        defaults = {
+            "id": str(uuid.uuid4()),
+            "content": "The tavern is dimly lit.",
+            "memory_type": MemoryType.SCENE,
+            "visibility": "common",
+            "embedding": None,
+            "owner_id": None,
+            "target_id": "scene_001",
+            "created_at": time.time(),
+            "updated_at": time.time(),
+            "gametime": None,
+            "access_count": 0,
+            "last_accessed_at": None,
+        }
+        defaults.update(overrides)
+        return Memory(**defaults)
+
+    def test_all_required_fields(self):
+        mem = self._make_memory()
+        assert mem.content == "The tavern is dimly lit."
+        assert mem.memory_type == MemoryType.SCENE
+
+    def test_optional_fields_accept_none(self):
+        mem = self._make_memory(
+            embedding=None, owner_id=None, gametime=None, last_accessed_at=None
+        )
+        assert mem.embedding is None
+        assert mem.owner_id is None
+        assert mem.gametime is None
+        assert mem.last_accessed_at is None
+
+    def test_common_visibility_no_owner(self):
+        mem = self._make_memory(visibility="common", owner_id=None)
+        assert mem.visibility == "common"
+        assert mem.owner_id is None
+
+    def test_private_visibility_with_owner(self):
+        mem = self._make_memory(visibility="private", owner_id="char_001")
+        assert mem.visibility == "private"
+        assert mem.owner_id == "char_001"
+
+    def test_serialization_roundtrip(self):
+        mem = self._make_memory(embedding=[0.1, 0.2, 0.3])
+        dumped = mem.model_dump()
+        restored = Memory(**dumped)
+        assert restored == mem
+
+
+class TestContextResult:
+    def test_fields_accessible(self):
+        cr = ContextResult(
+            memory_text="World facts here.",
+            chat_text="Recent chat here.",
+            token_estimate=150,
+        )
+        assert cr.memory_text == "World facts here."
+        assert cr.chat_text == "Recent chat here."
+        assert cr.token_estimate == 150
+
+
+class TestContextMemories:
+    def _make_memory(self, **overrides):
+        defaults = {
+            "id": str(uuid.uuid4()),
+            "content": "test content",
+            "memory_type": MemoryType.SCENE,
+            "visibility": "common",
+            "embedding": None,
+            "owner_id": None,
+            "target_id": "scene_001",
+            "created_at": time.time(),
+            "updated_at": time.time(),
+            "gametime": None,
+            "access_count": 0,
+            "last_accessed_at": None,
+        }
+        defaults.update(overrides)
+        return Memory(**defaults)
+
+    def test_groups_memories_correctly(self):
+        common = self._make_memory(content="common scene")
+        private = self._make_memory(content="private scene", visibility="private", owner_id="char_1")
+        char_mem = self._make_memory(content="char memory", memory_type=MemoryType.CHARACTER)
+        fact = self._make_memory(content="world fact", memory_type=MemoryType.WORLD_FACT)
+
+        cm = ContextMemories(
+            common_scene_memory=common,
+            private_scene_memory=private,
+            character_memories={"char_1": char_mem},
+            world_facts=[fact],
+        )
+        assert cm.common_scene_memory.content == "common scene"
+        assert cm.private_scene_memory.content == "private scene"
+        assert cm.character_memories["char_1"].content == "char memory"
+        assert len(cm.world_facts) == 1
+        assert cm.world_facts[0].content == "world fact"
+
+    def test_none_scene_memories(self):
+        cm = ContextMemories(
+            common_scene_memory=None,
+            private_scene_memory=None,
+            character_memories={},
+            world_facts=[],
+        )
+        assert cm.common_scene_memory is None
+        assert cm.private_scene_memory is None
