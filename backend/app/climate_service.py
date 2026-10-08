"""Cached NOAA CPC ONI climate context.

ENSO is deliberately treated as seasonal context, not as a six-hour forecast
signal. The cached value is refreshed at most once per day and failures return
unknown context rather than inventing a current climate state.
"""

import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import DATA_DIR

logger = logging.getLogger(__name__)
NOAA_ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
CLIMATE_CACHE = DATA_DIR / "enso_cache.csv"
CACHE_MAX_AGE_SECONDS = 86_400


def _state(anomaly: float) -> str:
    if anomaly >= 0.5:
        return "el_nino"
    if anomaly <= -0.5:
        return "la_nina"
    return "neutral"


def _parse_latest(text: str) -> tuple[str, float] | None:
    latest: tuple[int, int, float] | None = None
    month_by_season = {
        "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
        "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
    }
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] not in month_by_season:
            continue
        try:
            year, anomaly = int(fields[1]), float(fields[3])
        except ValueError:
            continue
        marker = (year, month_by_season[fields[0]], anomaly)
        if latest is None or marker[:2] > latest[:2]:
            latest = marker
    if latest is None:
        return None
    return _state(latest[2]), latest[2]


def _read_cache() -> dict[str, Any] | None:
    if not CLIMATE_CACHE.exists() or (datetime.now(timezone.utc).timestamp() - CLIMATE_CACHE.stat().st_mtime) > CACHE_MAX_AGE_SECONDS:
        return None
    try:
        with CLIMATE_CACHE.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        return {"enso_state": row["enso_state"], "nino34_anom": float(row["nino34_anom"])}
    except (StopIteration, KeyError, ValueError, OSError):
        return None


def _write_cache(state: str, anomaly: float) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CLIMATE_CACHE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fetched_at", "enso_state", "nino34_anom"])
        writer.writeheader()
        writer.writerow({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "enso_state": state,
            "nino34_anom": anomaly,
        })
    return {"enso_state": state, "nino34_anom": anomaly}


async def get_climate_state() -> dict[str, Any]:
    cached = _read_cache()
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(NOAA_ONI_URL)
            response.raise_for_status()
        parsed = _parse_latest(response.text)
        if parsed:
            return _write_cache(*parsed)
    except Exception as exc:
        logger.warning("NOAA ONI fetch failed: %s", exc)
    # No stale/fabricated El Niño default: downstream metadata makes the
    # uncertainty visible to users.
    return {"enso_state": "unknown", "nino34_anom": None}
