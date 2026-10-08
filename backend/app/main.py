import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException, Request, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import CORS_ORIGINS, PORT, HOST
from app.schemas import (
    InsightSchema, PredictRequest, PredictResponse,
    ChatRequest, ChatResponse, SmsRequest, SmsResponse
)
from app.providers.open_meteo import OpenMeteoProvider
from app.location import get_lat_lon_from_place, get_lat_lon_from_pin, reverse_geocode
from app.climate_service import get_climate_state
from app.cache import get_cached_insight, set_cached_insight, start_cache_scheduler
from app.engine.insight import build_insight
from app.sms.twilio_adapter import SMSProvider, validate_phone_number
from app.llm.client import LLMClient
from app.ivr.twiml_handler import (
    load_cities_menu, build_twiml_response, build_twiml_say_and_hangup, generate_voice_script
)

# Structured Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mazh_backend")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Mazh AI Backend Application...")
    # Start background cache refresher for preset cities
    refresher_task = asyncio.create_task(start_cache_scheduler(get_or_build_insight, interval_seconds=900))
    yield
    refresher_task.cancel()

app = FastAPI(
    title="Mazh AI - Weather Intelligence System",
    description="Rainfall Risk Intelligence API (Hackathon Theme: Climate intelligence and weather analytics)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services
weather_provider = OpenMeteoProvider(timeout=2.0, max_retries=1)
sms_provider = SMSProvider()
llm_client = LLMClient(timeout=3.0)

# Simple Rate Limiting Middleware (Memory sliding window)
REQUEST_HISTORY: Dict[str, list] = {}
RATE_LIMIT_MAX = 60 # max requests per minute per IP

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    
    # Clean old timestamps
    if client_ip not in REQUEST_HISTORY:
        REQUEST_HISTORY[client_ip] = []
    REQUEST_HISTORY[client_ip] = [t for t in REQUEST_HISTORY[client_ip] if now - t < 60.0]
    
    if len(REQUEST_HISTORY[client_ip]) >= RATE_LIMIT_MAX:
        logger.warning(f"Rate limit exceeded for IP {client_ip}")
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "detail": "Too many requests. Please wait a minute."}
        )
    
    REQUEST_HISTORY[client_ip].append(now)
    response = await call_next(request)
    return response

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)}
    )

# Helper function to fetch or build insight
async def get_or_build_insight(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    place: Optional[str] = None,
    pin: Optional[str] = None,
    place_name_override: Optional[str] = None
) -> Dict[str, Any]:

    loc_info = None

    if pin:
        loc_info = await get_lat_lon_from_pin(pin)
    elif place:
        loc_info = await get_lat_lon_from_place(place)
    elif lat is not None and lon is not None:
        rev_name = place_name_override or await reverse_geocode(lat, lon)
        loc_info = {"name": rev_name, "lat": lat, "lon": lon}
    else:
        # Default to Chennai if no parameters provided
        loc_info = {"name": "Chennai, Tamil Nadu", "lat": 13.0827, "lon": 80.2707}

    target_lat = loc_info["lat"]
    target_lon = loc_info["lon"]

    # 1. Check cache layer (stale-while-revalidate)
    cached_insight, is_stale = get_cached_insight(target_lat, target_lon, ttl_seconds=900)
    if cached_insight and not is_stale:
        return cached_insight

    # 2. Fetch fresh weather & climate data
    try:
        raw_weather = await weather_provider.get_weather(target_lat, target_lon)
        climate = await get_climate_state()
        insight = build_insight(raw_weather, loc_info, climate, force_fallback=False)
        # Update cache
        set_cached_insight(target_lat, target_lon, insight)
        return insight
    except Exception as e:
        logger.error(f"Failed to fetch live weather data for ({target_lat}, {target_lon}): {e}")
        # If live fetch fails, serve stale cached insight if available!
        if cached_insight:
            logger.info("Serving stale cached insight due to weather provider error (Stale-While-Revalidate)")
            cached_insight["meta"]["fallback_used"] = True
            return cached_insight
        
        # Absolute fallback: construct minimal deterministic fallback insight
        logger.warning("No cached insight available. Generating fallback forecast insight.")
        dummy_weather = {
            "current": {"temp_c": 28.0, "feels_like_c": 30.0, "humidity": 75, "pressure_hpa": 1012.0, "wind_kph": 12.0, "wind_dir": "NE", "condition": "Partly cloudy"},
            "hourly": [{"time": datetime.now(timezone.utc).isoformat(), "temp_c": 28.0, "rain_prob": 20, "rain_mm": 0.0}],
            "daily": [{"date": str(datetime.now(timezone.utc).date()), "min_c": 24.0, "max_c": 32.0, "rain_prob": 20, "rain_mm": 0.0}]
        }
        climate = {"enso_state": "el_nino", "nino34_anom": 1.2}
        fallback_insight = build_insight(dummy_weather, loc_info, climate, force_fallback=True)
        return fallback_insight

# API Endpoints
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": "1.0.0"
    }

@app.get("/weather", response_model=InsightSchema)
async def get_weather(
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude"),
    place: Optional[str] = Query(None, description="Place name e.g. Chennai"),
    pin: Optional[str] = Query(None, description="6-digit PIN code e.g. 600001")
):
    try:
        insight = await get_or_build_insight(lat=lat, lon=lon, place=place, pin=pin)
        return insight
    except ValueError as ve:
        raise HTTPException(status_code=400, detail={"error": "Invalid location parameter", "detail": str(ve)})

@app.post("/predict", response_model=PredictResponse)
async def predict_risk(req: PredictRequest):
    insight = await get_or_build_insight(lat=req.lat, lon=req.lon)
    heavy_rain_risk = next((r for r in insight["risks"] if r["type"] == "heavy_rain"), insight["risks"][0])
    
    return PredictResponse(
        score=heavy_rain_risk["score"],
        level=heavy_rain_risk["level"],
        reasons=heavy_rain_risk["reasons"],
        risks=insight["risks"]
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # 1. Parse intent and language
    parsed = await llm_client.parse_intent(req.message)
    intent = parsed["intent"]
    lang = req.lang or parsed["language"]
    
    # Determine location target
    loc_query = req.pin or req.place or parsed.get("location")
    insight = await get_or_build_insight(
        lat=req.lat,
        lon=req.lon,
        place=loc_query if loc_query and not loc_query.isdigit() else None,
        pin=loc_query if loc_query and loc_query.isdigit() else None
    )

    # 2. Phrase reply using LLM (with strict number validation and fallback)
    reply = await llm_client.generate_reply(
        user_message=req.message,
        intent=intent,
        insight=insight,
        lang=lang,
        session_id=req.session_id
    )

    return ChatResponse(
        reply=reply,
        intent=intent,
        insight=insight
    )

@app.post("/sms", response_model=SmsResponse)
async def send_sms_endpoint(req: SmsRequest):
    try:
        validate_phone_number(req.phone)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail={"error": "Invalid phone number", "detail": str(ve)})

    insight = await get_or_build_insight(
        lat=req.lat, lon=req.lon, place=req.place, pin=req.pin
    )
    sms_text = insight["insight"]["sms_text"]
    
    res = await sms_provider.send_sms(to_phone=req.phone, message_text=sms_text)
    return SmsResponse(status=res["status"], detail=res.get("detail"))

# Twilio Keypad IVR Webhooks
@app.post("/voice/welcome")
async def voice_welcome():
    prompt = "Welcome to Mazh AI Rainfall Intelligence. Press 1 for English. தமிழ் தகவலுக்கு 2 ஐ அழுத்தவும்."
    twiml = build_twiml_response(prompt_text=prompt, gather_action="/voice/language", num_digits=1)
    return Response(content=twiml, media_type="application/xml")

@app.post("/voice/language")
async def voice_language(Digits: Optional[str] = Form(None)):
    lang = "ta" if Digits == "2" else "en"
    cities = load_cities_menu()
    
    if lang == "ta":
        options = " ".join([f"{c['name_ta']} தகவலுக்கு {c['digit']} அழுத்தவும்." for c in cities])
        prompt = f"நகரத்தை தேர்ந்தெடுக்கவும்: {options} PIN குறியீடு உள்ளிட 5 ஐ அழுத்தவும்."
    else:
        options = " ".join([f"Press {c['digit']} for {c['name']}." for c in cities])
        prompt = f"Please choose your city: {options} Or Press 5 to enter a 6-digit Pincode."

    twiml = build_twiml_response(prompt_text=prompt, gather_action=f"/voice/menu?lang={lang}", num_digits=1)
    return Response(content=twiml, media_type="application/xml")

@app.post("/voice/menu")
async def voice_menu(Digits: Optional[str] = Form(None), lang: str = Query("en")):
    cities = load_cities_menu()
    
    if Digits == "5":
        prompt = "தயவுசெய்து உங்கள் 6 இலக்க PIN குறியீட்டை உள்ளிடவும்." if lang == "ta" else "Please enter your 6-digit PIN code followed by hash."
        twiml = build_twiml_response(prompt_text=prompt, gather_action=f"/voice/pincode-submit?lang={lang}", num_digits=6)
        return Response(content=twiml, media_type="application/xml")
    
    matched_city = next((c for c in cities if c["digit"] == Digits), cities[0])
    insight = await get_or_build_insight(lat=matched_city["lat"], lon=matched_city["lon"], place_name_override=matched_city["name"])
    
    script = generate_voice_script(insight, lang=lang)
    twiml = build_twiml_say_and_hangup(script)
    return Response(content=twiml, media_type="application/xml")

@app.post("/voice/pincode-submit")
async def voice_pincode_submit(Digits: Optional[str] = Form(None), lang: str = Query("en")):
    pin = Digits or "600001"
    try:
        insight = await get_or_build_insight(pin=pin)
    except Exception:
        insight = await get_or_build_insight(place="Chennai")
    
    script = generate_voice_script(insight, lang=lang)
    twiml = build_twiml_say_and_hangup(script)
    return Response(content=twiml, media_type="application/xml")
