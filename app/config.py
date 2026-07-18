"""Application configuration loaded from .env via pydantic-settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./smartcs.db"
    chroma_persist_dir: str = "./chroma_data"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    embedding_model: str = "text-embedding-v3"
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    l1_cache_ttl: int = 300
    l2_cache_threshold: float = 0.85
    intent_confidence_threshold: float = 0.6
    max_context_tokens: int = 2000
    max_conversation_turns: int = 10
    rate_limit_per_minute: int = 30
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Optional local document parser. Keep downloaded artifacts off the system drive.
    docling_artifacts_path: str = "D:/DevData/smartcs/docling/artifacts"
    hf_home: str = "D:/DevData/smartcs/huggingface"
    torch_home: str = "D:/DevData/smartcs/torch"
    tesseract_cmd: str = "D:/DevData/smartcs/tesseract/tesseract.exe"
    tessdata_prefix: str = "D:/DevData/smartcs/tesseract/tessdata/"
    docling_device: str = "cpu"
    docling_num_threads: int = Field(default=4, ge=1)

    # Agent
    agent_recursion_limit: int = 10
    agent_timeout_seconds: int = 60
    agent_stream_enabled: bool = True

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    @field_validator(
        "docling_artifacts_path",
        "hf_home",
        "torch_home",
        "tesseract_cmd",
        "tessdata_prefix",
    )
    @classmethod
    def document_parser_paths_must_use_d_drive(cls, value: str) -> str:
        if not value.replace("\\", "/").lower().startswith("d:/"):
            raise ValueError("document parser paths must be on D:")
        return value

settings = Settings()
