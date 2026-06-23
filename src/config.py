from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    app_name: str = os.getenv("APP_NAME")
    app_version: str = os.getenv("APP_VERSION")
    debug: bool = os.getenv("DEBUG")
    secret_key: str = os.getenv("SECRET_KEY")
    # Used to sign the session cookie — override in .env in production
    session_secret_key: str = os.getenv("SESSION_SECRET_KEY")

    # Database
    database_url: str = os.getenv("DATABASE_URL")
    database_host: str = os.getenv("DATABASE_HOST")
    database_port: int = os.getenv("DATABASE_PORT")
    database_name: str = os.getenv("DATABASE_NAME")
    database_user: str = os.getenv("DATABASE_USER")
    database_password: str = os.getenv("DATABASE_PASSWORD")

    # Redis
    redis_url: str = os.getenv("REDIS_URL")
    redis_host: str = os.getenv("REDIS_HOST")
    redis_port: int = os.getenv("REDIS_PORT")
    redis_db: int = os.getenv("REDIS_DB")

    # MinIO Storage
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY")
    minio_secure: bool = os.getenv("MINIO_SECURE")
    minio_bucket_name: str = os.getenv("MINIO_BUCKET_NAME")
    minio_default_region: str = os.getenv("MINIO_DEFAULT_REGION")
    public_url: str = os.getenv("PUBLIC_URL") or "localhost"

    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS")

    # Cache TTL (in seconds)
    cache_ttl_master_metadata: int = os.getenv("CACHE_TTL_MASTER_METADATA")
    cache_ttl_stage_path: int = os.getenv("CACHE_TTL_STAGE_PATH")
    cache_ttl_visible_stages: int = os.getenv("CACHE_TTL_VISIBLE_STAGES")
    cache_ttl_permissions: int = os.getenv("CACHE_TTL_PERMISSIONS")

    # Pagination
    default_page_size: int = os.getenv("DEFAULT_PAGE_SIZE")
    max_page_size: int = os.getenv("MAX_PAGE_SIZE")


settings = Settings()
