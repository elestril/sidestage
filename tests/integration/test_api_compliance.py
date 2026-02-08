import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.models import (
    EntityModel, SceneModel, CharacterModel, LocationModel, ItemModel, EventModel, ChatMessageModel,
)
from sidestage.schemas import (
    SceneCreateRequest, EntityMarkdownUpdateRequest, ChatRequest,
    EntityListResponse, EntityMarkdownResponse, StatusResponse,
)
from sidestage.agent import AgentResponse
from unittest.mock import MagicMock, AsyncMock

class TestApiCompliance:
    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.campaign_name = "test_compliance_campaign"
        
        # Mock the agent creation and LLM availability check
        monkeypatch.setattr("sidestage.campaign.Campaign._ensure_llm_availability", lambda s: None)
        
        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=AgentResponse(content="I am a mocked agent."))
        mock_agent.model = "gpt-3.5-turbo" # Valid string for LiteLLM
        mock_agent.api_base = "http://localhost:8080"
        mock_agent.api_key = "sk-dummy"
        mock_agent.tools = []
        mock_agent.debug_mode = False
        
        monkeypatch.setattr("sidestage.campaign.Campaign.create_agent", lambda s: mock_agent)
        # Also patch LiteLLMAgent in character.py because AgentActor creates new instances
        monkeypatch.setattr("sidestage.character.LiteLLMAgent", lambda **kwargs: mock_agent)
        
        self.orchestrator = SidestageOrchestrator(
            campaign_name=self.campaign_name,
            base_dir=tmp_path
        )
        # Create a mock agent explicitly if the patch didn't catch it in __init__
        self.orchestrator.campaign.agent = mock_agent
        
        self.client = TestClient(self.orchestrator.fastapi_app)

    def test_list_entities_schema(self):
        # Create a dummy entity
        char = CharacterModel(id="char_1", name="Test CharacterModel", body="Body")
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
        req = SceneCreateRequest(name="Test SceneModel", description="Desc", current_gametime=100)
        response = self.client.post("/v1/scenes", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        # Validate response schema
        scene = SceneModel(**data) # Should not raise
        assert scene.name == "Test SceneModel"
        assert scene.current_gametime == 100

    def test_update_entity_markdown_schema(self):
        char = CharacterModel(id="char_2", name="Markdown CharacterModel", body="Body")
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
        self.orchestrator.campaign.storage.add_scene(SceneModel(id="scene_1", name="S1", body="B"))
        
        req = ChatRequest(message="Hello", scene_id="scene_1")
        response = self.client.post("/v1/chat", json=req.model_dump())
        assert response.status_code == 200
        data = response.json()
        
        assert "user_message" in data
        assert "agent_message" in data
        assert data["user_message"]["character_id"] == "user" # Fallback logic in scene.py sets this
        assert data["agent_message"] is None # Asynchronous architecture means None in response

    def test_get_entity_markdown(self):
        char = CharacterModel(id="char_md", name="MD CharacterModel", body="MD Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        response = self.client.get("/v1/entities/char_md/markdown")
        assert response.status_code == 200
        data = response.json()
        assert "markdown" in data
        assert "MD CharacterModel" in data["markdown"]
        assert "MD Body" in data["markdown"]

    def test_update_entity_data(self):
        char = CharacterModel(id="char_data", name="Old Name", body="Old Body")
        self.orchestrator.campaign.storage.add_character(char)
        
        response = self.client.post("/v1/entities/char_data", json={"name": "New Name", "type": "Character", "body": "New Body"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        updated = self.orchestrator.campaign.storage.get_character("char_data")
        assert updated is not None
        assert updated.name == "New Name"

    def test_list_scenes(self):
        self.orchestrator.campaign.storage.add_scene(SceneModel(id="scene_list", name="S List", body="B"))
        response = self.client.get("/v1/scenes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["id"] == "scene_list" for s in data)

    def test_get_scene_messages(self):
        # Fix ChatMessageModel instantiation to include required character_id and actor_id
        msg = ChatMessageModel(
            id="msg_1", name="M1", body="B1", scene_id="scene_msg", 
            gametime=0, walltime="now", actor_id="user", message="Hello",
            character_id="char_user"
        )
        self.orchestrator.campaign.storage.add_scene(SceneModel(id="scene_msg", name="S Msg", body="B", messages=[msg]))
        
        response = self.client.get("/v1/scenes/scene_msg/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["message"] == "Hello"

    def test_export_import_entities(self):
        char = CharacterModel(id="char_exp", name="Export CharacterModel", body="Body")
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
        exp_file.write_text(content.replace("Export CharacterModel", "Imported CharacterModel"))
        
        resp_imp = self.client.post("/v1/entities/import", json={})
        assert resp_imp.status_code == 200
        assert "Successfully imported" in resp_imp.json()["message"]        
        
        updated = self.orchestrator.campaign.storage.get_character("char_exp")
        # Depending on how import works (add vs update), it might or might not update if ID exists.
        # Storage.add_character uses INSERT OR REPLACE, so it should update.
        # Let's verify.
        assert updated is not None
        assert updated.name == "Imported CharacterModel"

