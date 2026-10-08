import re
import logging
import httpx
from typing import Dict, Any, Optional
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER

logger = logging.getLogger(__name__)

# E.164 phone number validation regex pattern
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{1,14}$")

def validate_phone_number(phone: str) -> str:
    cleaned = re.sub(r"[\s\-\(\)]", "", phone.strip())
    if not cleaned.startswith("+") and len(cleaned) == 10 and cleaned.isdigit():
        cleaned = "+91" + cleaned # Default to India country code if 10 digits
    if not PHONE_REGEX.match(cleaned):
        raise ValueError(f"Invalid phone number format: '{phone}'")
    return cleaned

class SMSProvider:
    def __init__(self):
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.from_phone = TWILIO_PHONE_NUMBER

    async def send_sms(self, to_phone: str, message_text: str) -> Dict[str, Any]:
        """
        Sends SMS using Twilio REST API if configured, otherwise returns simulated success response.
        Note: The phone number is processed strictly transiently and NEVER persisted or logged.
        """
        valid_phone = validate_phone_number(to_phone)

        if self.account_sid and self.auth_token and self.from_phone:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            data = {
                "To": valid_phone,
                "From": self.from_phone,
                "Body": message_text
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(url, data=data, auth=(self.account_sid, self.auth_token))
                    resp.raise_for_status()
                    res_json = resp.json()
                    return {"status": "sent", "sid": res_json.get("sid")}
            except Exception as e:
                logger.error(f"Twilio SMS delivery failed: {e}")
                return {"status": "failed", "detail": str(e)}

        # Fallback simulation when Twilio env vars are not set
        logger.info(f"[SMS SIMULATION] Message sent to recipient ending in ***{valid_phone[-4:]}: '{message_text[:40]}...'")
        return {"status": "simulated", "detail": "Twilio credentials omitted. SMS simulated successfully."}
