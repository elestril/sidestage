import pytest
from unittest.mock import MagicMock, patch
from sidestage.campaign import Campaign, SidestageConfig
from sidestage.agent import LiteLLMAgent

def test_campaign_create_agent_llama_cpp(tmp_path):
    """Test that campaign creates LiteLLMAgent with correct settings for Llama.cpp."""
    test_config = SidestageConfig(
        llm_provider="llama_cpp",
        llama_cpp_model="test-model",
        llama_cpp_base_url="http://test:8080/v1"
    )
    
    with patch('sidestage.campaign.Campaign._load_or_create_config', return_value=test_config):
        with patch('sidestage.campaign.Campaign._ensure_llm_availability'):
            campaign = Campaign(name="test", base_dir=tmp_path)
            agent = campaign.agent
        
        assert isinstance(agent, LiteLLMAgent)
        assert agent.model == "openai/test-model"
        assert agent.api_base == "http://test:8080/v1"

def test_agent_tools_configuration(tmp_path):
    """Test that the agent is initialized with the correct tools."""
    with patch('sidestage.campaign.Campaign._ensure_llm_availability'):
        campaign = Campaign(name="test", base_dir=tmp_path)
        agent = campaign.agent
    
        assert agent.tools is not None
        tool_names = [t.__name__ for t in agent.tools]
        assert "create_character" in tool_names
        assert "update_character" in tool_names
        assert "list_characters" in tool_names
        assert "create_location" in tool_names
