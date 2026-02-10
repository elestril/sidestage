"""Integration tests for WebSocket communication via User actor."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from unittest.mock import patch


@pytest.mark.timeout(5)
class TestWebSocketIntegration:
    @pytest.fixture
    def client(self, tmp_path: Path) -> TestClient:
        campaign_name = "test_ws_campaign"
        with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
            orchestrator = SidestageOrchestrator(
                campaign_name=campaign_name,
                base_dir=tmp_path
            )
        return TestClient(orchestrator.fastapi_app)

    def test_websocket_broadcast_on_entity_update(self, client: TestClient):
        """Entity updates via REST broadcast to connected WebSocket clients."""
        with client.websocket_connect("/v1/ws") as websocket:
            # Trigger an update via REST
            resp = client.post(
                "/v1/entities/sync_char",
                json={"name": "Updated Sync Char", "type": "Character", "body": "New"},
            )
            assert resp.status_code == 200

            # Receive broadcast via User actor
            data = websocket.receive_json()
            assert data["type"] == "entities_updated"

    def test_collaborative_editing_relay(self, client: TestClient):
        """entity_content_sync messages relay to other clients, excluding sender."""
        with client.websocket_connect("/v1/ws") as ws1:
            with client.websocket_connect("/v1/ws") as ws2:
                sync_msg = {
                    "type": "entity_content_sync",
                    "entity_id": "char_1",
                    "body": "User 1 is typing...",
                }
                ws1.send_json(sync_msg)

                # Client 2 should receive it
                received = ws2.receive_json()
                assert received == sync_msg
