from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MarkMonica"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://markmonica:markmonica@db:5432/markmonica"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "markmonica"
    s3_secret_key: str = "change-me"
    s3_bucket: str = "markmonica"
    s3_region: str = "auto"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
