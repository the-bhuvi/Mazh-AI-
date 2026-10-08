import sqlite3
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from app.config import DB_PATH, CITIES_FILE

logger = logging.getLogger(__name__)

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_cache_tables():
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insight_cache (
            location_key TEXT PRIMARY KEY,
            insight_json TEXT,
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()

init_cache_tables()

def _make_key(lat: float, lon: float) -> str:
    return f"{round(lat, 2)},{round(lon, 2)}"

def get_cached_insight(lat: float, lon: float, ttl_seconds: int = 900) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Retrieves cached insight JSON.
    Returns: (insight_dict, is_stale)
    If cached item exists but updated_at > ttl_seconds, is_stale=True.
    """
    key = _make_key(lat, lon)
    conn = _get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT insight_json, updated_at FROM insight_cache WHERE location_key = ?", (key,)).fetchone()
    conn.close()

    if not row:
        return None, False

    try:
        insight = json.loads(row["insight_json"])
        age = time.time() - float(row["updated_at"])
        is_stale = age > ttl_seconds
        return insight, is_stale
    except Exception as e:
        logger.error(f"Failed to parse cached insight for key {key}: {e}")
        return None, False

def set_cached_insight(lat: float, lon: float, insight: Dict[str, Any]):
    key = _make_key(lat, lon)
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO insight_cache (location_key, insight_json, updated_at)
        VALUES (?, ?, ?)
    """, (key, json.dumps(insight), time.time()))
    conn.commit()
    conn.close()

async def refresh_preset_cities(build_insight_fn):
    """
    Refreshes preset cities from config/cities.json in the background.
    """
    if not CITIES_FILE.exists():
        logger.warning(f"Cities config file not found at {CITIES_FILE}")
        return

    try:
        with open(CITIES_FILE, "r", encoding="utf-8") as f:
            cities = json.load(f)

        logger.info(f"Background refresh starting for {len(cities)} preset cities...")
        for city in cities:
            try:
                lat = float(city["lat"])
                lon = float(city["lon"])
                name = city["name"]
                logger.info(f"Background refreshing insight for {name} ({lat}, {lon})...")
                insight = await build_insight_fn(
                    lat=lat,
                    lon=lon,
                    place_name_override=name,
                )
                set_cached_insight(lat, lon, insight)
            except Exception as e:
                logger.error(f"Failed to refresh preset city {city.get('name')}: {e}")
        logger.info("Background refresh of preset cities completed.")
    except Exception as e:
        logger.error(f"Error reading cities config during refresh: {e}")

async def start_cache_scheduler(build_insight_fn, interval_seconds: int = 900):
    """
    Background loop refreshing preset cities every 15 minutes.
    """
    while True:
        await refresh_preset_cities(build_insight_fn)
        await asyncio.sleep(interval_seconds)
