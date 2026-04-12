from fastapi import APIRouter, HTTPException
import aiohttp
import os

from app.core.homeassistant import (
    LightControl,
    ClimateControl,
    CoverControl,
    FanControl
)

from app import schemas

router = APIRouter(prefix="/automation", tags=["Automation"])

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8001")


@router.post("/run")
async def run_automation(room: str):
    """
    Generic automation webhook:
    - Calls AI smart suggestions
    - Executes light / climate / cover actions automatically
    """

    try:
        # 1️⃣ Call AI service
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{AI_SERVICE_URL}/ai/smart-suggestions",
                params={"room": room}
            ) as resp:

                if resp.status != 200:
                    raise HTTPException(status_code=500, detail="AI service error")

                ai_data = await resp.json()

        suggestions = ai_data.get("suggestions", [])

        if not suggestions:
            return {"success": True, "message": "No suggestions returned."}

        results = []

        # 2️⃣ Execute suggestions
        for suggestion in suggestions:

            suggestion_type = suggestion.get("type")
            action = suggestion.get("action", {})

            entity_id = action.get("entity_id")

            if suggestion_type == "light":
                light_state = schemas.LightState(
                    entity_id=entity_id,
                    state="on"
                )
                result = await LightControl.turn_on_light(light_state)
                results.append({"type": "light", "entity": entity_id, "result": result.success})

            elif suggestion_type == "climate":
                temperature = action.get("temperature")
                result = await ClimateControl.control_climate(
                    entity_id=entity_id,
                    temperature=temperature
                )
                results.append({"type": "climate", "entity": entity_id, "result": result.success})

            elif suggestion_type == "cover":
                position = action.get("position")
                result = await CoverControl.set_cover_position(
                    cover_entity=entity_id,
                    position=int(position)
                )
                results.append({"type": "cover", "entity": entity_id, "result": result.success})

            elif suggestion_type == "fan":
                percentage = action.get("percentage")
                result = await FanControl.control_fan(
                    entity_id=entity_id,
                    state="on",
                    percentage=percentage,
                )
                results.append({
                    "type": "fan",
                    "entity": entity_id,
                    "result": result.success
                })

        return {
            "success": True,
            "executed_actions": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))