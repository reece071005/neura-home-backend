# app/voice/handler.py

import json
import re
from typing import Optional

from pydantic import BaseModel, ValidationError

from app.core.redis_init import get_redis
from app.voice.device_matcher import match_entity
from app.voice.llm_client import fetch_intent_from_llm


class LLMIntentResponse(BaseModel):
    intent: str
    device: Optional[str] = None
    location: Optional[str] = None
    brightness: Optional[int] = None
    response: Optional[str] = None


class IntentParser:
    DEFAULT_DIM_BRIGHTNESS = 40

    def __init__(self, text: str):
        self.text = text.lower().strip()

    async def parse(self) -> dict:
        """
        1. Try rule-based parsing (fast & cheap)
        2. If not matched, fallback to LLM
        3. Match user phrase to a specific entity_id from controllable_devices using embeddings
        """

        result_dict = {
            "intent": "unknown",
            "device": None,
            "location": None,
            "brightness": None,
            "response": "Sorry, I didn't understand that.",
        }
        rule_result = self._parse_rule_based()
        if rule_result:
            result_dict.update(rule_result)

        result_dict = await self._add_entity_match(result_dict)

        result_dict = await self._call_llm(result_dict)
        return result_dict

    async def _add_entity_match(self, intent_result: dict) -> dict:
        """Resolve entity_id and top candidates from controllable_devices using embedding match."""
        controllable = await self._get_controllable_devices()
        if controllable:
            candidates = await match_entity(
                self.text,
                controllable,
                device_hint=intent_result.get("device"),
            )
            intent_result["entity_id"] = candidates[0] if candidates else None
            intent_result["entity_id_candidates"] = candidates  # top 5 (or fewer)
        else:
            intent_result["entity_id"] = None
            intent_result["entity_id_candidates"] = []
        return intent_result

    async def _get_controllable_devices(self) -> list[str]:
        """Load list of entity_ids from Redis (populated by cache_management)."""
        try:
            redis = get_redis()
            raw = await redis.get("controllable_devices")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return []

    #  rule-based parsing
    def _parse_rule_based(self) -> Optional[dict]:

        LIGHT_KEYWORDS = ["light", "lights", "lamp", "bulb"]
        FAN_KEYWORDS = ["fan", "fans"]
        BLIND_KEYWORDS = ["blind", "blinds", "cover"]
        AC_KEYWORDS = ["ac", "air conditioner", "climate"]

        ON_KEYWORDS = ["turn on", "switch on"]
        OFF_KEYWORDS = ["turn off", "switch off"]
        DIM_KEYWORDS = ["dim", "brightness"]
        result_dict = {
            "intent": "unknown",
            "device": None,
            "location": None,
            "brightness": None,
            "response": None,
        }


        # Turn ON
        if any(keyword in self.text for keyword in ON_KEYWORDS):
            result_dict["intent"] = "turn_on"
            return result_dict
        # Turn OFF
        if any(keyword in self.text for keyword in OFF_KEYWORDS):
            result_dict["intent"] = "turn_off"
            return result_dict

        # Brightness
        if any(keyword in self.text for keyword in DIM_KEYWORDS):
            brightness = self._extract_brightness()
            result_dict["intent"] = "set_brightness"
            result_dict["brightness"] = brightness
            return result_dict


        # Light
        if any(keyword in self.text for keyword in LIGHT_KEYWORDS):
            result_dict["device"] = "light"
            return result_dict

        # Fan
        if any(keyword in self.text for keyword in FAN_KEYWORDS):
            result_dict["device"] = "fan"
            return result_dict

        # Blind
        if any(keyword in self.text for keyword in BLIND_KEYWORDS):
            result_dict["device"] = "cover"
            return result_dict

        # AC
        if any(keyword in self.text for keyword in AC_KEYWORDS):
            result_dict["device"] = "climate"
            return result_dict

        return result_dict

    # helpers
    def _extract_location(self) -> str:
        pass


    def _extract_brightness(self) -> int:
        match = re.search(r"\b(\d{1,3})\s*(percent|%)", self.text)
        if match:
            value = int(match.group(1))
            return max(0, min(value, 100))

        if "dim" in self.text:
            return self.DEFAULT_DIM_BRIGHTNESS

        return 100

    # LLM fallback (async + validated)
    async def _call_llm(self, intent_result: dict) -> dict:
        llm_result = await fetch_intent_from_llm(self.text, intent_result)
        if llm_result:
            return llm_result
        return None

