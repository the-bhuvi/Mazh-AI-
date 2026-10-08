from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def action(xml: str) -> str:
    match = re.search(r'action="([^"]+)"', xml)
    assert match
    return match.group(1)


def post_data(url: str, digits: str | None = None) -> tuple[str, dict[str, str]]:
    parsed = urlparse(url)
    data = {"From": "+919876543210"}
    if digits is not None:
        data["Digits"] = digits
    return parsed.path, {key: values[0] for key, values in parse_qs(parsed.query).items()} | data


@pytest.mark.asyncio
async def test_voice_pin_confirmation_and_menu():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/welcome")
        language = action(response.text)
        path, params = post_data(language, "1")
        response = await client.post(path, params={"s": params["s"]}, data={"Digits": "1", "From": params["From"]})
        pin_url = action(response.text)
        path, params = post_data(pin_url, "600001")
        response = await client.post(path, params={"s": params["s"]}, data={"Digits": "600001", "From": params["From"]})
        confirm_url = action(response.text)
        path, params = post_data(confirm_url, "1")
        response = await client.post(path, params={"s": params["s"]}, data={"Digits": "1", "From": params["From"]})
        assert response.status_code == 200
        assert "<Gather" in response.text
        assert 'numDigits="1"' in response.text


@pytest.mark.asyncio
async def test_unknown_pin_twice_offers_cities():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/welcome")
        language = action(response.text)
        token = parse_qs(urlparse(language).query)["s"][0]
        response = await client.post("/voice/language", params={"s": token}, data={"Digits": "1"})
        pin_url = action(response.text)
        token = parse_qs(urlparse(pin_url).query)["s"][0]
        response = await client.post("/voice/pin", params={"s": token}, data={"Digits": "000000"})
        retry_url = action(response.text)
        token = parse_qs(urlparse(retry_url).query)["s"][0]
        response = await client.post("/voice/pin", params={"s": token}, data={"Digits": "000000"})
        assert "Choose a city" in response.text
        assert "/voice/city" in response.text


@pytest.mark.asyncio
async def test_tampered_state_is_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/language", params={"s": "bad.token"}, data={"Digits": "1"})
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_three_idle_prompts_hang_up():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/welcome")
        url = action(response.text)
        for _ in range(3):
            token = parse_qs(urlparse(url).query)["s"][0]
            response = await client.post(urlparse(url).path, params={"s": token}, data={})
            if "<Hangup" in response.text:
                break
            url = action(response.text)
        assert "<Hangup" in response.text


@pytest.mark.asyncio
async def test_preset_city_and_sms_menu_paths():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/welcome")
        language_url = action(response.text)
        token = parse_qs(urlparse(language_url).query)["s"][0]
        response = await client.post("/voice/language", params={"s": token}, data={"Digits": "1"})
        pin_url = action(response.text)
        token = parse_qs(urlparse(pin_url).query)["s"][0]
        response = await client.post("/voice/pin", params={"s": token}, data={"Digits": "000000"})
        retry_url = action(response.text)
        token = parse_qs(urlparse(retry_url).query)["s"][0]
        response = await client.post("/voice/pin", params={"s": token}, data={"Digits": "000000"})
        city_url = action(response.text)
        token = parse_qs(urlparse(city_url).query)["s"][0]
        response = await client.post("/voice/city", params={"s": token}, data={"Digits": "1"})
        menu_url = action(response.text)
        token = parse_qs(urlparse(menu_url).query)["s"][0]
        response = await client.post("/voice/menu", params={"s": token}, data={"Digits": "5"})
        assert "/voice/sms-choice" in response.text
        sms_url = action(response.text)
        token = parse_qs(urlparse(sms_url).query)["s"][0]
        response = await client.post("/voice/sms-choice", params={"s": token}, data={"Digits": "2"})
        assert "/voice/sms-number" in response.text
