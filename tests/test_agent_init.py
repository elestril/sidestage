import pytest
from unittest.mock import MagicMock, patch
from sidestage.orchestrator import SidestageOrchestrator, SidestageConfig
from agno.models.llama_cpp import LlamaCpp

def test_orchestrator_get_llm_model_llama_cpp():
    """Test that orchestrator returns LlamaCpp with correct settings for Llama.cpp."""
    # Create a config to test
    test_config = SidestageConfig(
        llm_provider="llama_cpp",
        llama_cpp_base_url="http://test:8080/v1"
    )
    
    with patch('sidestage.orchestrator.SidestageOrchestrator._load_or_create_config', return_value=test_config):
        real_model = LlamaCpp(id="test")
        with patch('sidestage.orchestrator.LlamaCpp', return_value=real_model) as MockLlama:
            orch = SidestageOrchestrator(campaign_name="test")
            orch.get_llm_model()
            MockLlama.assert_called()
            last_call_kwargs = MockLlama.call_args.kwargs
            assert last_call_kwargs['base_url'] == "http://test:8080/v1"

def test_orchestrator_create_agent_initialization():
    """Test that agent is initialized correctly using the model from factory."""
    with patch('sidestage.orchestrator.SidestageOrchestrator.get_llm_model') as mock_get_model:
        mock_model = LlamaCpp(id="test-model")
        mock_get_model.return_value = mock_model
        
        orch = SidestageOrchestrator(campaign_name="test")
        agent = orch.agent
        
        assert agent is not None
        assert agent.model is not None
        assert agent.model.id == "test-model" 
