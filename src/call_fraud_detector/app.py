import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from call_fraud_detector.api import router as api_router
from call_fraud_detector.config import settings
from call_fraud_detector.web import router as web_router

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def create_app() -> FastAPI:
    application = FastAPI(title="Call Fraud Detector")

    static_dir = Path(__file__).resolve().parents[2] / "static"
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    application.include_router(api_router)
    application.include_router(web_router)

    return application
