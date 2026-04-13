import json
import re
from typing import Any
from app.core.homeassistant import (
    LightControl,
    CoverControl,
    ClimateControl,
    FanControl,
)
from app import schemas
from app.voiceassistant.intentparser import parse_command
from app.core.redis_init import get_redis
from app.voiceassistant.llm import query_llm

class VoiceAssistant:
    """
    output_json shape: {
        "intent": "turn_on" | "turn_off" | "open" | "close" | "set_position" | "set_temperature" | ...
        "domain": "light" | "cover" | "climate" | "fan",
        "entity_id": "light.kitchen" | "climate.reece_bedroom_fan" | ...,
        "parameters": {} | {"brightness": 80} | {"position": 50} | {"temperature": 22} | ...,
        "response": "Turn on the ac in reece_bedroom_fan."
    }
    """


    @staticmethod
    def _normalize_brightness(brightness: Any) -> int | None:
        """Convert brightness like '80%' into Home Assistant's 0-255 scale."""
        if brightness is None:
            return None

        if isinstance(brightness, str):
            value = brightness.strip()
            if value.endswith("%"):
                percent_str = value[:-1].strip()
                try:
                    percent = float(percent_str)
                except ValueError:
                    return None
                percent = max(0.0, min(100.0, percent))
                return round((percent / 100.0) * 255)
            try:
                numeric = float(value)
            except ValueError:
                return None
            return max(0, min(255, round(numeric)))

        if isinstance(brightness, (int, float)):
            percent = max(0.0, min(100.0, float(brightness)))
            return round((percent / 100.0) * 255)

        return None


    @staticmethod
    async def search_commands(query: str) -> dict | None:
        redis = await get_redis()
        controllable_devices = await redis.get("controllable_devices")
        if not controllable_devices:
            return None
        controllable_devices = json.loads(controllable_devices)
        command = parse_command(query, controllable_devices)
        return command
        

    @staticmethod
    async def execute_command(command: dict) -> dict[str, Any]:
        """
        Execute a single command from output_json. Dispatches to the right
        Home Assistant control (light, cover, climate, fan).

        Accepts either:
        - {"output_json": {"intent": "turn_on", "domain": "climate", "entity_id": "...", ...}}
        - or the output_json dict directly: {"intent": "turn_on", "domain": "climate", ...}
        """
        if "output_json" in command:
            command = command["output_json"]
        intent = (command.get("intent") or "").strip().lower()
        domain = (command.get("domain") or "").strip().lower()
        entity_id = command.get("entity_id") or ""
        parameters = command.get("parameters") or {}
        response_text = command.get("response") or ""

        if not entity_id:
            return {"success": False, "message": "Missing entity_id", "response": response_text}

        # --- Light ---
        if domain == "light":
            if intent in ("turn_on", "on"):
                light_state = schemas.LightState(
                    entity_id=entity_id,
                    state="on",
                    brightness=VoiceAssistant._normalize_brightness(parameters.get("brightness")),
                    color_name=parameters.get("color_name"),
                    rgb_color=parameters.get("rgb_color"),
                    color_temp_kelvin=parameters.get("color_temp_kelvin"),
                )
                result = await LightControl.turn_on_light(light_state)
            elif intent in ("turn_off", "off"):
                light_state = schemas.LightState(entity_id=entity_id, state="off")
                result = await LightControl.turn_off_light(light_state)
            else:
                return {"success": False, "message": f"Unknown light intent: {intent}", "response": response_text}
            return {"success": result.success, "message": result.message, "response": response_text}

        # --- Cover ---
        if domain == "cover":
            if intent in ("open", "turn_on", "on"):
                result = await CoverControl.open_cover(entity_id)
            elif intent in ("close", "turn_off", "off"):
                result = await CoverControl.close_cover(entity_id)
            elif intent == "set_position" and "position" in parameters:
                result = await CoverControl.set_cover_position(entity_id, int(parameters["position"]))
            else:
                return {"success": False, "message": f"Unknown cover intent: {intent}", "response": response_text}
            return {"success": result.success, "message": result.message, "response": response_text}

        # --- Climate ---
        if domain == "climate":
            result = await ClimateControl.control_climate(
                entity_id=entity_id,
                state="on" if intent in ("turn_on", "on") else "off" if intent in ("turn_off", "off") else None,
                hvac_mode=parameters.get("hvac_mode"),
                temperature=parameters.get("temperature"),
                fan_mode=parameters.get("fan_mode"),
                swing_mode=parameters.get("swing_mode"),
                swing_horizontal_mode=parameters.get("swing_horizontal_mode"),
            )
            return {"success": result.success, "message": result.message, "response": response_text}

        # --- Fan ---
        if domain == "fan":
            result = await FanControl.control_fan(
                entity_id=entity_id,
                state="on" if intent in ("turn_on", "on") else "off" if intent in ("turn_off", "off") else None,
                percentage=parameters.get("percentage"),
                oscillating=parameters.get("oscillating"),
                direction=parameters.get("direction"),
            )
            return {"success": result.success, "message": result.message, "response": response_text}

        if domain == "generic":
            return {"success": True, "message": "Generic command executed", "response": response_text}
        return {"success": False, "message": f"Unknown domain: {domain}", "response": response_text}