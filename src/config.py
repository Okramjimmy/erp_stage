from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Application
    app_name: str = "ERP Stage Builder"
    app_version: str = "1.0.0"
    debug: bool = True
    secret_key: str = "your-secret-key-here-change-in-production"
    # Used to sign the session cookie — override in .env in production
    session_secret_key: str = "your-session-secret-key-change-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/erp_stage"
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "erp_stage"
    database_user: str = "postgres"
    database_password: str = "postgres"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # MinIO Storage
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_name: str = "erp-stage-storage"
    minio_default_region: str = "us-east-1"
    public_url: str = "13.214.237.209"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Cache TTL (in seconds)
    cache_ttl_master_metadata: int = 3600  # 1 hour
    cache_ttl_stage_path: int = 86400  # 24 hours
    cache_ttl_visible_stages: int = 900  # 15 minutes
    cache_ttl_permissions: int = 1800  # 30 minutes

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
