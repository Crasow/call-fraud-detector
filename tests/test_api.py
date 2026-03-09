import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from call_fraud_detector.app import create_app
from call_fraud_detector.models import AnalysisResult, Call


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_call_and_result():
    call_id = uuid.uuid4()
    call = Call(
        id=call_id,
        filename="test.wav",
        audio_format="wav",
        source="api",
        created_at=datetime.now(UTC),
    )
    result = AnalysisResult(
        id=uuid.uuid4(),
        call_id=call_id,
        transcript="Hello",
        is_fraud=True,
        fraud_score=0.85,
        fraud_categories=["Vishing"],
        reasons=["Suspicious"],
        analyzed_at=datetime.now(UTC),
    )
    call.analysis = result
    return call, result


@pytest.mark.asyncio
async def test_analyze_endpoint(client):
    call, result = _make_call_and_result()

    with patch("call_fraud_detector.api.analyze_bytes", new_callable=AsyncMock, return_value=(call, result)):
        resp = await client.post(
            "/api/v1/calls/analyze",
            files={"file": ("test.wav", b"fake audio", "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "test.wav"
    assert data["analysis"]["is_fraud"] is True
