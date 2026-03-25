import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from call_analyzer.app import create_app
from call_analyzer.models import AnalysisResult, Call


@pytest.fixture
def app():
    with patch("call_analyzer.app.worker_loop", new_callable=AsyncMock):
        yield create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_pending_call():
    call = Call(
        id=uuid.uuid4(),
        filename="test.wav",
        audio_format="wav",
        source="api",
        status="pending",
        created_at=datetime.now(UTC),
    )
    return call


@pytest.mark.asyncio
async def test_analyze_endpoint(client):
    call = _make_pending_call()

    async def fake_create(file, source, session):
        return call

    with patch("call_analyzer.api._create_pending_call", new_callable=AsyncMock, return_value=call):
        resp = await client.post(
            "/api/v1/calls/analyze",
            files={"file": ("test.wav", b"fake audio", "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(call.id)
    assert data["status"] == "pending"
