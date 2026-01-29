import pytest
from unittest.mock import MagicMock, patch
from sidestage.agent import create_agent
from sidestage.llm_factory import get_llm_model
from sidestage.config import settings
from agno.models.base import Model

def test_get_llm_model_llama_cpp():
    """Test that factory returns OpenAIChat with correct settings for Llama.cpp."""
    with patch.object(settings, 'LLM_PROVIDER', 'llama_cpp'):
        with patch('sidestage.llm_factory.OpenAIChat') as MockOpenAI:
            # We don't check return value type here, just that it was called correctly
            get_llm_model()
            MockOpenAI.assert_called_once()
            call_kwargs = MockOpenAI.call_args.kwargs
            assert call_kwargs['base_url'] == settings.LLAMA_CPP_BASE_URL
            assert call_kwargs['api_key'] == settings.LLAMA_CPP_API_KEY

def test_get_llm_model_gemini_raises():
    """Test that Gemini provider raises NotImplementedError (until implemented)."""
    with patch.object(settings, 'LLM_PROVIDER', 'gemini'):
        with pytest.raises(NotImplementedError):
            get_llm_model()

def test_get_llm_model_unknown_provider_raises():
    """Test that unknown provider raises ValueError."""
    with patch.object(settings, 'LLM_PROVIDER', 'unknown_provider'):
        with pytest.raises(ValueError):
            get_llm_model()

def test_create_agent_initialization():
    """Test that agent is initialized correctly using the model from factory."""
    with patch('sidestage.agent.get_llm_model') as mock_get_model:
        # Use a real OpenAIChat instance (it's concrete) but with dummy config
        from agno.models.openai import OpenAIChat
        
        mock_model = OpenAIChat(id="test-model", api_key="test-key")
        mock_get_model.return_value = mock_model
        
        agent = create_agent()
        
        assert agent is not None
        assert agent.model.id == "test-model" 
        assert "Sidestage" in agent.description
