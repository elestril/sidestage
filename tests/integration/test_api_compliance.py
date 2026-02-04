import pytest
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.schemas import (
    Entity, Scene, Character, Location, Item, Event, ChatMessage,
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
        char = Character(id="char_1", name="Test Character", body="Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        response = self.client.get("/v1/entities")
        assert response.status_code == 200
        data = response.json()
        
        # Validate schema
        assert isinstance(data, list)
        assert len(data) >= 1
        
        # Find our test character
        found = next((e for e in data if e["id"] == "char_1"), None)
        assert found is not None
        assert found["type"] == "Character"

    def test_create_scene_schema(self):
        req = SceneCreateRequest(name="Test Scene", description="Desc", current_gametime=100)
        response = self.client.post("/v1/scenes", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        # Validate response schema
        scene = Scene(**data) # Should not raise
        assert scene.name == "Test Scene"
        assert scene.current_gametime == 100

    def test_update_entity_markdown_schema(self):
        char = Character(id="char_2", name="Markdown Character", body="Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        req = EntityMarkdownUpdateRequest(markdown="---\nname: Updated Name\ntype: Character\n---\nNew Body")
        response = self.client.post(f"/v1/entities/char_2/markdown", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        # Validate status response
        assert data["status"] == "ok"
        
        # Verify update
        updated = self.orchestrator.campaign.storage.get_character("char_2")
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.body == "New Body"

    def test_chat_endpoint_schema(self):
        # Ensure scene exists
        self.orchestrator.campaign.storage.add_scene(Scene(id="scene_1", name="S1", body="B"))
        
        req = ChatRequest(message="Hello", scene_id="scene_1")
        response = self.client.post("/v1/chat", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        assert "user_message" in data
        assert "agent_message" in data
        assert data["user_message"]["character_id"] == "user" # Fallback logic in scene.py sets this
        assert data["agent_message"]["character_id"] == "char_co_author"

    def test_get_entity_markdown(self):
        char = Character(id="char_md", name="MD Character", body="MD Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        response = self.client.get("/v1/entities/char_md/markdown")
        assert response.status_code == 200
        data = response.json()
        assert "markdown" in data
        assert "MD Character" in data["markdown"]
        assert "MD Body" in data["markdown"]

    def test_update_entity_data(self):
        char = Character(id="char_data", name="Old Name", body="Old Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        response = self.client.post("/v1/entities/char_data", json={"name": "New Name", "type": "Character", "body": "New Body"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        updated = self.orchestrator.campaign.storage.get_character("char_data")
        assert updated.name == "New Name"

    def test_list_scenes(self):
        self.orchestrator.campaign.storage.add_scene(Scene(id="scene_list", name="S List", body="B"))
        response = self.client.get("/v1/scenes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["id"] == "scene_list" for s in data)

    def test_get_scene_messages(self):
        # Fix ChatMessage instantiation to include required character_id if needed,
        # but ChatMessage schema was just updated to require character_id.
        # Wait, the previous test failure was due to ImportErrors.
        # I need to check ChatMessage schema again.
        # It has character_id now.
        
        msg = ChatMessage(
            id="msg_1", name="M1", body="B1", scene_id="scene_msg", 
            gametime=0, walltime="now", actor="user", message="Hello",
            character_id="char_user" # Added required field
        )
        self.orchestrator.campaign.storage.add_scene(Scene(id="scene_msg", name="S Msg", body="B", messages=[msg]))
        
        response = self.client.get("/v1/scenes/scene_msg/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["message"] == "Hello"

    def test_export_import_entities(self):
        char = Character(id="char_exp", name="Export Character", body="Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        # Export
        resp_exp = self.client.post("/v1/entities/export", json={})
        assert resp_exp.status_code == 200
        assert "Exported" in resp_exp.json()["message"]
        
        # Verify file exists
        exp_file = self.orchestrator.campaign.campaign_dir / "entities" / "char_exp.md"
        assert exp_file.exists()
        
        # Modify file and Import
        content = exp_file.read_text()
        exp_file.write_text(content.replace("Export Character", "Imported Character"))
        
        resp_imp = self.client.post("/v1/entities/import", json={})
        assert resp_imp.status_code == 200
        assert "Successfully imported" in resp_imp.json()["message"]        
        
        updated = self.orchestrator.campaign.storage.get_character("char_exp")
        # Depending on how import works (add vs update), it might or might not update if ID exists.
        # Storage.add_character uses INSERT OR REPLACE, so it should update.
        # Let's verify.
        assert updated.name == "Imported Character"

