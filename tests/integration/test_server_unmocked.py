import pytest
import time
from pathlib import Path
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator


@pytest.mark.llm
class TestServerUnmocked:
    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path: Path):
        """
        Setup a real orchestrator in a temp directory.
        No mocking of agents or models here.
        """
        self.campaign_name = "unmocked_campaign"
        self.orchestrator = SidestageOrchestrator(
            campaign_name=self.campaign_name,
            base_dir=tmp_path
        )
        self.client = TestClient(self.orchestrator.fastapi_app)

    def test_real_chat_interaction(self):
        """
        Tests a real interaction with the backend.
        Sends a message and expects a non-empty response from the LLM.
        """
        message = "Respond with the single word 'Sausage'."

        # Send a real message to the backend via Sidestage Chat API
        resp = self.client.post(
            "/v1/chat",
            json={"message": message, "scene_id": "campaign_planning"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "user_message" in data

        # Agent responses are async (fire-and-forget via the bus).
        # Poll storage until at least one agent reply appears.
        deadline = time.time() + 15
        scene = None
        while time.time() < deadline:
            scene = self.orchestrator.campaign.storage.get_scene("campaign_planning")
            if scene and len(scene.messages) >= 2:
                break
            time.sleep(0.5)

        assert scene is not None
        assert len(scene.messages) >= 2  # User msg + Agent msg

        last_msg = scene.messages[-1]
        assert last_msg.actor_id.startswith("agent")
        content = last_msg.message

        print(f"Received response: {content}")
        assert "sausage" in content.lower()

    def test_consecutive_real_messages(self):
        """
        Tests that consecutive messages work without 'alternating roles' error.
        """
        # First message
        resp1 = self.client.post(
            "/v1/chat",
            json={"message": "First message.", "scene_id": "campaign_planning"}
        )
        assert resp1.status_code == 200

        # Wait for first agent response before sending second message
        deadline = time.time() + 15
        while time.time() < deadline:
            scene = self.orchestrator.campaign.storage.get_scene("campaign_planning")
            if scene and len(scene.messages) >= 2:
                break
            time.sleep(0.5)

        # Second message (consecutive)
        resp2 = self.client.post(
            "/v1/chat",
            json={"message": "Second message.", "scene_id": "campaign_planning"}
        )
        assert resp2.status_code == 200

        # Wait for second agent response
        deadline = time.time() + 15
        while time.time() < deadline:
            scene = self.orchestrator.campaign.storage.get_scene("campaign_planning")
            if scene and len(scene.messages) >= 4:
                break
            time.sleep(0.5)

        scene = self.orchestrator.campaign.storage.get_scene("campaign_planning")
        # Should have User1, Agent1, User2, Agent2 = 4 messages (or more if history preserved)
        assert scene is not None
        assert len(scene.messages) >= 4
