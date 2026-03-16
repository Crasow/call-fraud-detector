from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/call_fraud_detector"
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


settings = Settings()
