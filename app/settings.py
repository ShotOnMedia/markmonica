from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MarkMonica"
    environment: str = "development"
    app_url: str = "http://localhost:8000"
    database_url: str = "postgresql+psycopg://markmonica:markmonica@db:5432/markmonica"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "markmonica"
    s3_secret_key: str = "change-me"
    s3_bucket: str = "markmonica"
    s3_region: str = "auto"
    s3_auto_create_bucket: bool = False
    s3_force_path_style: bool = True
    upload_url_expiry_seconds: int = 900
    max_image_upload_mb: int = 50
    max_video_upload_mb: int = 500
    worker_queue: str = "markmonica:jobs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
