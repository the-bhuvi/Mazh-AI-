import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from app.config import CITIES_FILE

logger = logging.getLogger(__name__)

def load_cities_menu() -> list:
    if CITIES_FILE.exists():
        with open(CITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return [
        {"digit": "1", "id": "chennai", "name": "Chennai", "name_ta": "சென்னை", "lat": 13.0827, "lon": 80.2707, "pincode": "600001"},
        {"digit": "2", "id": "coimbatore", "name": "Coimbatore", "name_ta": "கோயம்புத்தூர்", "lat": 11.0168, "lon": 76.9558, "pincode": "641001"},
        {"digit": "3", "id": "madurai", "name": "Madurai", "name_ta": "மதுரை", "lat": 9.9252, "lon": 78.1198, "pincode": "625001"},
        {"digit": "4", "id": "tiruchirappalli", "name": "Tiruchirappalli", "name_ta": "திருச்சிராப்பள்ளி", "lat": 10.7905, "lon": 78.7047, "pincode": "620001"}
    ]

def build_twiml_response(prompt_text: str, gather_action: str, num_digits: int = 1) -> str:
    """Helper to generate TwiML XML string for Twilio voice calls."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather action="{gather_action}" method="POST" numDigits="{num_digits}">
        <Say voice="Polly.Aditi" language="en-IN">{prompt_text}</Say>
    </Gather>
    <Say voice="Polly.Aditi" language="en-IN">We did not receive any key press. Goodbye!</Say>
</Response>"""

def build_twiml_say_and_hangup(message_text: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="en-IN">{message_text}</Say>
    <Hangup/>
</Response>"""

def generate_voice_script(insight: Dict[str, Any], lang: str = "en") -> str:
    """
    Fixed phrase templates filled strictly with engine output (NO LLM, NO SPEECH RECOGNITION).
    """
    loc_name = insight["location"]["name"]
    summary = insight["insight"]["summary"]
    rain_risk = next((r for r in insight["risks"] if r["type"] == "heavy_rain"), {})
    level = rain_risk.get("level", "low")
    score_pct = int(rain_risk.get("score", 0.0) * 100)
    current = insight["current"]

    if lang == "ta":
        script = f"வணக்கம்! {loc_name} பகுதியில் மழை அபாயம் {level.upper()} நிலையில் உள்ளது. அபாய சதவீதம் {score_pct} விழுக்காடு. தற்போதைய வெப்பநிலை {current['temp_c']} டிகிரி செல்சியஸ். {summary} பாதுகாப்பாக இருக்கவும்."
    else:
        script = f"Welcome to Mazh AI. In {loc_name}, the rainfall risk is {level.upper()}, with a risk score of {score_pct} percent. Current temperature is {current['temp_c']} degrees Celsius. {summary} Stay safe!"

    return script
