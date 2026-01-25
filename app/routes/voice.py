# app/routes/voice.py

from fastapi import APIRouter, Query, Depends
from app.voice.handler import IntentParser
from app.core.homeassistant import turn_on_light, turn_off_light
from app import models, auth, schemas

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])


@router.get("/command")
async def voice_command(
    text: str = Query(..., description="Command text from user"),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Accepts a voice command as text, parses intent, and executes action via Home Assistant.
    Example: /voice/command?text=turn on the guest room light
    """
    intent_data = IntentParser(text).parse()

    if intent_data["intent"] == "unknown":
        return {
            "success": False,
            "message": "Sorry, I didn't understand the command."
        }

    entity_id = f"light.{intent_data.get('location', '').replace(' ', '_')}"
    brightness = intent_data.get("brightness")

    light_state = schemas.LightState(entity_id=entity_id, brightness=brightness)

    if intent_data["intent"] == "turn_on_light":
        result = await turn_on_light(light_state)
    elif intent_data["intent"] == "turn_off_light":
        result = await turn_off_light(light_state)
    else:
        return {"success": False, "message": "Intent not supported yet."}

    return {"success": result.success, "message": result.message}
