# app/routes/voice.py

from fastapi import APIRouter, Query, Depends
from app.voice.handler import parse_intent
from app.voice.hass import send_light_command
from app import models, auth

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])

@router.get("/command")
async def voice_command(text: str = Query(..., description="Command text from user"), current_user: models.User = Depends(auth.get_current_active_user)):
    """
    Accepts a voice command as text, parses intent, and executes action via Home Assistant.
    Example: /voice/command?text=turn on the guest room light
    """
    intent_data = parse_intent(text)

    if intent_data["intent"] == "unknown":
        return {
            "success": False,
            "message": "Sorry, I didn't understand the command."
        }

    # Only handle light commands for now
    if intent_data["intent"].startswith("turn_"):
        success = send_light_command(
            intent_data["intent"],
            intent_data.get("location", "")
        )
        return {
            "success": success,
            "message": f"{intent_data.get('location', '').replace('_', ' ').title()} light {'turned on' if 'on' in intent_data['intent'] else 'turned off'}" if success else "Failed to control the device."
        }

    # Handle other intents here (e.g. temperature)
    return {
        "success": False,
        "message": "That intent is not supported yet."
    }