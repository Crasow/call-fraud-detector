"""Integration test with real Gemini proxy. Requires tunnel to server."""

import pytest

from call_fraud_detector.audio import encode_audio_base64, get_mime_type
from call_fraud_detector.analyzer import _parse_gemini_response
from call_fraud_detector.gemini_client import generate_content

from pathlib import Path

TEST_AUDIO = Path(__file__).parent / "test-audio.mp3"

PROMPT = """\
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


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_AUDIO.exists(), reason="test-audio.mp3 not found")
async def test_gemini_real_call():
    """Send real audio to Gemini and validate response structure."""
    audio_b64 = encode_audio_base64(TEST_AUDIO)
    mime_type = get_mime_type(TEST_AUDIO.name)

    raw = await generate_content(audio_b64, mime_type, PROMPT)

    # Validate raw response structure
    assert "candidates" in raw
    assert len(raw["candidates"]) > 0
    assert "content" in raw["candidates"][0]

    # Parse and validate
    parsed = _parse_gemini_response(raw)

    assert "transcript" in parsed
    assert isinstance(parsed["transcript"], str)
    assert len(parsed["transcript"]) > 0

    assert "is_fraud" in parsed
    assert isinstance(parsed["is_fraud"], bool)

    assert "fraud_score" in parsed
    assert isinstance(parsed["fraud_score"], (int, float))
    assert 0.0 <= parsed["fraud_score"] <= 1.0

    assert "fraud_categories" in parsed
    assert isinstance(parsed["fraud_categories"], list)

    assert "reasons" in parsed
    assert isinstance(parsed["reasons"], list)

    # Print results for manual review
    print(f"\n{'='*60}")
    print(f"Transcript (first 200 chars): {parsed['transcript'][:200]}...")
    print(f"Is fraud: {parsed['is_fraud']}")
    print(f"Fraud score: {parsed['fraud_score']}")
    print(f"Categories: {parsed['fraud_categories']}")
    print(f"Reasons: {parsed['reasons']}")
    print(f"{'='*60}")
