from unittest.mock import MagicMock, patch
from sidestage.orchestrator import SidestageOrchestrator
from sidestage.tools import WorldTools
from sidestage.storage import Storage
from agno.models.llama_cpp import LlamaCpp

def test_agent_tools_configuration():
    """Test that the agent is initialized with the correct tools."""
    with patch('sidestage.orchestrator.SidestageOrchestrator.get_llm_model') as mock_get_model:
        # Mock model with a real class instance to satisfy Agno validation
        mock_model = LlamaCpp(id="test")
        mock_get_model.return_value = mock_model
        
        # Create orchestrator
        orch = SidestageOrchestrator(campaign_name="test")
        agent = orch.agent
        
        # Check if tools are registered
        assert agent.tools is not None
        tool_names = [t.__name__ for t in agent.tools] # type: ignore
        assert "create_npc" in tool_names
        assert "update_npc" in tool_names
        assert "list_npcs" in tool_names
        assert "create_location" in tool_names

def test_world_tools_wrapper(tmp_path):
    """Test the WorldTools wrapper logic separately."""
    # Initialize storage manually with tmp_path
    storage = Storage(db_path=tmp_path / "world.db")
    tools = WorldTools(storage=storage)
    
    # Test create
    resp = tools.create_npc("TestNPC", "A test guy")
    assert "TestNPC" in resp
    npc_data = storage.list_npcs()[0]
    npc_id = npc_data.id
    
    # Test update
    update_resp = tools.update_npc(npc_id, description="Updated description")
    assert "Updated description" in update_resp
    
    updated_npc = storage.get_npc(npc_id)
    assert updated_npc is not None
    assert updated_npc.description == "Updated description"
    
    # Test list
    list_resp = tools.list_npcs()
    assert "TestNPC" in list_resp
