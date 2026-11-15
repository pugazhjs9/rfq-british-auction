from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://auction:auction@localhost:5433/auction"
    redis_url: str = "redis://localhost:6380/0"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    # How often the Celery beat job looks for auctions that have just closed.
    finalize_interval_seconds: float = 5.0


settings = Settings()
