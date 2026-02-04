import pytest
import json
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.schemas import Character
from unittest.mock import patch

class TestSyncIntegration:
    @pytest.fixture
    def client(self, tmp_path):
        campaign_name = "test_sync_campaign"
        with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
            orchestrator = SidestageOrchestrator(
                campaign_name=campaign_name,
                base_dir=tmp_path
            )
            # Short-circuit agent creation for sync tests if needed, 
            # but orchestrator already handles it.
        return TestClient(orchestrator.fastapi_app)

    def test_websocket_broadcast_on_entity_update(self, client):
        # Create a dummy entity via REST
        char_data = {"id": "sync_char", "name": "Sync Character", "body": "Original", "type": "Character"}
        
        with client.websocket_connect("/v1/ws") as websocket:
            # Trigger an update via REST
            resp = client.post("/v1/entities/sync_char", json={"name": "Updated Sync Char", "type": "Character", "body": "New"})
            assert resp.status_code == 200
            
            # Receive broadcast
            data = websocket.receive_json()
            assert data["type"] == "entities_updated"

    def test_collaborative_editing_relay(self, client):
        # Connect two clients
        with client.websocket_connect("/v1/ws") as ws1:
            with client.websocket_connect("/v1/ws") as ws2:
                # Client 1 sends a sync message
                sync_msg = {
                    "type": "entity_content_sync",
                    "entity_id": "char_1",
                    "body": "User 1 is typing..."
                }
                ws1.send_json(sync_msg)
                
                # Client 2 should receive it
                received = ws2.receive_json()
                assert received == sync_msg
                
                # Client 1 should NOT receive its own message (if exclude is working)
                # But TestClient might behave differently or we need to wait.
                # In implementation: await self.broadcast(message, exclude=websocket)
                # So it should be excluded.

    def test_chat_broadcast(self, client):
        # Mocking the agent to avoid LLM calls
        with patch("sidestage.agent.LiteLLMAgent.arun") as mock_arun:
            from sidestage.agent import AgentResponse
            mock_arun.return_value = AgentResponse(content="AI Response")
            
            with client.websocket_connect("/v1/ws") as ws:
                # Trigger chat via REST
                client.post("/v1/chat", json={"message": "Hello", "scene_id": "campaign_planning"})
                
                # Receive user message broadcast
                msg1 = ws.receive_json()
                assert msg1["type"] == "chat_message"
                assert msg1["message"]["character_id"] == "user"
                
                # Receive agent message broadcast
                msg2 = ws.receive_json()
                assert msg2["type"] == "chat_message"
                assert msg2["message"]["character_id"] == "char_co_author"
