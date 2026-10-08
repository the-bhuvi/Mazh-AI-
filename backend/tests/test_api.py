import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.llm.client import validate_numbers_in_reply

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

@pytest.mark.asyncio
async def test_weather_endpoint_with_place():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/weather?place=Chennai")
        assert resp.status_code == 200
        data = resp.json()
        assert "Chennai" in data["location"]["name"]
        assert "current" in data
        assert "risks" in data
        assert "insight" in data
        assert "meta" in data

@pytest.mark.asyncio
async def test_weather_endpoint_with_pin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/weather?pin=641001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"]["lat"] == pytest.approx(11.0168, rel=1e-2)

@pytest.mark.asyncio
async def test_predict_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"lat": 13.0827, "lon": 80.2707}
        resp = await client.post("/predict", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert data["level"] in ["low", "moderate", "high"]

@pytest.mark.asyncio
async def test_sms_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"phone": "+919876543210", "place": "Coimbatore"}
        resp = await client.post("/sms", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["sent", "simulated"]

@pytest.mark.asyncio
async def test_chat_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "session_id": "test_sess_1",
            "message": "Is it safe to dry clothes in Madurai today?",
            "place": "Madurai",
            "lang": "en"
        }
        resp = await client.post("/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert data["intent"] == "CLOTHES_DRYING"

def test_number_grounding_validation():
    insight = {
        "location": {"name": "Chennai", "lat": 13.08, "lon": 80.27},
        "current": {"temp_c": 31.0, "humidity": 75},
        "hourly": [{"rain_prob": 85, "rain_mm": 12.5}],
        "risks": []
    }
    
    # Valid reply using ground truth numbers
    valid_reply = "In Chennai, temperature is 31.0°C with 85% rain probability."
    assert validate_numbers_in_reply(valid_reply, insight) is True
    
    # Invalid reply inventing non-existent temperature/rainfall number
    invalid_reply = "In Chennai, temperature is 99.0°C with 100% rain probability."
    assert validate_numbers_in_reply(invalid_reply, insight) is False
