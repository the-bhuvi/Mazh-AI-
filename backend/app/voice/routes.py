from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import CITIES_FILE
from app.location import get_lat_lon_from_pin
from app.sms.twilio_adapter import validate_phone_number
from app.voice.phrases import phrase, render_insight
from app.voice.security import validate_twilio_request
from app.voice.state import InvalidVoiceToken, action_url, advance_idle, decode_state
from app.voice.twilio_adapter import gather, goodbye, say_and_menu

logger = logging.getLogger(__name__)
voice_router = APIRouter()


def load_cities_menu() -> list[dict[str, Any]]:
    if CITIES_FILE.exists():
        return json.loads(CITIES_FILE.read_text(encoding="utf-8"))
    return []


def _response(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


async def _form(request: Request) -> dict[str, str]:
    form = {str(key): str(value) for key, value in (await request.form()).items()}
    if not validate_twilio_request(request, form):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    if request.query_params.get("s"):
        form["s"] = request.query_params["s"]
    return form


def _state(token: str | None) -> dict[str, Any]:
    try:
        return decode_state(token)
    except InvalidVoiceToken as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired voice state") from exc


def _menu_state(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "step": "menu", "idle_count": 0}


def _menu(state: dict[str, Any], lang: str, messages: list[str] | None = None) -> str:
    return say_and_menu(
        messages or [],
        phrase(lang, "menu"),
        action_url("/voice/menu", _menu_state(state)),
        lang,
    )


def _idle(state: dict[str, Any], lang: str, path: str, prompt: str, digits: int = 1) -> str:
    updated = advance_idle(state)
    if updated["idle_count"] >= 3:
        return goodbye(phrase(lang, "goodbye"), lang)
    return gather(prompt, action_url(path, updated), lang, digits)


def _get_services():
    # Deferred imports avoid a module cycle: main owns the existing service and
    # insight builder, while this router owns only the Twilio flow.
    from app.main import get_or_build_insight, set_cached_insight, sms_provider
    return get_or_build_insight, set_cached_insight, sms_provider


def _prefetch(state: dict[str, Any]) -> None:
    get_or_build_insight, set_cached_insight, _ = _get_services()

    async def run() -> None:
        try:
            insight = await get_or_build_insight(
                lat=state["lat"], lon=state["lon"], place_name_override=state.get("place")
            )
            set_cached_insight(state["lat"], state["lon"], insight)
        except Exception as exc:
            logger.warning("Voice insight prefetch failed: %s", exc)

    asyncio.create_task(run())


@voice_router.post("/voice/welcome")
async def welcome(request: Request):
    await _form(request)
    state = {"step": "language", "idle_count": 0}
    return _response(gather(phrase("en", "welcome"), action_url("/voice/language", state), "en"))


@voice_router.post("/voice/language")
async def language(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    if form.get("Digits") not in {"1", "2"}:
        return _response(_idle(state, "en", "/voice/language", phrase("en", "welcome")))
    lang = "ta" if form["Digits"] == "2" else "en"
    pin_state = {"step": "pin", "lang": lang, "attempts": 0, "idle_count": 0}
    return _response(gather(phrase(lang, "pin_prompt"), action_url("/voice/pin", pin_state), lang, 6, 8))


@voice_router.post("/voice/pin")
async def pin(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    digits = form.get("Digits", "")
    if not digits:
        return _response(_idle(state, lang, "/voice/pin", phrase(lang, "pin_prompt"), 6))
    try:
        location = await get_lat_lon_from_pin(digits)
    except ValueError:
        attempts = int(state.get("attempts", 0)) + 1
        if attempts >= 2:
            city_state = {**state, "step": "city", "attempts": attempts, "idle_count": 0}
            return _response(gather(phrase(lang, "city_prompt"), action_url("/voice/city", city_state), lang))
        retry = {**state, "attempts": attempts, "idle_count": 0}
        return _response(gather(phrase(lang, "pin_invalid"), action_url("/voice/pin", retry), lang, 6, 8))

    confirmed = {
        **state,
        "step": "pin_confirm",
        "pin": digits,
        "lat": float(location["lat"]),
        "lon": float(location["lon"]),
        "place": location["name"],
        "attempts": 0,
        "idle_count": 0,
    }
    return _response(gather(
        phrase(lang, "pin_readback", pin=" ".join(digits)),
        action_url("/voice/pin-confirm", confirmed),
        lang,
    ))


@voice_router.post("/voice/pin-confirm")
async def pin_confirm(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    if form.get("Digits") == "1":
        _prefetch(state)
        return _response(_menu(state, lang))
    if form.get("Digits") == "2":
        retry = {**state, "step": "pin", "attempts": 0, "idle_count": 0}
        return _response(gather(phrase(lang, "pin_prompt"), action_url("/voice/pin", retry), lang, 6, 8))
    return _response(_idle(
        state, lang, "/voice/pin-confirm",
        phrase(lang, "pin_readback", pin=" ".join(state.get("pin", ""))),
    ))


@voice_router.post("/voice/city")
async def city(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    selected = next((item for item in load_cities_menu() if item.get("digit") == form.get("Digits")), None)
    if selected is None:
        return _response(gather(phrase(lang, "city_prompt"), action_url("/voice/city", state), lang))
    chosen = {
        **state, "step": "menu", "lat": float(selected["lat"]), "lon": float(selected["lon"]),
        "place": selected["name"], "pin": selected.get("pincode"), "idle_count": 0,
    }
    _prefetch(chosen)
    return _response(_menu(chosen, lang))


@voice_router.post("/voice/menu")
async def menu(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    digits = form.get("Digits")
    if not digits:
        return _response(_idle(state, lang, "/voice/menu", phrase(lang, "menu")))
    if digits == "9":
        pin_state = {**state, "step": "pin", "attempts": 0, "idle_count": 0}
        return _response(gather(phrase(lang, "pin_prompt"), action_url("/voice/pin", pin_state), lang, 6, 8))
    if digits == "0":
        return _response(_menu(state, lang))
    if digits == "5":
        sms_state = {**state, "step": "sms_choice", "idle_count": 0}
        return _response(gather(phrase(lang, "sms_prompt"), action_url("/voice/sms-choice", sms_state), lang))
    if digits not in {"1", "2", "3", "4"}:
        return _response(_menu(state, lang, [phrase(lang, "invalid_menu")]))
    try:
        get_or_build_insight, _, _ = _get_services()
        insight = await get_or_build_insight(
            lat=state["lat"], lon=state["lon"], place_name_override=state.get("place")
        )
        view = {"1": "rain", "2": "today", "3": "tomorrow", "4": "alerts"}[digits]
        return _response(_menu(state, lang, [render_insight(insight, lang, view)]))
    except Exception as exc:
        logger.warning("Voice menu insight failed: %s", exc)
        return _response(_menu(state, lang, [phrase(lang, "sms_failed")]))


@voice_router.post("/voice/sms-choice")
async def sms_choice(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    if form.get("Digits") == "2":
        return _response(gather(
            phrase(lang, "number_prompt"),
            action_url("/voice/sms-number", {**state, "step": "sms_number", "idle_count": 0}),
            lang, 10, 10,
        ))
    if form.get("Digits") != "1":
        return _response(_idle(state, lang, "/voice/sms-choice", phrase(lang, "sms_prompt")))
    return _response(await _send_sms(state, form.get("From"), lang))


@voice_router.post("/voice/sms-number")
async def sms_number(request: Request):
    form = await _form(request)
    state = _state(form.get("s"))
    lang = state.get("lang", "en")
    number = form.get("Digits", "")
    if len(number) != 10 or not number.isdigit():
        return _response(gather(phrase(lang, "number_prompt"), action_url("/voice/sms-number", state), lang, 10, 10))
    return _response(await _send_sms(state, number, lang))


async def _send_sms(state: dict[str, Any], number: str | None, lang: str) -> str:
    try:
        if not number:
            raise ValueError("caller number unavailable")
        valid_number = validate_phone_number(number)
        get_or_build_insight, _, sms_provider = _get_services()
        insight = await get_or_build_insight(
            lat=state["lat"], lon=state["lon"], place_name_override=state.get("place")
        )
        result = await sms_provider.send_sms(valid_number, insight["insight"]["sms_text"])
        message = phrase(lang, "sms_sent") if result["status"] in {"sent", "simulated"} else phrase(lang, "sms_failed")
    except Exception:
        message = phrase(lang, "sms_failed")
    return _menu(state, lang, [message])
