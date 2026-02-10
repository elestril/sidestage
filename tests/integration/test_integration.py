import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.agent import AgentResponse

@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    campaign_name = "test_integration"

    with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
        orchestrator = SidestageOrchestrator(campaign_name=campaign_name, base_dir=tmp_path)

    return TestClient(orchestrator.fastapi_app)

def test_consecutive_messages(client: TestClient):
    with patch("sidestage.agent.LiteLLMAgent.arun", new_callable=AsyncMock) as mock_arun:
        mock_arun.return_value = AgentResponse(content="I am a helpful assistant.")

        # Send first message
        resp1 = client.post(
            "/v1/chat",
            json={"message": "Hello for the first time!", "scene_id": "campaign_planning"}
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        # New format: {"event": {...}} with EventModel fields
        assert "event" in data1
        assert data1["event"]["event_type"] == "ChatMessage"
        assert data1["event"]["body"] == "Hello for the first time!"

        # Poll for agent response in scene messages
        import time
        max_retries = 10
        found = False
        for _ in range(max_retries):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            if any(
                m.get("character_id") == "char_co_author"
                and "helpful assistant" in m.get("body", "")
                for m in messages
            ):
                found = True
                break
            time.sleep(0.5)

        assert found, "Agent message not found in scene history"

        # Send second message immediately after
        resp2 = client.post(
            "/v1/chat",
            json={"message": "Hello again!", "scene_id": "campaign_planning"}
        )
        assert resp2.status_code == 200
