import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from call_fraud_detector.analyzer import analyze_bytes
from call_fraud_detector.audio import SUPPORTED_EXTENSIONS
from call_fraud_detector.config import settings
from call_fraud_detector.database import get_session
from call_fraud_detector.models import AnalysisResult, Call

router = APIRouter(prefix="/api/v1")


def _call_to_dict(call: Call) -> dict:
    d = {
        "id": str(call.id),
        "filename": call.filename,
        "audio_format": call.audio_format,
        "source": call.source,
        "file_path": call.file_path,
        "duration_seconds": call.duration_seconds,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }
    if call.analysis:
        d["analysis"] = {
            "id": str(call.analysis.id),
            "transcript": call.analysis.transcript,
            "is_fraud": call.analysis.is_fraud,
            "fraud_score": call.analysis.fraud_score,
            "fraud_categories": call.analysis.fraud_categories,
            "reasons": call.analysis.reasons,
            "analyzed_at": call.analysis.analyzed_at.isoformat() if call.analysis.analyzed_at else None,
        }
    return d


@router.post("/calls/analyze")
async def analyze_call(file: UploadFile, session: AsyncSession = Depends(get_session)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    data = await file.read()
    save_path = Path(settings.upload_dir) / f"{uuid.uuid4()}{ext}"

    call, result = await analyze_bytes(data, file.filename or "unknown", "api", session, save_path)
    return _call_to_dict(call)


@router.get("/calls")
async def list_calls(
    is_fraud: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    query = select(Call).options(joinedload(Call.analysis)).order_by(Call.created_at.desc())

    if is_fraud is not None:
        query = query.join(AnalysisResult).where(AnalysisResult.is_fraud == is_fraud)

    total_q = select(func.count(Call.id))
    if is_fraud is not None:
        total_q = total_q.join(AnalysisResult).where(AnalysisResult.is_fraud == is_fraud)
    total = (await session.execute(total_q)).scalar() or 0

    query = query.offset((page - 1) * size).limit(size)
    rows = (await session.execute(query)).unique().scalars().all()

    return {
        "items": [_call_to_dict(c) for c in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/calls/{call_id}")
async def get_call(call_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    query = select(Call).options(joinedload(Call.analysis)).where(Call.id == call_id)
    call = (await session.execute(query)).unique().scalar_one_or_none()
    if not call:
        raise HTTPException(404, "Call not found")
    return _call_to_dict(call)


@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    total = (await session.execute(select(func.count(Call.id)))).scalar() or 0
    fraud_count = (
        await session.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
        )
    ).scalar() or 0
    avg_score = (
        await session.execute(select(func.avg(AnalysisResult.fraud_score)))
    ).scalar()

    return {
        "total_calls": total,
        "fraud_calls": fraud_count,
        "clean_calls": total - fraud_count,
        "average_fraud_score": round(avg_score, 3) if avg_score else 0.0,
    }


@router.post("/webhook/call")
async def webhook_call(file: UploadFile, session: AsyncSession = Depends(get_session)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}")

    data = await file.read()
    save_path = Path(settings.upload_dir) / f"{uuid.uuid4()}{ext}"

    call, result = await analyze_bytes(data, file.filename or "unknown", "api", session, save_path)
    return _call_to_dict(call)
