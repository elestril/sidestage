import pytest
from unittest.mock import MagicMock, patch
from sidestage.orchestrator import SidestageOrchestrator, SidestageConfig
from agno.models.llama_cpp import LlamaCpp

def test_orchestrator_get_llm_model_llama_cpp(tmp_path):
    """Test that orchestrator returns LlamaCpp with correct settings for Llama.cpp."""
    test_config = SidestageConfig(
        llm_provider="llama_cpp",
        llama_cpp_base_url="http://test:8080/v1"
    )
    
    with patch('sidestage.orchestrator.SidestageOrchestrator._load_or_create_config', return_value=test_config):
        real_model = LlamaCpp(id="test")
        with patch('sidestage.orchestrator.LlamaCpp', return_value=real_model) as MockLlama:
            orch = SidestageOrchestrator(campaign_name="test", base_dir=tmp_path)
            orch.get_llm_model()
            MockLlama.assert_called()
            last_call_kwargs = MockLlama.call_args.kwargs
            assert last_call_kwargs['base_url'] == "http://test:8080/v1"

def test_orchestrator_create_agent_initialization(tmp_path):
    """Test that agent is initialized correctly using the model from factory."""
    with patch('sidestage.orchestrator.SidestageOrchestrator.get_llm_model') as mock_get_model:
        mock_model = LlamaCpp(id="test-model")
        mock_get_model.return_value = mock_model
        
        orch = SidestageOrchestrator(campaign_name="test", base_dir=tmp_path)
        agent = orch.agent
        
        assert agent is not None
        assert agent.model is not None
        assert agent.model.id == "test-model" 

def test_agent_tools_configuration(tmp_path):
    """Test that the agent is initialized with the correct tools."""
    with patch('sidestage.orchestrator.SidestageOrchestrator.get_llm_model') as mock_get_model:
        mock_model = LlamaCpp(id="test")
        mock_get_model.return_value = mock_model
        
        orch = SidestageOrchestrator(campaign_name="test", base_dir=tmp_path)
        agent = orch.agent
        
        assert agent.tools is not None
        tool_names = [t.__name__ for t in agent.tools] # type: ignore
        assert "create_npc" in tool_names
        assert "update_npc" in tool_names
        assert "list_npcs" in tool_names
        assert "create_location" in tool_names
