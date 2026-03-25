import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile

logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import cast, func, select, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from call_analyzer.config import settings
from call_analyzer.database import get_session
import json as _json

from call_analyzer.models import AnalysisResult, Call, Profile, ProfileResult
from call_analyzer.services import FileTooLargeError, UnsupportedFormatError, save_uploaded_file

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
templates.env.filters["prettyjson"] = lambda v: _json.dumps(v, indent=2, ensure_ascii=False)
templates.env.filters["keyname"] = lambda k: k.replace("_", " ").title()


templates.env.tests["list_value"] = lambda v: isinstance(v, list)
templates.env.tests["dict_value"] = lambda v: isinstance(v, dict)
templates.env.tests["bool_value"] = lambda v: isinstance(v, bool)
templates.env.tests["number_value"] = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
templates.env.globals["base_path"] = settings.root_path


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    stats_q = select(func.count(Call.id))
    total = (await session.execute(stats_q)).scalar() or 0
    fraud = (
        await session.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
        )
    ).scalar() or 0
    profile_calls = (
        await session.execute(select(func.count(ProfileResult.id)))
    ).scalar() or 0

    profiles = (await session.execute(select(Profile).order_by(Profile.name))).scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_calls": total,
        "fraud_calls": fraud,
        "profile_calls": profile_calls,
        "profiles": profiles,
    })


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile,
    profile_id: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    pid = uuid.UUID(profile_id) if profile_id else None

    try:
        call = await save_uploaded_file(file, "upload", session, profile_id=pid)
    except UnsupportedFormatError as e:
        return templates.TemplateResponse("partials/analysis_result.html", {
            "request": request,
            "error": str(e),
        })
    except FileTooLargeError as e:
        return templates.TemplateResponse("partials/analysis_result.html", {
            "request": request,
            "error": str(e),
        })

    if pid:
        call_q = select(Call).options(joinedload(Call.profile), joinedload(Call.profile_result)).where(Call.id == call.id)
        call = (await session.execute(call_q)).unique().scalar_one()

    return templates.TemplateResponse("partials/analysis_result.html", {
        "request": request,
        "call": call,
    })


@router.get("/calls/{call_id}/status", response_class=HTMLResponse)
async def call_status(request: Request, call_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    query = select(Call).options(joinedload(Call.analysis), joinedload(Call.profile), joinedload(Call.profile_result)).where(Call.id == call_id)
    call = (await session.execute(query)).unique().scalar_one_or_none()
    if not call:
        return HTMLResponse("Call not found", status_code=404)
    result = (call.analysis or call.profile_result) if call.status == "done" else None
    return templates.TemplateResponse("partials/analysis_result.html", {
        "request": request,
        "call": call,
        "result": result,
        "error": call.error_message if call.status == "error" else None,
    })


@router.get("/calls", response_class=HTMLResponse)
async def calls_list(
    request: Request,
    is_fraud: str | None = None,
    page: int = 1,
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Call)
        .options(joinedload(Call.analysis), joinedload(Call.profile), joinedload(Call.profile_result))
        .order_by(Call.created_at.desc())
    )
    size = 20

    fraud_filter = None
    if is_fraud == "true":
        fraud_filter = True
        query = query.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(True))
    elif is_fraud == "false":
        fraud_filter = False
        query = query.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(False))
    elif is_fraud == "profile":
        query = query.where(Call.profile_id.isnot(None))

    total_q = select(func.count(Call.id))
    if fraud_filter is True:
        total_q = total_q.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(True))
    elif fraud_filter is False:
        total_q = total_q.join(AnalysisResult).where(AnalysisResult.is_fraud.is_(False))
    elif is_fraud == "profile":
        total_q = total_q.where(Call.profile_id.isnot(None))
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
    query = select(Call).options(joinedload(Call.analysis), joinedload(Call.profile), joinedload(Call.profile_result)).where(Call.id == call_id)
    call = (await session.execute(query)).unique().scalar_one_or_none()
    if not call:
        return HTMLResponse("Call not found", status_code=404)
    return templates.TemplateResponse("call_detail.html", {
        "request": request,
        "call": call,
        "result": call.analysis or call.profile_result,
    })


# ── Profile CRUD (Web UI) ───────────────────────────────────────────

@router.get("/profiles", response_class=HTMLResponse)
async def profiles_list(request: Request, session: AsyncSession = Depends(get_session)):
    profiles = (await session.execute(select(Profile).order_by(Profile.name))).scalars().all()
    return templates.TemplateResponse("profiles.html", {
        "request": request,
        "profiles": profiles,
    })


@router.get("/profiles/new", response_class=HTMLResponse)
async def profile_new(request: Request):
    return templates.TemplateResponse("profile_form.html", {
        "request": request,
        "profile": None,
    })


@router.post("/profiles", response_class=HTMLResponse)
async def profile_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    prompt_mode: str = Form("custom"),
    custom_prompt: str = Form(""),
    expert: str = Form(""),
    main_task: str = Form(""),
    fields_for_json: str = Form(""),
    trigger_words: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if prompt_mode not in ("custom", "template"):
        return templates.TemplateResponse("profile_form.html", {
            "request": request,
            "profile": None,
            "error": "prompt_mode must be 'custom' or 'template'",
        })
    if prompt_mode == "template" and not main_task.strip():
        return templates.TemplateResponse("profile_form.html", {
            "request": request,
            "profile": None,
            "error": "Template mode requires 'main_task' field",
        })

    tw_list = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words.strip() else None

    profile = Profile(
        id=uuid.uuid4(),
        name=name.strip(),
        description=description.strip() or None,
        prompt_mode=prompt_mode,
        custom_prompt=custom_prompt.strip() or None,
        expert=expert.strip() or None,
        main_task=main_task.strip() or None,
        fields_for_json=fields_for_json.strip() or None,
        trigger_words=tw_list,
    )
    session.add(profile)
    await session.commit()
    return RedirectResponse(url=f"{settings.root_path}/profiles", status_code=303)


@router.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
async def profile_edit(request: Request, profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        return HTMLResponse("Profile not found", status_code=404)
    return templates.TemplateResponse("profile_form.html", {
        "request": request,
        "profile": profile,
    })


@router.post("/profiles/{profile_id}/edit", response_class=HTMLResponse)
async def profile_update(
    request: Request,
    profile_id: uuid.UUID,
    name: str = Form(...),
    description: str = Form(""),
    prompt_mode: str = Form("custom"),
    custom_prompt: str = Form(""),
    expert: str = Form(""),
    main_task: str = Form(""),
    fields_for_json: str = Form(""),
    trigger_words: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        return HTMLResponse("Profile not found", status_code=404)

    if prompt_mode not in ("custom", "template"):
        return templates.TemplateResponse("profile_form.html", {
            "request": request,
            "profile": profile,
            "error": "prompt_mode must be 'custom' or 'template'",
        })
    if prompt_mode == "template" and not main_task.strip():
        return templates.TemplateResponse("profile_form.html", {
            "request": request,
            "profile": profile,
            "error": "Template mode requires 'main_task' field",
        })

    profile.name = name.strip()
    profile.description = description.strip() or None
    profile.prompt_mode = prompt_mode
    profile.custom_prompt = custom_prompt.strip() or None
    profile.expert = expert.strip() or None
    profile.main_task = main_task.strip() or None
    profile.fields_for_json = fields_for_json.strip() or None
    profile.trigger_words = [w.strip() for w in trigger_words.split(",") if w.strip()] if trigger_words.strip() else None

    await session.commit()
    return RedirectResponse(url=f"{settings.root_path}/profiles", status_code=303)


@router.post("/profiles/{profile_id}/delete")
async def profile_delete(profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()
    if not profile:
        return HTMLResponse("Profile not found", status_code=404)
    await session.delete(profile)
    await session.commit()
    return RedirectResponse(url=f"{settings.root_path}/profiles", status_code=303)


# ── Dashboard ────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    total = (await session.execute(select(func.count(Call.id)))).scalar() or 0
    fraud = (
        await session.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.is_fraud.is_(True))
        )
    ).scalar() or 0
    profile_count = (
        await session.execute(select(func.count(ProfileResult.id)))
    ).scalar() or 0

    stats = {
        "total_calls": total,
        "fraud_calls": fraud,
        "clean_calls": total - fraud - profile_count,
        "profile_calls": profile_count,
    }

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    day_col = cast(Call.created_at, Date).label("day")
    daily_q = (
        select(day_col, func.count(Call.id).label("total"))
        .where(Call.created_at >= since)
        .group_by(day_col)
        .order_by(day_col)
    )
    daily_rows = (await session.execute(daily_q)).all()

    fraud_q = (
        select(cast(Call.created_at, Date).label("day"), func.count(Call.id).label("fraud"))
        .join(AnalysisResult)
        .where(Call.created_at >= since, AnalysisResult.is_fraud.is_(True))
        .group_by(cast(Call.created_at, Date))
    )
    fraud_map = {str(r.day): r.fraud for r in (await session.execute(fraud_q)).all()}

    daily_stats = [
        {"date": str(r.day), "total": r.total, "fraud": fraud_map.get(str(r.day), 0)}
        for r in daily_rows
    ]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "daily_stats": daily_stats,
    })
