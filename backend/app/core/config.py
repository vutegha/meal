from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "We MEAL"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://meal:meal@localhost:5432/meal"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]

    # Stockage des fichiers : "local" (dossier) ou "s3" (MinIO, S3, R2…)
    storage_backend: str = "local"
    storage_local_path: str = "./data/files"
    s3_endpoint: str | None = None
    s3_bucket: str = "wemeal"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    max_upload_mb: int = 25

    # Tâches longues : exécutées dans la requête (développement, tests) ou par le worker ARQ
    jobs_inline: bool = False

    # IA
    anthropic_api_key: str | None = None
    llm_model_extraction: str = "claude-opus-5-5"
    llm_model_drafting: str = "claude-sonnet-5"
    llm_model_light: str = "claude-haiku-4-5"
    # Plafond mensuel des dépenses IA par organisation, en USD (0 = illimité)
    ai_monthly_budget_usd: float = 50.0
    # Taille maximale du texte envoyé en une fois (au-delà : erreur explicite, pas de troncature)
    llm_max_document_chars: int = 2_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
