"""Measure local DTMF webhook response latency with a warmed cache."""

from __future__ import annotations

import asyncio
import re
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.main import app


async def main() -> None:
    times = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/welcome")
        action = re.search(r'action="([^"]+)"', response.text).group(1)
        parsed = urlparse(action)
        token = parse_qs(parsed.query)["s"][0]
        await client.post(parsed.path, params={"s": token}, data={"Digits": "1"})
        response = await client.post("/voice/language", params={"s": token}, data={"Digits": "1"})
        pin_action = re.search(r'action="([^"]+)"', response.text).group(1)
        parsed = urlparse(pin_action)
        token = parse_qs(parsed.query)["s"][0]
        response = await client.post(parsed.path, params={"s": token}, data={"Digits": "600001"})
        confirm_action = re.search(r'action="([^"]+)"', response.text).group(1)
        parsed = urlparse(confirm_action)
        token = parse_qs(parsed.query)["s"][0]
        response = await client.post(parsed.path, params={"s": token}, data={"Digits": "1"})
        menu_action = re.search(r'action="([^"]+)"', response.text).group(1)
        parsed = urlparse(menu_action)
        token = parse_qs(parsed.query)["s"][0]
        for _ in range(10):
            start = time.perf_counter()
            response = await client.post(parsed.path, params={"s": token}, data={"Digits": "0"})
            times.append((time.perf_counter() - start) * 1000)
            action = re.search(r'action="([^"]+)"', response.text).group(1)
            parsed = urlparse(action)
            token = parse_qs(parsed.query)["s"][0]
    values = sorted(times)
    p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
    print({"samples": len(values), "p50_ms": round(statistics.median(values), 1), "p95_ms": round(p95, 1), "max_ms": round(max(values), 1)})


if __name__ == "__main__":
    asyncio.run(main())
