import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from call_fraud_detector.audio import SUPPORTED_EXTENSIONS, get_audio_format
from call_fraud_detector.config import settings
from call_fraud_detector.database import get_session
from call_fraud_detector.models import AnalysisResult, Call, Profile

router = APIRouter(prefix="/api/v1")


def _call_to_dict(call: Call) -> dict:
    d = {
        "id": str(call.id),
        "filename": call.filename,
        "audio_format": call.audio_format,
        "source": call.source,
        "file_path": call.file_path,
        "duration_seconds": call.duration_seconds,
        "status": call.status,
        "error_message": call.error_message,
        "profile_id": str(call.profile_id) if call.profile_id else None,
        "profile_name": call.profile.name if call.profile else None,
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


def _profile_to_dict(profile: Profile) -> dict:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "description": profile.description,
        "prompt_mode": profile.prompt_mode,
        "custom_prompt": profile.custom_prompt,
        "expert": profile.expert,
        "main_task": profile.main_task,
        "fields_for_json": profile.fields_for_json,
        "trigger_words": profile.trigger_words,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


async def _create_pending_call(
    file: UploadFile,
    source: str,
    session: AsyncSession,
    profile_id: uuid.UUID | None = None,
) -> Call:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    data = await file.read()
    save_path = Path(settings.upload_dir) / f"{uuid.uuid4()}{ext}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(data)

    call = Call(
        id=uuid.uuid4(),
        filename=file.filename or "unknown",
        audio_format=get_audio_format(file.filename or "unknown"),
        source=source,
        file_path=str(save_path),
        status="pending",
        profile_id=profile_id,
    )
    session.add(call)
    await session.commit()
    await session.refresh(call)
    return call


# ── Profile CRUD ─────────────────────────────────────────────────────

@router.post("/profiles")
async def create_profile(
    name: str = Form(...),
    description: str | None = Form(None),
    prompt_mode: str = Form("custom"),
    custom_prompt: str | None = Form(None),
    expert: str | None = Form(None),
    main_task: str | None = Form(None),
    fields_for_json: str | None = Form(None),
    trigger_words: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    if prompt_mode not in ("custom", "template"):
        raise HTTPException(400, "prompt_mode must be 'custom' or 'template'")
    if prompt_mode == "template" and not main_task:
        raise HTTPException(400, "Template mode requires 'main_task' field")

    tw_list = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words else None

    profile = Profile(
        id=uuid.uuid4(),
        name=name,
        description=description,
        prompt_mode=prompt_mode,
        custom_prompt=custom_prompt,
        expert=expert,
        main_task=main_task,
        fields_for_json=fields_for_json,
        trigger_words=tw_list,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _profile_to_dict(profile)


@router.get("/profiles")
async def list_profiles(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Profile).order_by(Profile.name))
    profiles = result.scalars().all()
    return [_profile_to_dict(p) for p in profiles]


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")
    return _profile_to_dict(profile)


@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: uuid.UUID,
    name: str | None = Form(None),
    description: str | None = Form(None),
    prompt_mode: str | None = Form(None),
    custom_prompt: str | None = Form(None),
    expert: str | None = Form(None),
    main_task: str | None = Form(None),
    fields_for_json: str | None = Form(None),
    trigger_words: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")

    if name is not None:
        profile.name = name
    if description is not None:
        profile.description = description
    if prompt_mode is not None:
        if prompt_mode not in ("custom", "template"):
            raise HTTPException(400, "prompt_mode must be 'custom' or 'template'")
        profile.prompt_mode = prompt_mode
    if custom_prompt is not None:
        profile.custom_prompt = custom_prompt
    if expert is not None:
        profile.expert = expert
    if main_task is not None:
        profile.main_task = main_task
    if fields_for_json is not None:
        profile.fields_for_json = fields_for_json
    if trigger_words is not None:
        profile.trigger_words = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words else None

    effective_mode = prompt_mode or profile.prompt_mode
    if effective_mode == "template" and not profile.main_task:
        raise HTTPException(400, "Template mode requires 'main_task' field")

    await session.commit()
    await session.refresh(profile)
    return _profile_to_dict(profile)


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")
    await session.delete(profile)
    await session.commit()
    return {"ok": True}


# ── Calls ────────────────────────────────────────────────────────────

@router.post("/calls/analyze")
async def analyze_call(
    file: UploadFile,
    profile_id: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    pid = uuid.UUID(profile_id) if profile_id else None
    call = await _create_pending_call(file, "api", session, profile_id=pid)
    return {"id": str(call.id), "status": "pending"}


@router.get("/calls")
async def list_calls(
    is_fraud: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Call)
        .options(joinedload(Call.analysis), joinedload(Call.profile))
        .order_by(Call.created_at.desc())
    )

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
    query = select(Call).options(joinedload(Call.analysis), joinedload(Call.profile)).where(Call.id == call_id)
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
async def webhook_call(
    file: UploadFile,
    profile_id: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    pid = uuid.UUID(profile_id) if profile_id else None
    call = await _create_pending_call(file, "webhook", session, profile_id=pid)
    return {"id": str(call.id), "status": "pending"}
