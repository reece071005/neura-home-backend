import json
from typing import Any

from fastembed import TextEmbedding

from app.config import QDRANT_COLLECTION_NAME
from app.core.qdrant_init import get_qdrant
from app.core.homeassistant import (
    LightControl,
    CoverControl,
    ClimateControl,
    FanControl,
)
from app import schemas


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
    async def search_commands(query: str) -> dict | None:
        qdrant = get_qdrant()
        embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        embedding = list(embedding_model.embed(query))[0]
        hits = await qdrant.query_points(
            collection_name=QDRANT_COLLECTION_NAME,
            query=embedding,
            limit=1,
        )
        if not hits.points:
            return None
        return hits.points[0].payload

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
                    brightness=parameters.get("brightness"),
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

        return {"success": False, "message": f"Unknown domain: {domain}", "response": response_text}