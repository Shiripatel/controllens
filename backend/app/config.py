from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CL_", extra="ignore")

    app_name: str = "ControlLens"
    env: str = "dev"  # dev | prod
    database_url: str = "sqlite:///./controllens.db"  # e.g. postgresql+psycopg://user:pw@host/db
    storage_dir: str = "./storage"
    max_upload_mb: int = 25
    cors_origins: str = "http://localhost:5173"

    # Auth
    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_expire_minutes: int = 480

    # AI
    anthropic_api_key: str = ""
    llm_provider: str = "auto"  # auto | anthropic | mock
    llm_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = 8000
    llm_temperature: float = 0.0
    max_evidence_chars: int = 60000  # per agent call

    # Seed admin (first start only)
    seed_admin_email: str = "admin@controllens.local"
    seed_admin_password: str = "Admin#12345"
    seed_demo: bool = True


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and (s.jwt_secret.startswith("dev-only") or len(s.jwt_secret) < 32):
        raise RuntimeError("CL_JWT_SECRET must be set to a random value of 32+ characters in production")
    return s
