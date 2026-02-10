"""End-to-end integration tests for the Actor-based chat flow.

These tests validate the full event lifecycle: user input -> event creation ->
queue processing -> persistence -> dispatch to actors -> NPC response generation.

WebSocket-based tests for direct broadcast (entity updates, content sync) are
in test_sync.py. Tests here focus on the REST API and event queue flow, using
polling to verify async results.

Depends on all sections (01-07) being implemented.
"""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient

from sidestage.orchestrator import SidestageOrchestrator
from sidestage.agent import AgentResponse


@pytest.fixture
def mock_agent():
    """Create a mock LiteLLMAgent that returns a canned response."""
    agent = MagicMock()
    agent.arun = AsyncMock(return_value=AgentResponse(content="NPC response text."))
    agent.model = "test-model"
    agent.api_base = "http://localhost:8080"
    agent.api_key = "sk-test"
    agent.tools = []
    agent.debug_mode = False
    return agent


@pytest.fixture
def orchestrator(tmp_path: Path) -> SidestageOrchestrator:
    """Create an Orchestrator with mocked LLM availability check."""
    with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
        orch = SidestageOrchestrator(
            campaign_name="test_chat_flow",
            base_dir=tmp_path,
        )
    return orch


@pytest.fixture
def client(orchestrator: SidestageOrchestrator, mock_agent) -> TestClient:
    """TestClient with LiteLLMAgent patched to return mock_agent."""
    with patch("sidestage.agent.LiteLLMAgent", return_value=mock_agent):
        yield TestClient(orchestrator.fastapi_app)


class TestFullChatFlow:
    """User sends message -> event created -> persisted -> dispatched."""

    def test_user_message_creates_event(self, client: TestClient):
        """POST /v1/chat returns a ChatResponse with an EventModel."""
        resp = client.post(
            "/v1/chat",
            json={"message": "Hello world!", "scene_id": "campaign_planning"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "event" in data
        event = data["event"]
        assert event["event_type"] == "ChatMessage"
        assert event["id"].startswith("evt_")
        assert event["body"] == "Hello world!"
        assert event["scene_id"] == "campaign_planning"

    def test_user_message_persisted(self, client: TestClient):
        """After sending a chat message, the event appears in scene messages."""
        client.post(
            "/v1/chat",
            json={"message": "Persist me", "scene_id": "campaign_planning"},
        )

        # Poll for persistence
        found = False
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            if any(m["body"] == "Persist me" for m in messages):
                found = True
                break
            time.sleep(0.3)

        assert found, "User message not persisted to scene messages"

    def test_event_has_correct_fields(self, client: TestClient):
        """The returned EventModel has all required fields."""
        resp = client.post(
            "/v1/chat",
            json={"message": "Fields test", "scene_id": "campaign_planning"},
        )
        event = resp.json()["event"]

        # All required EventModel fields must be present
        assert "id" in event
        assert "event_type" in event
        assert "scene_id" in event
        assert "gametime" in event
        assert "walltime" in event
        assert "body" in event
        assert "metadata" in event
        assert "visibility" in event
        assert "name" in event


class TestNPCResponse:
    """NPCActor response -> new event created -> persisted."""

    def test_npc_responds_to_user_message(self, client: TestClient, mock_agent):
        """After a user sends a message, NPCActor generates a response."""
        client.post(
            "/v1/chat",
            json={"message": "Hello NPC", "scene_id": "campaign_planning"},
        )

        # Poll for the NPC response in scene messages
        found = False
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            npc_msgs = [
                m for m in messages
                if (m.get("actor_id") or "").startswith("agent:")
                and m["event_type"] == "ChatMessage"
            ]
            if npc_msgs:
                assert "NPC response text." in npc_msgs[0]["body"]
                found = True
                break
            time.sleep(0.3)

        assert found, "NPC response not found in scene messages"

    def test_npc_response_has_agent_actor_id(self, client: TestClient, mock_agent):
        """The NPC response has an actor_id starting with 'agent:'."""
        client.post(
            "/v1/chat",
            json={"message": "Actor ID test", "scene_id": "campaign_planning"},
        )

        found = False
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            npc_msgs = [
                m for m in messages
                if (m.get("actor_id") or "").startswith("agent:")
            ]
            if npc_msgs:
                assert npc_msgs[0]["actor_id"].startswith("agent:")
                assert npc_msgs[0]["character_id"] is not None
                found = True
                break
            time.sleep(0.3)

        assert found, "NPC response with agent: actor_id not found"

    def test_user_and_npc_messages_in_history(self, client: TestClient, mock_agent):
        """Both user message and NPC response appear in scene history."""
        client.post(
            "/v1/chat",
            json={"message": "History test", "scene_id": "campaign_planning"},
        )

        # Poll until we see both user and NPC messages
        found_user = False
        found_npc = False
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            found_user = any(m["body"] == "History test" for m in messages)
            found_npc = any(
                (m.get("actor_id") or "").startswith("agent:") for m in messages
            )
            if found_user and found_npc:
                break
            time.sleep(0.3)

        assert found_user, "User message not found in scene history"
        assert found_npc, "NPC response not found in scene history"


class TestLLMFailure:
    """LLM failure -> ERROR event created -> persisted."""

    @pytest.fixture
    def failing_agent(self):
        """Create a mock agent that raises on arun."""
        agent = MagicMock()
        agent.arun = AsyncMock(side_effect=Exception("LLM unavailable"))
        agent.model = "test-model"
        agent.api_base = "http://localhost:8080"
        agent.api_key = "sk-test"
        agent.tools = []
        agent.debug_mode = False
        return agent

    @pytest.fixture
    def failing_client(
        self, orchestrator: SidestageOrchestrator, failing_agent
    ) -> TestClient:
        with patch("sidestage.agent.LiteLLMAgent", return_value=failing_agent):
            yield TestClient(orchestrator.fastapi_app)

    def test_llm_error_produces_error_event(self, failing_client: TestClient):
        """When LLM raises, an Error event is created and persisted."""
        failing_client.post(
            "/v1/chat",
            json={"message": "Trigger error", "scene_id": "campaign_planning"},
        )

        found = False
        for _ in range(20):
            resp = failing_client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            error_msgs = [m for m in messages if m["event_type"] == "Error"]
            if error_msgs:
                assert "LLM unavailable" in error_msgs[0]["body"]
                found = True
                break
            time.sleep(0.3)

        assert found, "Error event not found after LLM failure"

    def test_error_event_has_correct_fields(self, failing_client: TestClient):
        """The Error event has the NPC's character_id and agent: actor_id."""
        failing_client.post(
            "/v1/chat",
            json={"message": "Error fields test", "scene_id": "campaign_planning"},
        )

        found = False
        for _ in range(20):
            resp = failing_client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            error_msgs = [m for m in messages if m["event_type"] == "Error"]
            if error_msgs:
                err = error_msgs[0]
                assert err["name"] == "Error"
                assert (err.get("actor_id") or "").startswith("agent:")
                assert err.get("character_id") is not None
                found = True
                break
            time.sleep(0.3)

        assert found, "Error event not found"


class TestCoAuthorParticipation:
    """Co-Author NPCActor with system_actor=True participates in scenes."""

    def test_co_author_responds_as_npc(self, client: TestClient, mock_agent):
        """The Co-Author responds with character_id='char_co_author'."""
        client.post(
            "/v1/chat",
            json={"message": "Hello Co-Author", "scene_id": "campaign_planning"},
        )

        found = False
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            co_author_msgs = [
                m for m in messages
                if m.get("character_id") == "char_co_author"
                and m["event_type"] == "ChatMessage"
                and (m.get("actor_id") or "").startswith("agent:")
            ]
            if co_author_msgs:
                found = True
                break
            time.sleep(0.3)

        assert found, "Co-Author NPC response not found"


class TestChatResponseFormat:
    """Verify the new ChatResponse format with a single event field."""

    def test_no_old_response_format(self, client: TestClient):
        """Response should NOT contain old user_message/agent_message fields."""
        resp = client.post(
            "/v1/chat",
            json={"message": "Format check", "scene_id": "campaign_planning"},
        )
        data = resp.json()

        assert "user_message" not in data
        assert "agent_message" not in data
        assert "event" in data

    def test_event_type_is_chat_message(self, client: TestClient):
        """The returned event should have event_type='ChatMessage'."""
        resp = client.post(
            "/v1/chat",
            json={"message": "Type check", "scene_id": "campaign_planning"},
        )
        assert resp.json()["event"]["event_type"] == "ChatMessage"


class TestSceneMessages:
    """GET /v1/scenes/{id}/messages returns EventModel list."""

    def test_messages_are_event_models(self, client: TestClient):
        """Scene messages use EventModel format, not old ChatMessage format."""
        client.post(
            "/v1/chat",
            json={"message": "Model check", "scene_id": "campaign_planning"},
        )

        # Poll for at least one message
        messages = []
        for _ in range(20):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            if messages:
                break
            time.sleep(0.3)

        assert len(messages) >= 1
        msg = messages[0]
        # Should have EventModel fields, not old ChatMessage fields
        assert "body" in msg  # not "message"
        assert "event_type" in msg
        assert "metadata" in msg  # not "widget"
        assert "message" not in msg
        assert "widget" not in msg
