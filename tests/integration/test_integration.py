import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.agent import AgentResponse

@pytest.fixture
def client(tmp_path):
    # Setup a test campaign
    campaign_name = "test_integration"
    
    with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
        # We use the real orchestrator
        orchestrator = SidestageOrchestrator(campaign_name=campaign_name, base_dir=tmp_path)
    
    return TestClient(orchestrator.fastapi_app)

def test_consecutive_messages(client):
    # Mock LiteLLMAgent.arun
    with patch("sidestage.agent.LiteLLMAgent.arun", new_callable=AsyncMock) as mock_arun:
        mock_arun.return_value = AgentResponse(content="I am a helpful assistant.")

        # 3. Send first message
        print("\nSending first message...")
        resp1 = client.post(
            "/v1/chat",
            json={"message": "Hello for the first time!", "scene_id": "campaign_planning"}
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["agent_message"]["message"] == "I am a helpful assistant."

        # 4. Send second message immediately after
        print("Sending second message...")
        resp2 = client.post(
            "/v1/chat",
            json={"message": "Hello again!", "scene_id": "campaign_planning"}
        )
        assert resp2.status_code == 200
