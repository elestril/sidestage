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

        Uses TestClient as a context manager so the ASGI event loop stays
        alive between requests, allowing background tasks (bus worker,
        agent LLM calls) to complete.
        """
        self.campaign_name = "unmocked_campaign"
        self.orchestrator = SidestageOrchestrator(
            campaign_name=self.campaign_name,
            base_dir=tmp_path
        )
        with TestClient(self.orchestrator.fastapi_app) as client:
            self.client = client
            yield

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
        assert last_msg.actor_id is not None
        assert last_msg.actor_id.startswith("agent")
        content = last_msg.message

        print(f"Received response: {content}")
        assert "sausage" in content.lower()

    def _wait_stable(self, scene_id: str, min_messages: int, timeout: float = 30) -> int:
        """Wait until the message count reaches min_messages and stops changing."""
        deadline = time.time() + timeout
        last_count = 0
        stable_since = None
        while time.time() < deadline:
            scene = self.orchestrator.campaign.storage.get_scene(scene_id)
            count = len(scene.messages) if scene else 0
            if count >= min_messages:
                if count != last_count:
                    last_count = count
                    stable_since = time.time()
                elif stable_since and time.time() - stable_since >= 2.0:
                    return count
            last_count = count
            time.sleep(0.5)
        return last_count

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

        # Wait for agent responses to stabilize (agents reply to each other
        # so the exact count is unpredictable; we just need the bus to be
        # idle before sending the next user message).
        count_after_first = self._wait_stable("campaign_planning", min_messages=2, timeout=60)
        assert count_after_first >= 2  # User1 + at least one agent

        # Second message (consecutive)
        resp2 = self.client.post(
            "/v1/chat",
            json={"message": "Second message.", "scene_id": "campaign_planning"}
        )
        assert resp2.status_code == 200

        # Wait for at least one agent response after User2
        count_after_second = self._wait_stable(
            "campaign_planning", min_messages=count_after_first + 2, timeout=60
        )
        assert count_after_second >= count_after_first + 2  # User2 + at least one agent
