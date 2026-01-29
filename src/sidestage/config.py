import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Configuration
    LLM_PROVIDER: str = "llama_cpp"  # "llama_cpp" or "gemini"
    
    # Llama.cpp Configuration
    LLAMA_CPP_BASE_URL: str = "http://medusa:8080/v1"
    LLAMA_CPP_API_KEY: str = "sk-no-key-required"
    LLAMA_CPP_MODEL: str = "default" # Often ignored by llama.cpp server if only one model is loaded

    # Gemini Configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
