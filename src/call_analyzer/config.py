from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/call_analyzer"
    gemini_proxy_url: str = "http://localhost:8000"
    gemini_project_id: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_location: str = "us-central1"
    watch_dir: Path = Path("./watch")
    upload_dir: Path = Path("./uploads")
    worker_concurrency: int = 5
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""
    root_path: str = ""
    max_upload_size: int = 100 * 1024 * 1024  # 100 MB
    gemini_read_timeout: int = 120
    gemini_max_retries: int = 3
    api_key: str = ""
    log_level: str = "INFO"
    log_format: str = "json"
    csrf_secret: str = ""
    webhook_url: str = ""
    webhook_timeout: int = 30
    storage_type: str = "local"  # "local" or "s3"
    s3_bucket: str = ""
    s3_prefix: str = "calls/"
    s3_region: str = ""
    s3_endpoint_url: str = ""


settings = Settings()
