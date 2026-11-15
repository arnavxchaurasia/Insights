from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MI_", env_file=BACKEND_DIR / ".env")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}"
    feeds_file: Path = BACKEND_DIR / "feeds.json"
    ingest_interval_minutes: int = 15
    run_scheduler: bool = True
    http_timeout_seconds: float = 20.0
    user_agent: str = "MarketIntelBot/0.1 (RSS reader)"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    sse_poll_seconds: float = 4.0

    # AI / LLM configuration (env prefix MI_LLM_*)
    llm_provider: str = "fake"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_timeout_seconds: float = 30.0


settings = Settings()
