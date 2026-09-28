from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    PROJECT_NAME: str = "Livestock Registry Dashboard API"
    # libpq-style DSN. The password may be left out and supplied as PGPASSWORD,
    # which avoids URL-encoding it.
    DATABASE_URL: str
    PGPASSWORD: str | None = None
    # Connections per worker process. The registry database is shared with the
    # rest of the platform and the dashboards cache responses, so the pool stays
    # small; asyncpg's own default holds 10 open per worker.
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 5
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
