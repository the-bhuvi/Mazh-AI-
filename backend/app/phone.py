from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import PHONE_API_KEY
from app.location import get_lat_lon_from_pin
from app.sms.twilio_adapter import validate_phone_number

phone_router = APIRouter(prefix="/api/phone", tags=["asterisk"])


class PhonePinRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PhoneSmsRequest(PhonePinRequest):
    phone: str = Field(min_length=1, max_length=32)


def _authorize(api_key: str | None) -> None:
    if not PHONE_API_KEY:
        raise HTTPException(status_code=503, detail="Phone API is not configured")
    if api_key != PHONE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid phone API key")


async def _insight_for_pin(pin: str) -> dict[str, Any]:
    from app.main import get_or_build_insight

    try:
        location = await get_lat_lon_from_pin(pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid postal PIN code") from exc
    return await get_or_build_insight(
        lat=float(location["lat"]),
        lon=float(location["lon"]),
        place_name_override=str(location["name"]),
    )


def _risk_message(insight: dict[str, Any]) -> str:
    risk = max(insight["risks"], key=lambda item: item["score"])
    return (
        f'{insight["location"]["name"]}. '
        f'Rain risk is {risk["level"]}. {insight["insight"]["summary"]}'
    )


def _daily_message(insight: dict[str, Any], index: int, label: str) -> str:
    days = insight.get("daily", [])
    if index >= len(days):
        return f"{label} forecast is not available right now."
    day = days[index]
    return (
        f'{label} in {insight["location"]["name"]}: '
        f'minimum {day["min_c"]:.0f} degrees, maximum {day["max_c"]:.0f} degrees, '
        f'rain probability {day["rain_prob"]} percent.'
    )


async def _run(request: PhonePinRequest, api_key: str | None, builder: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    _authorize(api_key)
    insight = await _insight_for_pin(request.pin)
    return {
        "success": True,
        "location": insight["location"],
        "message": builder(insight),
        "rain_risk": max(insight["risks"], key=lambda item: item["score"])["level"],
    }


@phone_router.post("/weather")
async def phone_weather(request: PhonePinRequest, x_phone_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    return await _run(request, x_phone_api_key, lambda insight: _risk_message(insight))


@phone_router.post("/today")
async def phone_today(request: PhonePinRequest, x_phone_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    return await _run(request, x_phone_api_key, lambda insight: _daily_message(insight, 0, "Today's"))


@phone_router.post("/tomorrow")
async def phone_tomorrow(request: PhonePinRequest, x_phone_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    return await _run(request, x_phone_api_key, lambda insight: _daily_message(insight, 1, "Tomorrow's"))


@phone_router.post("/alerts")
async def phone_alerts(request: PhonePinRequest, x_phone_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    def alerts(insight: dict[str, Any]) -> str:
        items = [
            f'{item["type"].replace("_", " ")} risk is {item["level"]}'
            for item in insight["risks"]
            if item["level"] != "low"
        ]
        return "No significant weather alerts." if not items else "Alerts: " + ". ".join(items) + "."

    return await _run(request, x_phone_api_key, alerts)


@phone_router.post("/sms")
async def phone_sms(request: PhoneSmsRequest, x_phone_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_phone_api_key)
    try:
        validate_phone_number(request.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid phone number") from exc
    insight = await _insight_for_pin(request.pin)
    from app.main import sms_provider

    result = await sms_provider.send_sms(request.phone, insight["insight"]["sms_text"])
    return {"success": result["status"] in {"sent", "simulated"}, **result}
