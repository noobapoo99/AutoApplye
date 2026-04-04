from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str | None = None
    GROQ_API_KEY: str
    GEMINI_FLASH_MODEL: str | None = None
    GEMINI_EMBEDDING_MODEL: str | None = None
    OLLAMA_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3:latest"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    RABBITMQ_URL: str
    REDIS_URL: str
    DATABASE_URL: str
    SERPAPI_KEY: str
    GMAIL_CLIENT_ID: str
    GMAIL_CLIENT_SECRET: str
    GMAIL_REDIRECT_URI: str
    SECRET_KEY: str
    ENVIRONMENT: str
    LOG_LEVEL: str
    RATE_LIMIT_CAPACITY: int
    RATE_LIMIT_LEAK_RATE: float
    HALLUCINATION_THRESHOLD: float
    RESUME_MATCH_THRESHOLD: float

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )
        return self.DATABASE_URL

    @property
    def gemini_api_key(self) -> str | None:
        return self.GEMINI_API_KEY

    @property
    def groq_api_key(self) -> str:
        return self.GROQ_API_KEY

    @property
    def gemini_flash_model(self) -> str | None:
        return self.GEMINI_FLASH_MODEL

    @property
    def gemini_embedding_model(self) -> str | None:
        return self.GEMINI_EMBEDDING_MODEL

    @property
    def ollama_url(self) -> str:
        return self.OLLAMA_URL

    @property
    def ollama_model(self) -> str:
        return self.OLLAMA_MODEL

    @property
    def ollama_embedding_model(self) -> str:
        return self.OLLAMA_EMBEDDING_MODEL

    @property
    def rabbitmq_url(self) -> str:
        return self.RABBITMQ_URL

    @property
    def redis_url(self) -> str:
        return self.REDIS_URL

    @property
    def log_level(self) -> str:
        return self.LOG_LEVEL

    @property
    def rate_limit_capacity(self) -> int:
        return self.RATE_LIMIT_CAPACITY

    @property
    def rate_limit_leak_rate(self) -> float:
        return self.RATE_LIMIT_LEAK_RATE

    @property
    def hallucination_threshold(self) -> float:
        return self.HALLUCINATION_THRESHOLD

    @property
    def serpapi_key(self) -> str:
        return self.SERPAPI_KEY

    @property
    def resume_match_threshold(self) -> float:
        return self.RESUME_MATCH_THRESHOLD


@lru_cache()
def get_settings() -> Settings:
    return Settings()
