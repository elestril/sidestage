import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from sidestage.orchestrator import SidestageOrchestrator

@pytest.fixture
def client(tmp_path):
    # Setup a test campaign
    campaign_name = "test_integration"
    
    # We use the real orchestrator which defaults to local llama_cpp config
    orchestrator = SidestageOrchestrator(campaign_name=campaign_name)
    orchestrator.storage.db_path = tmp_path / "world.db"
    orchestrator.storage._init_db()
    
    return TestClient(orchestrator.app.get_app())

def test_consecutive_messages(client):
    # 1. Get the Agent ID
    response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) > 0
    agent_id = agents[0]["id"]

    # 2. Mock Agent.run to simulate successful turns
    with patch("agno.agent.Agent.run") as mock_run:
        from agno.run.agent import RunOutput
        mock_run.return_value = RunOutput(content="I am a helpful assistant.") # type: ignore

        # 3. Send first message
        print("\nSending first message...")
        resp1 = client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "Hello for the first time!", "stream": "false"}
        )
        assert resp1.status_code == 200
        assert "helpful" in resp1.text.lower()

        # 4. Send second message immediately after
        print("Sending second message...")
        resp2 = client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "Hello again! This is consecutive.", "stream": "false"}
        )
        assert resp2.status_code == 200
        assert "helpful" in resp2.text.lower()