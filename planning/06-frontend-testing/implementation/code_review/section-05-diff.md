diff --git a/scripts/run-dev.sh b/scripts/run-dev.sh
index 7f2c3d5..ee3281d 100755
--- a/scripts/run-dev.sh
+++ b/scripts/run-dev.sh
@@ -16,5 +16,10 @@ if [ ! -d "./$CAMPAIGN" ]; then
   cp -rp ../data/dev_campaign/ "$CAMPAIGN"
 fi
 
-exec uv run sidestage --sidestage_dir . "$CAMPAIGN"
+PORT_ARGS=""
+if [ -n "${SIDESTAGE_PORT:-}" ]; then
+  PORT_ARGS="--port $SIDESTAGE_PORT"
+fi
+
+exec uv run sidestage --sidestage_dir . $PORT_ARGS "$CAMPAIGN"
 
diff --git a/src/sidestage/actors.py b/src/sidestage/actors.py
index 3bb8758..84c4ee0 100644
--- a/src/sidestage/actors.py
+++ b/src/sidestage/actors.py
@@ -72,6 +72,13 @@ class NPCActor(Actor):
 
     def _update_prompt(self) -> None:
         """Load the appropriate prompt template and instantiate the LiteLLMAgent."""
+        import os
+        if os.environ.get("SIDESTAGE_MOCK_AGENT"):
+            from sidestage.testing.mock_actor import MockLLMAgent
+            char_name = self.character.name if self.character else "NPC"
+            self.agent = MockLLMAgent(name=char_name)
+            return
+
         from sidestage.agent import LiteLLMAgent
 
         project_root = Path(__file__).parent.parent.parent
diff --git a/src/sidestage/orchestrator.py b/src/sidestage/orchestrator.py
index 0fc5780..fe14952 100644
--- a/src/sidestage/orchestrator.py
+++ b/src/sidestage/orchestrator.py
@@ -451,6 +451,11 @@ class SidestageOrchestrator:
                 "error": get_tracing_error(),
             }
 
+        # Test-only routes (mock agent configuration)
+        if os.environ.get("SIDESTAGE_MOCK_AGENT"):
+            from sidestage.testing.routes import register_test_routes
+            register_test_routes(self.fastapi_app, self)
+
         # Redirect root to /sidestage
         @self.fastapi_app.get("/")
         async def root_redirect() -> RedirectResponse:
diff --git a/src/sidestage/server.py b/src/sidestage/server.py
index 26cbaaa..070df3a 100644
--- a/src/sidestage/server.py
+++ b/src/sidestage/server.py
@@ -95,6 +95,8 @@ def main():
     logger.info(f"Starting Sidestage Server on {args.host}:{args.port} (reload={'enabled' if use_reload else 'disabled'})...")
     logger.info(f"Campaign data: {os.path.abspath(os.path.join(args.sidestage_dir, args.campaign))}")
 
+    port = int(os.environ.get("SIDESTAGE_PORT", str(args.port)))
+
     reload_kwargs: dict[str, object] = {}
     if use_reload:
         reload_kwargs["reload"] = True
@@ -102,7 +104,7 @@ def main():
 
     try:
         uvicorn.run("sidestage.server:get_app",
-                    host=args.host, port=args.port,
+                    host=args.host, port=port,
                     factory=True,
                     log_config=None,
                     **reload_kwargs)
diff --git a/src/sidestage/testing/__init__.py b/src/sidestage/testing/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/src/sidestage/testing/mock_actor.py b/src/sidestage/testing/mock_actor.py
new file mode 100644
index 0000000..38e10bd
--- /dev/null
+++ b/src/sidestage/testing/mock_actor.py
@@ -0,0 +1,47 @@
+"""Mock LLM agent for deterministic E2E testing."""
+
+import anyio
+from dataclasses import dataclass, field
+
+from sidestage.agent import AgentResponse
+
+
+@dataclass
+class MockResponse:
+    """A canned response for the mock agent."""
+
+    body: str = "Mock response"
+    character_id: str | None = None
+    actor_id: str = "agent:co_author"
+    event_type: str = "ChatMessage"
+    delay: float = 0.5
+
+
+class MockLLMAgent:
+    """Minimal stand-in for LiteLLMAgent that returns canned responses.
+
+    Duck-typed replacement implementing the same ``arun()`` interface.
+    """
+
+    def __init__(
+        self,
+        name: str = "MockAgent",
+        default_response: str = "Mock response",
+        response_delay: float = 0.1,
+    ):
+        self.name = name
+        self.responses: list[MockResponse] = []
+        self.default_response = default_response
+        self.response_delay = response_delay
+
+    async def arun(
+        self, message: str, context: str | None = None, stream: bool = False
+    ) -> AgentResponse:
+        """Return the next queued response or the default."""
+        if self.responses:
+            resp = self.responses.pop(0)
+            await anyio.sleep(resp.delay)
+            return AgentResponse(content=resp.body)
+
+        await anyio.sleep(self.response_delay)
+        return AgentResponse(content=self.default_response)
diff --git a/src/sidestage/testing/routes.py b/src/sidestage/testing/routes.py
new file mode 100644
index 0000000..b3ad676
--- /dev/null
+++ b/src/sidestage/testing/routes.py
@@ -0,0 +1,60 @@
+"""Test-only API routes for mock agent configuration."""
+
+from __future__ import annotations
+
+from typing import TYPE_CHECKING, Any
+
+from fastapi import FastAPI
+from pydantic import BaseModel
+
+from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
+
+if TYPE_CHECKING:
+    from sidestage.orchestrator import SidestageOrchestrator
+
+
+class MockAgentConfigureRequest(BaseModel):
+    responses: list[dict[str, Any]] = []
+    default_response: str | None = None
+    response_delay: float | None = None
+
+
+def _find_mock_agents(orchestrator: SidestageOrchestrator) -> list[MockLLMAgent]:
+    """Traverse active scenes and return all MockLLMAgent instances."""
+    agents: list[MockLLMAgent] = []
+    for scene in orchestrator.active_scenes.values():
+        for character in scene.characters.values():
+            actor = character.actor
+            if actor is not None and isinstance(getattr(actor, "agent", None), MockLLMAgent):
+                agents.append(actor.agent)
+    return agents
+
+
+def register_test_routes(app: FastAPI, orchestrator: SidestageOrchestrator) -> None:
+    """Register test-only API routes for mock agent configuration.
+
+    Only call this when SIDESTAGE_MOCK_AGENT is set.
+    """
+
+    @app.post("/v1/test/mock-agent/configure")
+    async def configure_mock_agent(request: MockAgentConfigureRequest) -> dict[str, Any]:
+        agents = _find_mock_agents(orchestrator)
+        for agent in agents:
+            if request.responses:
+                agent.responses = [
+                    MockResponse(**r) for r in request.responses
+                ]
+            if request.default_response is not None:
+                agent.default_response = request.default_response
+            if request.response_delay is not None:
+                agent.response_delay = request.response_delay
+        return {"status": "ok", "agents_configured": len(agents)}
+
+    @app.post("/v1/test/mock-agent/reset")
+    async def reset_mock_agent() -> dict[str, Any]:
+        agents = _find_mock_agents(orchestrator)
+        for agent in agents:
+            agent.responses = []
+            agent.default_response = "Mock response"
+            agent.response_delay = 0.1
+        return {"status": "ok", "agents_reset": len(agents)}
diff --git a/tests/unit/test_mock_actor.py b/tests/unit/test_mock_actor.py
new file mode 100644
index 0000000..58025d1
--- /dev/null
+++ b/tests/unit/test_mock_actor.py
@@ -0,0 +1,74 @@
+"""Tests for the MockLLMAgent class."""
+
+import asyncio
+import time
+import pytest
+from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
+
+
+@pytest.mark.anyio
+async def test_arun_returns_next_response_from_queue():
+    """MockLLMAgent.arun() should pop and return the first response from the queue."""
+    agent = MockLLMAgent(name="test")
+    agent.responses = [
+        MockResponse(body="first"),
+        MockResponse(body="second"),
+    ]
+    result = await agent.arun("hello")
+    assert result.content == "first"
+    result2 = await agent.arun("hello again")
+    assert result2.content == "second"
+
+
+@pytest.mark.anyio
+async def test_arun_uses_default_response_when_queue_empty():
+    """When the response queue is empty, arun() should return default_response."""
+    agent = MockLLMAgent(name="test")
+    result = await agent.arun("hello")
+    assert result.content == "Mock response"
+
+
+@pytest.mark.anyio
+async def test_arun_waits_response_delay_before_returning():
+    """arun() should wait response_delay seconds before returning (simulates LLM thinking)."""
+    agent = MockLLMAgent(name="test", response_delay=0.2)
+    start = time.monotonic()
+    await agent.arun("hello")
+    elapsed = time.monotonic() - start
+    assert elapsed >= 0.15  # allow small tolerance
+
+
+@pytest.mark.anyio
+async def test_arun_uses_per_response_delay():
+    """arun() should use the per-response delay when a queued response has one."""
+    agent = MockLLMAgent(name="test", response_delay=0.01)
+    agent.responses = [MockResponse(body="slow", delay=0.2)]
+    start = time.monotonic()
+    await agent.arun("hello")
+    elapsed = time.monotonic() - start
+    assert elapsed >= 0.15
+
+
+@pytest.mark.anyio
+async def test_arun_returns_response_with_correct_content():
+    """The returned AgentResponse should have the MockResponse's body as content."""
+    agent = MockLLMAgent(name="test")
+    agent.responses = [MockResponse(body="custom text")]
+    result = await agent.arun("hello")
+    assert result.content == "custom text"
+
+
+def test_mock_response_defaults():
+    """MockResponse should default to event_type='ChatMessage' and delay=0.5."""
+    r = MockResponse()
+    assert r.event_type == "ChatMessage"
+    assert r.delay == 0.5
+    assert r.body == "Mock response"
+    assert r.actor_id == "agent:co_author"
+    assert r.character_id is None
+
+
+def test_mock_agent_has_name():
+    """MockLLMAgent should store a name attribute for compatibility."""
+    agent = MockLLMAgent(name="Gandalf")
+    assert agent.name == "Gandalf"
diff --git a/tests/unit/test_mock_actor_integration.py b/tests/unit/test_mock_actor_integration.py
new file mode 100644
index 0000000..cea1b4c
--- /dev/null
+++ b/tests/unit/test_mock_actor_integration.py
@@ -0,0 +1,83 @@
+"""Tests for the MockLLMAgent integration point in NPCActor."""
+
+import os
+import pytest
+from unittest.mock import patch, MagicMock, AsyncMock
+from sidestage.actors import NPCActor
+
+
+def test_update_prompt_creates_mock_agent_when_env_set():
+    """When SIDESTAGE_MOCK_AGENT=1 is set, _update_prompt() should create a MockLLMAgent."""
+    from sidestage.testing.mock_actor import MockLLMAgent
+
+    actor = NPCActor(actor_id="agent:test_npc")
+    actor.character = MagicMock()
+    actor.character.name = "TestChar"
+
+    with patch.dict(os.environ, {"SIDESTAGE_MOCK_AGENT": "1"}):
+        actor._update_prompt()
+
+    assert isinstance(actor.agent, MockLLMAgent)
+    assert actor.agent.name == "TestChar"
+
+
+def test_update_prompt_creates_litellm_agent_when_env_not_set():
+    """When SIDESTAGE_MOCK_AGENT is not set, _update_prompt() should proceed to LiteLLMAgent path."""
+    actor = NPCActor(actor_id="agent:test_npc")
+    actor.character = MagicMock()
+    actor.character.name = "TestChar"
+    actor.character.unseen = False
+    # Without scene_logic (campaign), _update_prompt returns early after LiteLLM path
+    actor.scene_logic = None
+
+    env = os.environ.copy()
+    env.pop("SIDESTAGE_MOCK_AGENT", None)
+    with patch.dict(os.environ, env, clear=True):
+        actor._update_prompt()
+
+    # With no scene_logic, agent stays None (LiteLLM path returns early)
+    assert actor.agent is None
+
+
+@pytest.mark.anyio
+async def test_mock_agent_processes_chat_and_returns_canned_response():
+    """End-to-end: NPCActor with mock agent should process a chat event and return the canned response."""
+    from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
+    from sidestage.models import EventModel, EventType
+    from sidestage.event import Event
+    from datetime import datetime, timezone
+
+    actor = NPCActor(actor_id="agent:test_npc")
+    actor.character = MagicMock()
+    actor.character.name = "TestNPC"
+    actor.character.id = "char_test"
+
+    mock_agent = MockLLMAgent(name="TestNPC")
+    mock_agent.responses = [MockResponse(body="I am a mock!", delay=0.01)]
+    actor.agent = mock_agent
+
+    # Create a chat event from a user
+    event_model = EventModel(
+        id="evt_test001",
+        name="Test Message",
+        body="Hello NPC!",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_test",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+        character_id="user",
+        actor_id="user",
+    )
+    event = Event.from_model(event_model)
+
+    # Mock the scene to capture the response
+    mock_scene = AsyncMock()
+    event.scene = mock_scene
+
+    await actor.process(event)
+
+    # The scene.process should have been called with a response event
+    mock_scene.process.assert_called_once()
+    response_event = mock_scene.process.call_args[0][0]
+    assert response_event.model.body == "I am a mock!"
+    assert response_event.model.actor_id == "agent:test_npc"
diff --git a/tests/unit/test_mock_actor_routes.py b/tests/unit/test_mock_actor_routes.py
new file mode 100644
index 0000000..ef2df0a
--- /dev/null
+++ b/tests/unit/test_mock_actor_routes.py
@@ -0,0 +1,134 @@
+"""Tests for the test-only mock agent API endpoints."""
+
+import os
+import pytest
+from unittest.mock import patch, MagicMock, AsyncMock
+from fastapi import FastAPI
+from httpx import AsyncClient, ASGITransport
+from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
+from sidestage.testing.routes import register_test_routes
+
+
+@pytest.fixture
+def mock_orchestrator():
+    """Create a mock orchestrator with active scenes containing mock agents."""
+    orchestrator = MagicMock()
+
+    # Create a mock agent
+    mock_agent = MockLLMAgent(name="TestNPC")
+
+    # Set up character -> actor -> agent chain
+    mock_actor = MagicMock()
+    mock_actor.agent = mock_agent
+
+    mock_character = MagicMock()
+    mock_character.actor = mock_actor
+
+    # Set up scene -> characters
+    mock_scene = MagicMock()
+    mock_scene.characters = {"char_test": mock_character}
+
+    orchestrator.active_scenes = {"scene_test": mock_scene}
+    return orchestrator
+
+
+@pytest.fixture
+def test_app(mock_orchestrator):
+    """Create a FastAPI app with test routes registered."""
+    app = FastAPI()
+    register_test_routes(app, mock_orchestrator)
+    return app
+
+
+@pytest.mark.anyio
+async def test_configure_sets_response_queue(test_app, mock_orchestrator):
+    """POST /v1/test/mock-agent/configure should set the response queue on all active mock agents."""
+    async with AsyncClient(
+        transport=ASGITransport(app=test_app), base_url="http://test"
+    ) as client:
+        response = await client.post(
+            "/v1/test/mock-agent/configure",
+            json={
+                "responses": [{"body": "Hello from mock!"}],
+                "default_response": "Default mock",
+            },
+        )
+    assert response.status_code == 200
+    data = response.json()
+    assert data["status"] == "ok"
+    assert data["agents_configured"] == 1
+
+    # Verify the agent was configured
+    scene = mock_orchestrator.active_scenes["scene_test"]
+    char = scene.characters["char_test"]
+    agent = char.actor.agent
+    assert len(agent.responses) == 1
+    assert agent.responses[0].body == "Hello from mock!"
+    assert agent.default_response == "Default mock"
+
+
+@pytest.mark.anyio
+async def test_reset_clears_response_queue(test_app, mock_orchestrator):
+    """POST /v1/test/mock-agent/reset should clear the response queue on all active mock agents."""
+    # Pre-configure the agent
+    scene = mock_orchestrator.active_scenes["scene_test"]
+    agent = scene.characters["char_test"].actor.agent
+    agent.responses = [MockResponse(body="old")]
+    agent.default_response = "old default"
+
+    async with AsyncClient(
+        transport=ASGITransport(app=test_app), base_url="http://test"
+    ) as client:
+        response = await client.post("/v1/test/mock-agent/reset")
+    assert response.status_code == 200
+    data = response.json()
+    assert data["status"] == "ok"
+    assert data["agents_reset"] == 1
+
+    assert len(agent.responses) == 0
+    assert agent.default_response == "Mock response"
+    assert agent.response_delay == 0.1
+
+
+@pytest.mark.anyio
+async def test_configure_reaches_active_scene_mock_agents(test_app, mock_orchestrator):
+    """Configure endpoint should traverse active_scenes to find and update mock agents."""
+    # Add a second scene with a mock agent
+    mock_agent2 = MockLLMAgent(name="SecondNPC")
+    mock_actor2 = MagicMock()
+    mock_actor2.agent = mock_agent2
+    mock_char2 = MagicMock()
+    mock_char2.actor = mock_actor2
+    mock_scene2 = MagicMock()
+    mock_scene2.characters = {"char_test2": mock_char2}
+    mock_orchestrator.active_scenes["scene_test2"] = mock_scene2
+
+    async with AsyncClient(
+        transport=ASGITransport(app=test_app), base_url="http://test"
+    ) as client:
+        response = await client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "Shared response"}]},
+        )
+    assert response.status_code == 200
+    data = response.json()
+    assert data["agents_configured"] == 2
+
+
+@pytest.mark.anyio
+async def test_configure_with_no_active_scenes():
+    """Configure should succeed with agents_configured=0 when no scenes are active."""
+    app = FastAPI()
+    orchestrator = MagicMock()
+    orchestrator.active_scenes = {}
+    register_test_routes(app, orchestrator)
+
+    async with AsyncClient(
+        transport=ASGITransport(app=app), base_url="http://test"
+    ) as client:
+        response = await client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "No one home"}]},
+        )
+    assert response.status_code == 200
+    assert response.json()["agents_configured"] == 0
