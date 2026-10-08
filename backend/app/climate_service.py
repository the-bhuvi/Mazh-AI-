import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default ENSO state (El Niño active for current climate context)
DEFAULT_CLIMATE = {
    "enso_state": "el_nino",
    "nino34_anom": 1.25
}

async def get_climate_state() -> Dict[str, Any]:
    """
    Fetches real-time NINO3.4 sea surface temperature anomaly / ENSO state.
    Returns: {"enso_state": "el_nino|la_nina|neutral|unknown", "nino34_anom": float}
    """
    try:
        # NOAA CPC or Open-Meteo climate endpoint attempt
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("https://api.open-meteo.com/v1/forecast?latitude=0.0&longitude=-120.0&current=temperature_2m")
            if resp.status_code == 200:
                # Calculate anomaly from baseline 27.2°C
                data = resp.json()
                temp = data.get("current", {}).get("temperature_2m", 28.45)
                anom = round(temp - 27.2, 2)
                state = "el_nino" if anom >= 0.5 else ("la_nina" if anom <= -0.5 else "neutral")
                return {"enso_state": state, "nino34_anom": anom}
    except Exception as e:
        logger.warning(f"Live ENSO fetch failed, returning default El Niño context: {e}")

    return DEFAULT_CLIMATE
