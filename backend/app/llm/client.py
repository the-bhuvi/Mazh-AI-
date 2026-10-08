import os
import re
import json
import logging
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from app.config import LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, BASE_DIR

logger = logging.getLogger(__name__)

# Prompts directory
PROMPTS_DIR = BASE_DIR / "backend" / "app" / "prompts"

# In-memory session history storage
SESSION_HISTORY: Dict[str, List[Dict[str, str]]] = {}

def load_prompt(filename: str) -> str:
    filepath = PROMPTS_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    logger.warning(f"Prompt file {filename} not found at {filepath}")
    return ""

def extract_numbers(text_or_obj: Any) -> set:
    """Extract all numerical strings / floats / ints from string or nested dict/list."""
    numbers = set()
    s_text = json.dumps(text_or_obj) if isinstance(text_or_obj, (dict, list)) else str(text_or_obj)
    # Find digits and floating point numbers
    matches = re.findall(r"\b\d+(?:\.\d+)?\b", s_text)
    for m in matches:
        numbers.add(m)
        try:
            # Also add int representation if float (e.g. 13.0 -> 13)
            val = float(m)
            if val.is_integer():
                numbers.add(str(int(val)))
        except ValueError:
            pass
    return numbers

def validate_numbers_in_reply(reply: str, insight: Dict[str, Any]) -> bool:
    """
    Validates that the reply contains NO numbers that are absent from the insight JSON.
    Returns True if valid, False if hallucinated number detected.
    """
    allowed_numbers = extract_numbers(insight)
    # Common conversational numbers to allow (e.g., 24 for 24h, 1 or 2 for count)
    allowed_numbers.update({"1", "2", "3", "4", "5", "6", "7", "24", "48"})

    reply_numbers = extract_numbers(reply)
    for num in reply_numbers:
        if num not in allowed_numbers:
            logger.warning(f"Validation rejection: reply contains ungrounded number '{num}' not in insight JSON.")
            return False
    return True

class LLMClient:
    def __init__(self, timeout: float = 3.0):
        self.base_url = LLM_BASE_URL.rstrip("/")
        self.model = LLM_MODEL
        self.api_key = LLM_API_KEY
        self.timeout = timeout

    async def parse_intent(self, user_message: str) -> Dict[str, Any]:
        """
        Parses intent and location from user message using LLM or rule fallback.
        """
        # Rule-based pattern matching fallback
        msg_lower = user_message.lower()
        rule_intent = "CHECK_RAINFALL_RISK"
        if "cloth" in msg_lower or "dry" in msg_lower or "wash" in msg_lower or "துணி" in msg_lower:
            rule_intent = "CLOTHES_DRYING"
        elif "crop" in msg_lower or "farm" in msg_lower or "irrigat" in msg_lower or "விவசாயம்" in msg_lower:
            rule_intent = "FARMING_ADVICE"
        elif "nino" in msg_lower or "climate" in msg_lower:
            rule_intent = "EL_NINO_INFO"
        elif "rain" in msg_lower or "mazhai" in msg_lower or "weather" in msg_lower or "shower" in msg_lower or "storm" in msg_lower:
            rule_intent = "CHECK_RAINFALL_RISK"
        elif "hello" in msg_lower or "hi " in msg_lower or "help" in msg_lower or "how does" in msg_lower:
            rule_intent = "GENERAL_HELP"

        lang = "ta" if any(ord(c) > 2900 for c in user_message) or "tanglish" in msg_lower or "mazhai" in msg_lower else "en"

        # Simple rule-based location extraction fallback
        rule_loc = None
        pin_match = re.search(r"\b\d{6}\b", user_message)
        if pin_match:
            rule_loc = pin_match.group(0)
        else:
            for city in ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Trichy", "Salem", "Vellore"]:
                if city.lower() in msg_lower:
                    rule_loc = city
                    break

        if not self.api_key:
            return {"intent": rule_intent, "location": rule_loc, "language": lang}

        system_prompt = load_prompt("intent_system.txt")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        try:
            res_text = await self._call_llm_api(messages)
            if res_text:
                # Find JSON payload
                json_match = re.search(r"\{.*\}", res_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    return {
                        "intent": parsed.get("intent", rule_intent),
                        "location": parsed.get("location"),
                        "language": parsed.get("language", lang)
                    }
        except Exception as e:
            logger.warning(f"LLM intent parsing failed, using rule fallback: {e}")

        return {"intent": rule_intent, "location": rule_loc, "language": lang}

    async def generate_reply(
        self,
        user_message: str,
        intent: str,
        insight: Dict[str, Any],
        lang: str = "en",
        session_id: Optional[str] = None
    ) -> str:
        """
        Phrases reply using LLM (if key available and passes strict number validation),
        or falls back to deterministic template reply.
        """
        # Save to session history
        if session_id:
            if session_id not in SESSION_HISTORY:
                SESSION_HISTORY[session_id] = []
            SESSION_HISTORY[session_id].append({"user": user_message})

        fallback_reply = self._build_template_reply(intent, insight, lang)

        if not self.api_key:
            return fallback_reply

        prompt_file = "reply_ta.txt" if lang == "ta" else "reply_en.txt"
        template = load_prompt(prompt_file)
        if not template:
            return fallback_reply

        prompt_content = template.format(
            insight_json=json.dumps(insight, indent=2),
            intent=intent,
            user_message=user_message
        )

        messages = [
            {"role": "user", "content": prompt_content}
        ]

        try:
            llm_text = await self._call_llm_api(messages)
            if llm_text:
                clean_reply = llm_text.strip()
                # Strict verification: verify reply invents NO ungrounded numbers
                if validate_numbers_in_reply(clean_reply, insight):
                    if session_id:
                        SESSION_HISTORY[session_id].append({"bot": clean_reply})
                    return clean_reply
                else:
                    logger.warning("LLM output failed number grounding check! Falling back to template reply.")
        except Exception as e:
            logger.warning(f"LLM generation timed out/failed: {e}")

        if session_id:
            SESSION_HISTORY[session_id].append({"bot": fallback_reply})
        return fallback_reply

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Check if Ollama endpoint (/api/chat) or OpenAI/Gemini compatible (/v1/chat/completions)
        if "/api/chat" in self.base_url:
            url = self.base_url
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False
            }
        else:
            url = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2
            }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            elif "message" in data: # Ollama format
                return data["message"]["content"]
        return None

    def _build_template_reply(self, intent: str, insight: Dict[str, Any], lang: str) -> str:
        loc_name = insight["location"]["name"]
        summary = insight["insight"]["summary"]
        recs = insight["insight"]["recommendations"]
        current = insight["current"]

        if intent == "CLOTHES_DRYING":
            rain_risk = next((r for r in insight["risks"] if r["type"] == "heavy_rain"), {})
            level = rain_risk.get("level", "low")
            if level in ["high", "moderate"]:
                return f"In {loc_name}, {summary} It is best to dry your clothes indoors or bring them in before evening."
            return f"In {loc_name}, clothes can safely dry outdoors today. Current temperature is {current['temp_c']}°C."

        elif intent == "FARMING_ADVICE":
            rain_mm = sum(h["rain_mm"] for h in insight["hourly"][:24])
            if rain_mm > 15.0:
                return f"Heavy rain ({round(rain_mm, 1)} mm) is expected in {loc_name}. Pause field irrigation and ensure drainage paths are clear."
            return f"In {loc_name}, light/moderate rain of {round(rain_mm, 1)} mm is expected. Standard field operations can continue safely."

        elif intent == "EL_NINO_INFO":
            enso = insight["meta"]["climate"]["enso_state"]
            anom = insight["meta"]["climate"]["nino34_anom"]
            return f"El Niño status: {enso.upper()} (NINO3.4 anomaly: +{anom}°C). In South India, active El Niño typically enhances North-East monsoon rain."

        # Default fallback
        rec_str = f" Recommendation: {recs[0]}" if recs else ""
        return f"{summary}{rec_str}"
