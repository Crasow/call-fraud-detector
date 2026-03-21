import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from call_fraud_detector.audio import (
    encode_audio_base64,
    encode_bytes_base64,
    get_audio_format,
    get_mime_type,
)
from call_fraud_detector.gemini_client import generate_content
from call_fraud_detector.models import AnalysisResult, Call, Profile

ANALYSIS_PROMPT = """\
You are a phone call fraud detection expert. Analyze this audio recording and provide:

1. A full transcript of the call
2. Whether this call is fraudulent
3. A fraud score from 0.0 (definitely legitimate) to 1.0 (definitely fraud)
4. Categories of fraud detected (if any)
5. Specific reasons for your assessment

Fraud categories to consider:
- Social Engineering: manipulating the victim into revealing information
- Impersonation: pretending to be someone else (bank, government, tech support, etc.)
- Urgency/Pressure: creating false urgency to force quick decisions
- Financial Fraud: requesting money transfers, gift cards, cryptocurrency
- Information Harvesting: collecting personal data (SSN, bank details, passwords)
- Vishing: voice phishing attempts

Respond in JSON format:
{
    "transcript": "full transcript of the call",
    "is_fraud": true/false,
    "fraud_score": 0.0-1.0,
    "fraud_categories": ["category1", "category2"],
    "reasons": ["reason1", "reason2"]
}
"""


def build_prompt(profile: Profile | None) -> str:
    """Build analysis prompt based on the profile configuration."""
    if profile is None:
        return ANALYSIS_PROMPT

    prompt = None
    trigger_words = profile.trigger_words or []

    if profile.prompt_mode == "custom" and profile.custom_prompt:
        prompt = profile.custom_prompt
    elif profile.prompt_mode == "template" and profile.main_task:
        expert = profile.expert or "анализ телефонных разговоров"
        parts = [f"Ты эксперт в {expert}. {profile.main_task}."]
        if profile.fields_for_json:
            parts.append(f"Верни ответ в формате JSON с полями: {profile.fields_for_json}.")
        prompt = " ".join(parts)

    if prompt and trigger_words:
        words = ", ".join(trigger_words)
        prompt += f"\n\nТакже найди совпадения для слов: {words}"
        return prompt
    elif prompt:
        return prompt
    elif trigger_words:
        words = ", ".join(trigger_words)
        return (
            f"Проанализируй аудиозапись. Найди совпадения и контекст для слов: {words}. "
            "Верни JSON с полями: transcript, matches."
        )

    # Fallback: profile exists but no prompt and no trigger words
    return ANALYSIS_PROMPT


def _parse_gemini_response(raw: dict) -> dict:
    text = raw["candidates"][0]["content"]["parts"][0]["text"]
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]  # remove first line (```json)
        text = text.rsplit("```", 1)[0]  # remove closing ```
    return json.loads(text)


async def analyze_call(call: Call, session: AsyncSession) -> AnalysisResult:
    """Analyze an existing Call record (used by the background worker)."""
    if call.file_path:
        audio_b64 = encode_audio_base64(Path(call.file_path))
    else:
        raise ValueError("Call has no file_path")

    mime_type = get_mime_type(call.filename)
    prompt = build_prompt(call.profile)
    raw_response = await generate_content(audio_b64, mime_type, prompt)
    parsed = _parse_gemini_response(raw_response)

    result = AnalysisResult(
        id=uuid.uuid4(),
        call_id=call.id,
        transcript=parsed.get("transcript"),
        is_fraud=parsed.get("is_fraud", False),
        fraud_score=parsed.get("fraud_score", 0.0),
        fraud_categories=parsed.get("fraud_categories", []),
        reasons=parsed.get("reasons", []),
        raw_response=raw_response,
        analyzed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result


async def analyze_file(
    file_path: Path,
    source: str,
    session: AsyncSession,
    profile_id: uuid.UUID | None = None,
) -> tuple[Call, AnalysisResult]:
    filename = file_path.name
    audio_format = get_audio_format(filename)
    mime_type = get_mime_type(filename)
    audio_b64 = encode_audio_base64(file_path)

    # Load profile if specified
    profile = None
    if profile_id:
        profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()

    prompt = build_prompt(profile)
    raw_response = await generate_content(audio_b64, mime_type, prompt)
    parsed = _parse_gemini_response(raw_response)

    call = Call(
        id=uuid.uuid4(),
        filename=filename,
        audio_format=audio_format,
        source=source,
        file_path=str(file_path),
        profile_id=profile_id,
    )
    session.add(call)

    result = AnalysisResult(
        id=uuid.uuid4(),
        call_id=call.id,
        transcript=parsed.get("transcript"),
        is_fraud=parsed.get("is_fraud", False),
        fraud_score=parsed.get("fraud_score", 0.0),
        fraud_categories=parsed.get("fraud_categories", []),
        reasons=parsed.get("reasons", []),
        raw_response=raw_response,
        analyzed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(result)
    await session.commit()
    await session.refresh(call)
    await session.refresh(result)

    return call, result


async def analyze_bytes(
    data: bytes,
    filename: str,
    source: str,
    session: AsyncSession,
    save_path: Path | None = None,
    profile_id: uuid.UUID | None = None,
) -> tuple[Call, AnalysisResult]:
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(data)

    mime_type = get_mime_type(filename)
    logger.warning("=== ANALYZE BYTES ===")
    logger.warning("File: %s, size: %d bytes, MIME: %s", filename, len(data), mime_type)
    audio_b64 = encode_bytes_base64(data)
    logger.warning("Base64 encoded size: %d bytes", len(audio_b64))

    # Load profile if specified
    profile = None
    if profile_id:
        profile = (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one_or_none()

    prompt = build_prompt(profile)
    logger.warning("Calling Gemini...")
    raw_response = await generate_content(audio_b64, mime_type, prompt)
    logger.warning("Gemini returned, parsing response...")
    parsed = _parse_gemini_response(raw_response)
    logger.warning("Parsed result: is_fraud=%s, score=%s", parsed.get("is_fraud"), parsed.get("fraud_score"))

    call = Call(
        id=uuid.uuid4(),
        filename=filename,
        audio_format=get_audio_format(filename),
        source=source,
        file_path=str(save_path) if save_path else None,
        profile_id=profile_id,
    )
    session.add(call)

    result = AnalysisResult(
        id=uuid.uuid4(),
        call_id=call.id,
        transcript=parsed.get("transcript"),
        is_fraud=parsed.get("is_fraud", False),
        fraud_score=parsed.get("fraud_score", 0.0),
        fraud_categories=parsed.get("fraud_categories", []),
        reasons=parsed.get("reasons", []),
        raw_response=raw_response,
        analyzed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(result)
    await session.commit()
    await session.refresh(call)
    await session.refresh(result)

    return call, result
