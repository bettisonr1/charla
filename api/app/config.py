from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://charla:charla@localhost:5442/charla"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    # Haiku until the eval (api/evals) says otherwise; see docs/phase-2-evals.md.
    correction_model: str = "claude-haiku-5-5"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
