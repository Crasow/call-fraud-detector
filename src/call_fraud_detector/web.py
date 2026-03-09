import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile

logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from call_fraud_detector.analyzer import analyze_bytes
from call_fraud_detector.audio import SUPPORTED_EXTENSIONS
from call_fraud_detector.config import settings
from call_fraud_detector.database import get_session
from call_fraud_detector.models import AnalysisResult, Call

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    stats_q = select(func.count(Call.id))
    total = (await session.execute(stats_q)).scalar() or 0
    fraud = (
        await session.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
        )
    ).scalar() or 0
    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_calls": total,
        "fraud_calls": fraud,
    })


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(request: Request, file: UploadFile, session: AsyncSession = Depends(get_session)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return templates.TemplateResponse("partials/analysis_result.html", {
            "request": request,
            "error": f"Unsupported format: {ext}",
        })

    data = await file.read()
    save_path = Path(settings.upload_dir) / f"{uuid.uuid4()}{ext}"

    try:
        call, result = await analyze_bytes(data, file.filename or "unknown", "upload", session, save_path)
    except Exception as e:
        logger.exception("Analysis failed for %s", file.filename)
        return templates.TemplateResponse("partials/analysis_result.html", {
            "request": request,
            "error": str(e),
        })

    return templates.TemplateResponse("partials/analysis_result.html", {
        "request": request,
        "call": call,
        "result": result,
    })


@router.get("/calls", response_class=HTMLResponse)
async def calls_list(
    request: Request,
    is_fraud: str | None = None,
    page: int = 1,
    session: AsyncSession = Depends(get_session),
):
    query = select(Call).options(joinedload(Call.analysis)).order_by(Call.created_at.desc())
    size = 20

    fraud_filter = None
    if is_fraud == "true":
        fraud_filter = True
        query = query.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(True))
    elif is_fraud == "false":
        fraud_filter = False
        query = query.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(False))

    total_q = select(func.count(Call.id))
    if fraud_filter is True:
        total_q = total_q.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(True))
    elif fraud_filter is False:
        total_q = total_q.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(False))
    total = (await session.execute(total_q)).scalar() or 0

    query = query.offset((page - 1) * size).limit(size)
    calls = (await session.execute(query)).unique().scalars().all()
    total_pages = (total + size - 1) // size

    return templates.TemplateResponse("calls.html", {
        "request": request,
        "calls": calls,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "is_fraud": is_fraud,
    })


@router.get("/calls/{call_id}", response_class=HTMLResponse)
async def call_detail(request: Request, call_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    query = select(Call).options(joinedload(Call.analysis)).where(Call.id == call_id)
    call = (await session.execute(query)).unique().scalar_one_or_none()
    if not call:
        return HTMLResponse("Call not found", status_code=404)
    return templates.TemplateResponse("call_detail.html", {
        "request": request,
        "call": call,
        "result": call.analysis,
    })
