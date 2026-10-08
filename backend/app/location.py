import sqlite3
import logging
import asyncio
import time
import httpx
from typing import Dict, Any, Optional, Tuple
from app.config import DB_PATH

logger = logging.getLogger(__name__)

# Global rate-limiting lock and timestamp for Nominatim (1 req/sec)
_nominatim_lock = asyncio.Lock()
_last_nominatim_time = 0.0

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_location_tables():
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS location_cache (
            query_key TEXT PRIMARY KEY,
            name TEXT,
            lat REAL,
            lon REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_location_tables()

async def get_lat_lon_from_pin(pin: str) -> Dict[str, Any]:
    """
    Look up PIN code in local SQLite database.
    Fallback to Nominatim if not present locally.
    """
    pin = pin.strip()
    if not pin.isdigit() or len(pin) != 6 or pin[0] == "0":
        raise ValueError(f"Invalid 6-digit Indian PIN code format: '{pin}'")

    conn = _get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT pincode, place_name, district, state, latitude, longitude FROM pincodes WHERE pincode = ?", (pin,)).fetchone()
    conn.close()

    if row:
        name = f"{row['place_name']}, {row['district']}" if row['place_name'] else f"PIN {pin}"
        return {
            "name": name,
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "source": "local_db"
        }

    # Fallback to Nominatim for unknown PIN
    logger.info(f"PIN {pin} not found in local DB, querying Nominatim fallback...")
    res = await _geocode_nominatim(f"{pin}, India")
    if res:
        res["name"] = f"PIN {pin} ({res['name']})"
        return res

    raise ValueError(f"PIN code '{pin}' could not be resolved to geographical coordinates.")

async def get_lat_lon_from_place(place: str) -> Dict[str, Any]:
    """
    Geocode place name to lat/lon using Open-Meteo Geocoding API,
    with local SQLite cache and Nominatim fallback.
    """
    place_clean = place.strip()
    if not place_clean:
        raise ValueError("Place name cannot be empty.")

    # Check local cache first
    cache_key = f"place:{place_clean.lower()}"
    cached = _get_cached_location(cache_key)
    if cached:
        return cached

    # 1. Try Open-Meteo Geocoding API
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url, params={"name": place_clean, "count": 1, "language": "en"})
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results")
                if results and len(results) > 0:
                    r = results[0]
                    name_parts = [r.get("name")]
                    if r.get("admin1"):
                        name_parts.append(r["admin1"])
                    if r.get("country"):
                        name_parts.append(r["country"])
                    full_name = ", ".join(name_parts)
                    res = {
                        "name": full_name,
                        "lat": float(r["latitude"]),
                        "lon": float(r["longitude"]),
                        "source": "open_meteo"
                    }
                    _set_cached_location(cache_key, res)
                    return res
    except Exception as e:
        logger.warning(f"Open-Meteo geocoding failed for '{place_clean}': {e}")

    # 2. Fallback to Nominatim
    res = await _geocode_nominatim(place_clean)
    if res:
        _set_cached_location(cache_key, res)
        return res

    raise ValueError(f"Location place name '{place_clean}' not found.")

async def reverse_geocode(lat: float, lon: float) -> str:
    """
    Convert lat/lon coordinates to place name string.
    """
    cache_key = f"rev:{round(lat, 3)},{round(lon, 3)}"
    cached = _get_cached_location(cache_key)
    if cached:
        return cached["name"]

    # Try Open-Meteo or Nominatim
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            url = f"https://nominatim.openstreetmap.org/reverse"
            headers = {"User-Agent": "MazhAI-WeatherSystem/1.0 (hackathon@mazh.ai)"}
            async with _nominatim_lock:
                await _throttle_nominatim()
                resp = await client.get(url, params={"lat": lat, "lon": lon, "format": "json"}, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("address", {})
                city = address.get("city") or address.get("town") or address.get("village") or address.get("county") or address.get("state_district")
                state = address.get("state")
                parts = [p for p in [city, state] if p]
                if parts:
                    res_name = ", ".join(parts)
                    _set_cached_location(cache_key, {"name": res_name, "lat": lat, "lon": lon})
                    return res_name
    except Exception as e:
        logger.warning(f"Reverse geocode failed for {lat},{lon}: {e}")

    return f"Location ({round(lat, 2)}, {round(lon, 2)})"

async def _geocode_nominatim(query: str) -> Optional[Dict[str, Any]]:
    global _last_nominatim_time
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "MazhAI-WeatherSystem/1.0 (hackathon@mazh.ai)"}
    params = {"q": query, "format": "json", "limit": 1}

    try:
        async with _nominatim_lock:
            await _throttle_nominatim()
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        first = data[0]
                        return {
                            "name": first.get("display_name", query).split(",")[0],
                            "lat": float(first["lat"]),
                            "lon": float(first["lon"]),
                            "source": "nominatim"
                        }
    except Exception as e:
        logger.warning(f"Nominatim geocode failed for query '{query}': {e}")
    return None

async def _throttle_nominatim():
    global _last_nominatim_time
    now = time.time()
    elapsed = now - _last_nominatim_time
    if elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)
    _last_nominatim_time = time.time()

def _get_cached_location(key: str) -> Optional[Dict[str, Any]]:
    conn = _get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT name, lat, lon FROM location_cache WHERE query_key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return {"name": row["name"], "lat": row["lat"], "lon": row["lon"], "source": "cache"}
    return None

def _set_cached_location(key: str, loc: Dict[str, Any]):
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO location_cache (query_key, name, lat, lon)
        VALUES (?, ?, ?, ?)
    """, (key, loc["name"], loc["lat"], loc["lon"]))
    conn.commit()
    conn.close()
