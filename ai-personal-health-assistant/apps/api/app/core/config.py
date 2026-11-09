from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./health.db"
    storage_dir: Path = Path("./private-storage")
    encryption_key: str | None = None
    session_hours: int = 12
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_bytes: int = 10 * 1024 * 1024
    document_retention_days: int = 30
    ai_service_url: str = "http://localhost:8001"
settings = Settings()
