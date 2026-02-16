import json
import re
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
        """
        Look up the best matching command in Qdrant and enrich it with
        parameters parsed from the raw user query (brightness %, fan level, AC mode, etc.).
        Before embedding, we normalize common name variants in the query
        (e.g. "recess", "recees") to their canonical forms so that they
        match how we phrase rooms in the generated commands.
        """

        # Map noisy/misspelled tokens in the *user query* to the same
        # canonical forms we use when generating commands for Qdrant.
        NAME_CASES = {
            "reece": "Reece's",
            "recees": "Reece's",
            "recess": "Reece's",
            "rece": "Reece's",
            'reces': "Reece's",
            "reece's": "Reece's",
            "jake": "Jake's",
            "jakes": "Jake's",
            "jake's": "Jake's",
        }

        def normalize_query(text: str) -> str:
            words = text.split()
            normalized_words: list[str] = []
            for w in words:
                # Strip punctuation for matching, keep original for fallback
                base = re.sub(r"[^a-zA-Z']+", "", w).lower()
                replacement = NAME_CASES.get(base)
                normalized_words.append(replacement if replacement else w)
            return " ".join(normalized_words)

        # Normalize the query first so "recess bedroom" lines up with
        # "Reece's Bedroom" style phrases in the vector DB.
        normalized_query = normalize_query(query)

        # 1) Parse structured parameters from the (normalized) natural language query
        parsed_params = VoiceAssistant._extract_parameters(normalized_query)

        # 2) Run semantic search in Qdrant to get intent/domain/entity_id/parameters
        qdrant = get_qdrant()
        embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        embedding = list(embedding_model.embed(normalized_query))[0]
        hits = await qdrant.query_points(
            collection_name=QDRANT_COLLECTION_NAME,
            query=embedding,
            limit=5,
        )
        print(hits)
        if not hits.points:
            return None

        payload = hits.points[0].payload or {}
        if not isinstance(payload, dict):
            return payload

        

    # ------------------------------------------------------------------
    # Parameter extraction from raw query text
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_parameters(query: str) -> dict:
        """
        Extract structured parameters from the spoken command, e.g.:
        - "set brightness to 80%" -> {"brightness": 80}
        - "set fan to low"        -> {"percentage": 25, "fan_mode": "low"}
        - "put ac on heat"        -> {"hvac_mode": "heat"}
        """
        text = query.lower().strip()
        params: dict[str, Any] = {}

        # --- Brightness ---
        # e.g. "set brightness to 80%" or "dim the lights to 30 percent"
        brightness_match = re.search(r"\b(\d{1,3})\s*(percent|%|percents)", text)
        if brightness_match:
            value = int(brightness_match.group(1))
            params["brightness"] = max(0, min(value, 100))
        elif "brightness" in text or "bright" in text or "dim" in text:
            # Handle "dim the lights" without a number -> pick a reasonable default dim level
            if "dim" in text:
                params["brightness"] = 40

        # --- Temperature for climate / AC ---
        # e.g. "set ac to 22 degrees", "set temperature to 24c"
        temp_match = re.search(r"\b(\d{1,2})\s*(degrees|degree|deg|c|celsius)\b", text)
        if temp_match:
            params["temperature"] = int(temp_match.group(1))

        # --- HVAC mode (climate) ---
        # e.g. "put ac on heat", "set ac to cooling", "set ac to auto"
        if "heat" in text or "heating" in text:
            params["hvac_mode"] = "heat"
        elif "cooling" in text or "cool" in text:
            params["hvac_mode"] = "cool"
        elif "auto" in text:
            params["hvac_mode"] = "heat_cool"

        # --- Fan speed / level ---
        # e.g. "set fan on low/medium/high", "put ac fan to high"
        FAN_LEVELS = {
            "low": 25,
            "medium": 60,
            "mid": 60,
            "high": 100,
            "max": 100,
            "maximum": 100,
        }
        for word, pct in FAN_LEVELS.items():
            if word in text and "fan" in text:
                # For fan domain: numeric percentage
                params["percentage"] = pct
                # For climate domain: fan_mode string
                params["fan_mode"] = word
                break

        return params

    # ------------------------------------------------------------------
    # Resolve entity_id from user query using controllable_devices + embeddings
    # ------------------------------------------------------------------
    @staticmethod
    async def _resolve_entity_from_query(text: str) -> str | None:
        """
        Best-effort resolution of an entity_id directly from the user query,
        using the same controllable_devices list that is cached in Redis and
        the embedding-based matcher from app.voice.device_matcher.

        Returns the best-matching entity_id, or None if nothing is clear.
        """
        try:
            redis = get_redis()
            raw = await redis.get("controllable_devices")
            if not raw:
                return None
            try:
                controllable_devices = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return None
            if not controllable_devices:
                return None

            # Ask the matcher for the single best candidate
            candidates = await match_entity(
                text,
                controllable_devices,
                device_hint=None,
                top_k=1,
            )
            return candidates[0] if candidates else None
        except Exception:
            # On any error, fail open and let plain Qdrant search handle it
            return None

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

        if domain == "generic":
            return {"success": True, "message": "Generic command executed", "response": response_text}
        return {"success": False, "message": f"Unknown domain: {domain}", "response": response_text}