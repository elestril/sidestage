import pytest
import httpx
from pathlib import Path
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator

def is_backend_up():
    """Checks if the medusa backend is reachable and healthy."""
    try:
        response = httpx.get("http://medusa:8080/health", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_backend_up(), reason="Backend at http://medusa:8080/health is unreachable")
class TestServerUnmocked:
    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path):
        """
        Setup a real orchestrator in a temp directory.
        No mocking of agents or models here.
        """
        self.campaign_name = "unmocked_campaign"
        self.orchestrator = SidestageOrchestrator(
            campaign_name=self.campaign_name,
            base_dir=tmp_path
        )
        self.client = TestClient(self.orchestrator.app.get_app())

    def test_real_chat_interaction(self):
        """
        Tests a real interaction with the backend.
        Sends a message and expects a non-empty response from the LLM.
        """
        # 1. Get the Agent ID
        response = self.client.get("/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) > 0
        agent_id = agents[0]["id"]

        # 2. Send a real message to the backend
        print(f"\nSending real message to agent {agent_id}...")
        resp = self.client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "Respond with the single word 'Sausage'.", "stream": "false"}
        )
        
        assert resp.status_code == 200
        content = resp.text
        print(f"Received response: {content}")
        
        # Verify we got a real response containing our keyword
        # (Llama-3 should be able to follow this simple instruction)
        assert "sausage" in content.lower()

    def test_consecutive_real_messages(self):
        """
        Tests that consecutive messages work without 'alternating roles' error.
        """
        response = self.client.get("/agents")
        agent_id = response.json()[0]["id"]

        # First message
        resp1 = self.client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "First message.", "stream": "false"}
        )
        assert resp1.status_code == 200

        # Second message (consecutive)
        resp2 = self.client.post(
            f"/agents/{agent_id}/runs",
            data={"message": "Second message.", "stream": "false"}
        )
        assert resp2.status_code == 200
        assert len(resp2.text) > 0
