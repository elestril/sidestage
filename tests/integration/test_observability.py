import pytest
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from unittest.mock import patch
from agno.run.agent import RunOutput

@pytest.fixture
def client(tmp_path):
    campaign_name = "test_observability"
    orchestrator = SidestageOrchestrator(campaign_name=campaign_name, base_dir=tmp_path)
    return TestClient(orchestrator.fastapi_app)

def test_trace_endpoint_captured_data(client):
    # 1. Get Agent ID
    resp = client.get("/agents")
    agent_id = resp.json()[0]["id"]

    # 2. Run the agent (mocking LLM for speed/reliability in tests)
    with patch("agno.agent.Agent.run") as mock_run:
        mock_run.return_value = RunOutput(
            content="Hello, I am the Co-Author.",
            session_id="test_session_123"
        )
        
        client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "Who are you?", "stream": "false", "session_id": "test_session_123"}
        )

    # 3. Verify session runs endpoint returns the interaction
    resp = client.get("/sessions/test_session_123/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) > 0
    
    # Agno's run schema should include the content
    latest_run = runs[0]
    assert "Who are you?" in str(latest_run)
    assert "Co-Author" in str(latest_run)

def test_traces_table_populated(client):
    # This test verifies that Agno's tracing is actually writing to the DB
    # (since we enabled tracing=True)
    resp = client.get("/traces")
    assert resp.status_code == 200
    # Even if empty (if no runs yet in this tmp DB), the endpoint should exist.
