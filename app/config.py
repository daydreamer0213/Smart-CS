"""Application configuration loaded from .env via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./smartcs.db"
    chroma_persist_dir: str = "./chroma_data"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    l1_cache_ttl: int = 300
    l2_cache_threshold: float = 0.85
    intent_confidence_threshold: float = 0.6
    max_context_tokens: int = 2000
    max_conversation_turns: int = 10
    rate_limit_per_minute: int = 30
    log_level: str = "INFO"
    log_dir: str = "logs"


settings = Settings()
