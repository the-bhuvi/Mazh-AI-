from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.phone as phone
from app.main import app


@pytest.fixture
def phone_key(monkeypatch):
    monkeypatch.setattr(phone, "PHONE_API_KEY", "test-phone-key")
    return "test-phone-key"


@pytest.mark.asyncio
async def test_phone_api_rejects_missing_or_invalid_key(phone_key):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/phone/weather", json={"pin": "600001"})
        assert response.status_code == 401
        response = await client.post(
            "/api/phone/weather",
            json={"pin": "123"},
            headers={"X-Phone-API-Key": phone_key},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_phone_api_returns_voice_message(monkeypatch, phone_key):
    async def fake_insight(pin):
        return {
            "location": {"name": "Chennai", "lat": 13.08, "lon": 80.27},
            "risks": [{"score": 0.8, "level": "high", "type": "heavy_rain"}],
            "insight": {"summary": "Rain is likely this evening."},
        }

    monkeypatch.setattr(
        phone,
        "_insight_for_pin",
        fake_insight,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/phone/weather",
            json={"pin": "600001"},
            headers={"X-Phone-API-Key": phone_key},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Chennai. Rain risk is high. Rain is likely this evening."
