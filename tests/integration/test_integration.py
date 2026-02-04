import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.agent import AgentResponse

@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # Setup a test campaign
    campaign_name = "test_integration"
    
    with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
        # We use the real orchestrator
        orchestrator = SidestageOrchestrator(campaign_name=campaign_name, base_dir=tmp_path)
    
    return TestClient(orchestrator.fastapi_app)

def test_consecutive_messages(client: TestClient):
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
        assert data1["agent_message"] is None # Async now
        
        # In a real async environment we'd wait. 
        # Here, the Bus worker is running in the background. 
        # We'll poll the messages endpoint.
        import time
        max_retries = 10
        found = False
        for _ in range(max_retries):
            resp = client.get("/v1/scenes/campaign_planning/messages")
            messages = resp.json()
            if any(m["character_id"] == "char_co_author" and "helpful assistant" in m["message"] for m in messages):
                found = True
                break
            time.sleep(0.5)
        
        assert found, "Agent message not found in scene history"

        # 4. Send second message immediately after
        print("Sending second message...")
        resp2 = client.post(
            "/v1/chat",
            json={"message": "Hello again!", "scene_id": "campaign_planning"}
        )
        assert resp2.status_code == 200
