from agno.models.base import Model
from agno.models.openai import OpenAIChat
# from agno.models.google import Gemini # Commented out until we need it and have dependencies

from sidestage.config import settings

def get_llm_model() -> Model:
    """
    Factory to return the configured LLM model instance.
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "llama_cpp":
        # Using OpenAIChat for llama.cpp server compatibility
        return OpenAIChat(
            id=settings.LLAMA_CPP_MODEL,
            base_url=settings.LLAMA_CPP_BASE_URL,
            api_key=settings.LLAMA_CPP_API_KEY,
        )
    
    elif provider == "gemini":
        # Placeholder for Gemini implementation
        # return Gemini(id=settings.GEMINI_MODEL, api_key=settings.GEMINI_API_KEY)
        raise NotImplementedError("Gemini provider not yet enabled. Please install google-generativeai.")

    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
