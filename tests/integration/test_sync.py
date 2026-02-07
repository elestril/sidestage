import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.schemas import Character
from unittest.mock import patch, AsyncMock

@pytest.mark.timeout(5)
class TestSyncIntegration:
    @pytest.fixture
    def client(self, tmp_path: Path) -> TestClient:
        campaign_name = "test_sync_campaign"
        with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
            orchestrator = SidestageOrchestrator(
                campaign_name=campaign_name,
                base_dir=tmp_path
            )
            # Short-circuit agent creation for sync tests if needed, 
            # but orchestrator already handles it.
        return TestClient(orchestrator.fastapi_app)

    def test_websocket_broadcast_on_entity_update(self, client: TestClient):
        # Create a dummy entity via REST
        char_data = {"id": "sync_char", "name": "Sync Character", "body": "Original", "type": "Character"}
        
        with client.websocket_connect("/v1/ws") as websocket:
            # Trigger an update via REST
            resp = client.post("/v1/entities/sync_char", json={"name": "Updated Sync Char", "type": "Character", "body": "New"})
            assert resp.status_code == 200
            
            # Receive broadcast
            data = websocket.receive_json()
            assert data["type"] == "entities_updated"

    def test_collaborative_editing_relay(self, client: TestClient):
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

    def test_chat_broadcast(self, client: TestClient):
        # Mocking the agent to avoid LLM calls
        from sidestage.agent import AgentResponse
        from unittest.mock import MagicMock
        
        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=AgentResponse(content="AI Response"))
        # Need to set other attributes accessed by AgentActor init or usage
        mock_agent.model = "test-model"
        mock_agent.api_base = "http://test"
        mock_agent.api_key = "sk-test"
        mock_agent.tools = []
        mock_agent.debug_mode = False

        # Patch LiteLLMAgent in character.py so AgentActor gets our mock
        with patch("sidestage.character.LiteLLMAgent", return_value=mock_agent):
            
            with client.websocket_connect("/v1/ws") as ws:
                # Trigger chat via REST
                client.post("/v1/chat", json={"message": "Hello", "scene_id": "campaign_planning"})
                
                # Receive user message broadcast
                msg1 = ws.receive_json()
                assert msg1["type"] == "chat_message"
                assert msg1["message"]["character_id"] == "user"
                
                # Receive agent message broadcast
                # Note: Multiple agents might reply (Co-Author, Narrator). 
                # We just check we get AT LEAST one agent message.
                msg2 = ws.receive_json()
                assert msg2["type"] == "chat_message"
                # It could be either character, so just check it's not user
                assert msg2["message"]["actor_id"].startswith("agent")
