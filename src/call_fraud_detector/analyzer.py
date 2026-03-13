import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from call_fraud_detector.audio import (
    encode_audio_base64,
    encode_bytes_base64,
    get_audio_format,
    get_mime_type,
)
from call_fraud_detector.gemini_client import generate_content
from call_fraud_detector.models import AnalysisResult, Call

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


def _parse_gemini_response(raw: dict) -> dict:
    text = raw["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


async def analyze_call(call: Call, session: AsyncSession) -> AnalysisResult:
    """Analyze an existing Call record (used by the background worker)."""
    if call.file_path:
        audio_b64 = encode_audio_base64(Path(call.file_path))
    else:
        raise ValueError("Call has no file_path")

    mime_type = get_mime_type(call.filename)
    raw_response = await generate_content(audio_b64, mime_type, ANALYSIS_PROMPT)
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
) -> tuple[Call, AnalysisResult]:
    filename = file_path.name
    audio_format = get_audio_format(filename)
    mime_type = get_mime_type(filename)
    audio_b64 = encode_audio_base64(file_path)

    raw_response = await generate_content(audio_b64, mime_type, ANALYSIS_PROMPT)
    parsed = _parse_gemini_response(raw_response)

    call = Call(
        id=uuid.uuid4(),
        filename=filename,
        audio_format=audio_format,
        source=source,
        file_path=str(file_path),
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
) -> tuple[Call, AnalysisResult]:
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(data)

    mime_type = get_mime_type(filename)
    logger.warning("=== ANALYZE BYTES ===")
    logger.warning("File: %s, size: %d bytes, MIME: %s", filename, len(data), mime_type)
    audio_b64 = encode_bytes_base64(data)
    logger.warning("Base64 encoded size: %d bytes", len(audio_b64))

    logger.warning("Calling Gemini...")
    raw_response = await generate_content(audio_b64, mime_type, ANALYSIS_PROMPT)
    logger.warning("Gemini returned, parsing response...")
    parsed = _parse_gemini_response(raw_response)
    logger.warning("Parsed result: is_fraud=%s, score=%s", parsed.get("is_fraud"), parsed.get("fraud_score"))

    call = Call(
        id=uuid.uuid4(),
        filename=filename,
        audio_format=get_audio_format(filename),
        source=source,
        file_path=str(save_path) if save_path else None,
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
