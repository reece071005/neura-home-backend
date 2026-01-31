# app/voice/handler.py

import re
import json
import aiohttp
from typing import Optional
from pydantic import BaseModel, ValidationError

class LLMIntentResponse(BaseModel):
    intent: str
    device: Optional[str] = None
    location: Optional[str] = None
    brightness: Optional[int] = None
    response: Optional[str] = None


class IntentParser:
    LLM_ENDPOINT = "http://localhost:8080/completion"

    known_locations = [
        "kitchen",
        "bedroom",
        "living room",
        "guest room",
        "hallway",
    ]

    DEFAULT_DIM_BRIGHTNESS = 40

    def __init__(self, text: str):
        self.text = text.lower().strip()

    #public entry point
    async def parse(self) -> dict:
        """
        1. Try rule-based parsing (fast & cheap)
        2. If not matched, fallback to LLM
        """
        rule_result = self._parse_rule_based()
        if rule_result:
            return rule_result

        llm_result = await self._call_llm()
        if llm_result:
            return llm_result.model_dump()

        return {
            "intent": "unknown",
            "device": None,
            "location": None,
            "brightness": None,
            "response": "Sorry, I didn't understand that.",
        }

    #  rule-based parsing
    def _parse_rule_based(self) -> Optional[dict]:
        location = self._extract_location()

        # Turn ON
        if "turn on" in self.text or "switch on" in self.text:
            return {
                "intent": "turn_on_light",
                "device": "light",
                "location": location,
                "brightness": None,
                "response": f"Turning on the {location} light.",
            }

        # Turn OFF
        if "turn off" in self.text or "switch off" in self.text:
            return {
                "intent": "turn_off_light",
                "device": "light",
                "location": location,
                "brightness": None,
                "response": f"Turning off the {location} light.",
            }

        # Brightness
        if "dim" in self.text or "brightness" in self.text:
            brightness = self._extract_brightness()
            return {
                "intent": "set_brightness",
                "device": "light",
                "location": location,
                "brightness": brightness,
                "response": f"Setting brightness of {location} light to {brightness}%.",
            }

        return None

    # helpers
    def _extract_location(self) -> str:
        for loc in self.known_locations:
            if loc in self.text:
                return loc
        return "current"

    def _extract_brightness(self) -> int:
        match = re.search(r"\b(\d{1,3})\s*(percent|%)", self.text)
        if match:
            value = int(match.group(1))
            return max(0, min(value, 100))

        if "dim" in self.text:
            return self.DEFAULT_DIM_BRIGHTNESS

        return 100

    # LLM fallback (async + validated)
    async def _call_llm(self) -> Optional[LLMIntentResponse]:
        payload = {
            "prompt": self.text,
            "n_predict": 256,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.LLM_ENDPOINT, json=payload) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    content = data.get("content", "")

                    # LLM MUST return JSON
                    try:
                        parsed_json = json.loads(content)
                        return LLMIntentResponse(**parsed_json)
                    except (json.JSONDecodeError, ValidationError) as e:
                        print("LLM output invalid:", e)
                        return None

        except Exception as e:
            print("LLM request failed:", e)
            return None
