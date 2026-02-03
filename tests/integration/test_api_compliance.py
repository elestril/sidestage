import pytest
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.schemas import (
    Entity, SceneData, NPC, Location, Item, Event, ChatMessage,
    SceneCreateRequest, EntityMarkdownUpdateRequest, ChatRequest,
    EntityListResponse, EntityMarkdownResponse, StatusResponse
)
from unittest.mock import MagicMock, AsyncMock

class TestApiCompliance:
    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path):
        self.campaign_name = "test_compliance_campaign"
        
        # Mock the agent creation and LLM availability check
        with pytest.MonkeyPatch.context() as m:
            m.setattr("sidestage.campaign.Campaign._ensure_llm_availability", lambda s: None)
            
            mock_agent = MagicMock()
            mock_agent.arun = AsyncMock(return_value="I am a mocked agent.")
            m.setattr("sidestage.campaign.Campaign.create_agent", lambda s: mock_agent)
            
            self.orchestrator = SidestageOrchestrator(
                campaign_name=self.campaign_name,
                base_dir=tmp_path
            )
            # Create a mock agent explicitly if the patch didn't catch it in __init__
            self.orchestrator.campaign.agent = mock_agent
            
            self.client = TestClient(self.orchestrator.fastapi_app)

    def test_list_entities_schema(self):
        # Create a dummy entity
        npc = NPC(id="npc_1", name="Test NPC", body="Body")
        self.orchestrator.campaign.storage.add_npc(npc)
        
        response = self.client.get("/v1/entities")
        assert response.status_code == 200
        data = response.json()
        
        # Validate schema
        assert isinstance(data, list)
        assert len(data) >= 1
        # Check if the first item matches Entity schema (conceptually)
        # We can't strict validate against Entity because it returns specific types
        assert data[0]["type"] == "NPC"
        assert data[0]["id"] == "npc_1"

    def test_create_scene_schema(self):
        req = SceneCreateRequest(name="Test Scene", description="Desc", current_gametime=100)
        response = self.client.post("/v1/scenes", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        # Validate response schema
        scene = SceneData(**data) # Should not raise
        assert scene.name == "Test Scene"
        assert scene.current_gametime == 100

    def test_update_entity_markdown_schema(self):
        npc = NPC(id="npc_2", name="Markdown NPC", body="Body")
        self.orchestrator.campaign.storage.add_npc(npc)
        
        req = EntityMarkdownUpdateRequest(markdown="---\nname: Updated Name\ntype: NPC\n---\nNew Body")
        response = self.client.post(f"/v1/entities/npc_2/markdown", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        # Validate status response
        assert data["status"] == "ok"
        
        # Verify update
        updated = self.orchestrator.campaign.storage.get_npc("npc_2")
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.body == "New Body"

    def test_chat_endpoint_schema(self):
        # Ensure scene exists
        self.orchestrator.campaign.storage.add_scene(SceneData(id="scene_1", name="S1", body="B"))
        
        req = ChatRequest(message="Hello", scene_id="scene_1")
        response = self.client.post("/v1/chat", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        assert "user_message" in data
        assert "agent_message" in data
        assert data["user_message"]["actor"] == "user"
        assert data["agent_message"]["actor"] == "agent"

    def test_get_entity_markdown(self):
        npc = NPC(id="npc_md", name="MD NPC", body="MD Body")
        self.orchestrator.campaign.storage.add_npc(npc)
        
        response = self.client.get("/v1/entities/npc_md/markdown")
        assert response.status_code == 200
        data = response.json()
        assert "markdown" in data
        assert "MD NPC" in data["markdown"]
        assert "MD Body" in data["markdown"]

    def test_update_entity_data(self):
        npc = NPC(id="npc_data", name="Old Name", body="Old Body")
        self.orchestrator.campaign.storage.add_npc(npc)
        
        response = self.client.post("/v1/entities/npc_data", json={"name": "New Name", "type": "NPC", "body": "New Body"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        updated = self.orchestrator.campaign.storage.get_npc("npc_data")
        assert updated.name == "New Name"

    def test_list_scenes(self):
        self.orchestrator.campaign.storage.add_scene(SceneData(id="scene_list", name="S List", body="B"))
        response = self.client.get("/v1/scenes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["id"] == "scene_list" for s in data)

    def test_get_scene_messages(self):
        msg = ChatMessage(
            id="msg_1", name="M1", body="B1", scene_id="scene_msg", 
            gametime=0, walltime="now", actor="user", message="Hello"
        )
        self.orchestrator.campaign.storage.add_scene(SceneData(id="scene_msg", name="S Msg", body="B", messages=[msg]))
        
        response = self.client.get("/v1/scenes/scene_msg/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["message"] == "Hello"

    def test_export_import_entities(self):
        npc = NPC(id="npc_exp", name="Export NPC", body="Body")
        self.orchestrator.campaign.storage.add_npc(npc)
        
        # Export
        resp_exp = self.client.post("/v1/entities/export", json={})
        assert resp_exp.status_code == 200
        assert "Exported" in resp_exp.json()["message"]
        
        # Verify file exists
        exp_file = self.orchestrator.campaign.campaign_dir / "entities" / "npc_exp.md"
        assert exp_file.exists()
        
        # Modify file and Import
        content = exp_file.read_text()
        exp_file.write_text(content.replace("Export NPC", "Imported NPC"))
        
        resp_imp = self.client.post("/v1/entities/import", json={})
        assert resp_imp.status_code == 200
        assert "Successfully imported" in resp_imp.json()["message"]        
        # Verify update (import adds if not exists, but here it overwrites if same ID and logic allows)
        # Actually storage.add_npc might fail if ID exists, let's check Storage.add_npc
        updated = self.orchestrator.campaign.storage.get_npc("npc_exp")
        # If add_npc uses INSERT OR REPLACE it will be Imported NPC.
        # Let's check storage.py

