"""Run the keypad IVR locally without a phone or Twilio credentials."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.main import app


ACTION_RE = re.compile(r'action="([^"]+)"')
SAY_RE = re.compile(r"<(?:Say|Play)[^>]*>(.*?)</(?:Say|Play)>")


async def post(client: httpx.AsyncClient, url: str, digits: str | None = None, caller: str = "+919876543210"):
    parsed = urlparse(url)
    data = {"From": caller}
    if digits is not None:
        data["Digits"] = digits
    response = await client.post(parsed.path, params=parse_qs(parsed.query), data=data)
    response.raise_for_status()
    xml = response.text
    speech = " ".join(SAY_RE.findall(xml))
    print(f"\n[{parsed.path}] {speech}")
    match = ACTION_RE.search(xml)
    return match.group(1) if match else None


async def simulate(pin: str, city_fallback: bool = False) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        action = await post(client, "/voice/welcome")
        action = await post(client, action, "1")
        action = await post(client, action, "000000" if city_fallback else pin)
        if city_fallback:
            action = await post(client, action, "000000")
            action = await post(client, action, "1")
        else:
            action = await post(client, action, "1")
        action = await post(client, action, "1")
        action = await post(client, action, "2")
        await post(client, action, "0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", default="600001")
    parser.add_argument("--city-fallback", action="store_true")
    args = parser.parse_args()
    asyncio.run(simulate(args.pin, args.city_fallback))


if __name__ == "__main__":
    main()
