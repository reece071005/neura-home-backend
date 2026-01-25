import aiohttp
from app.config import HOME_ASSISTANT_URL, HEADERS
from app import schemas

async def turn_on_light(light_state: schemas.LightState):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{HOME_ASSISTANT_URL}/services/light/turn_on", headers=HEADERS, json={"entity_id": light_state.entity_id, "brightness": light_state.brightness}) as response:
                if response.status == 200:
                    return schemas.LightStateResponse(message="Light turned on", success=True)
                else:
                    return schemas.LightStateResponse(message="Failed to turn on light", success=False)
    except Exception as e:
        return schemas.LightStateResponse(message=str(e), success=False)

async def turn_off_light(light_state: schemas.LightState):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{HOME_ASSISTANT_URL}/services/light/turn_off", headers=HEADERS, json={"entity_id": light_state.entity_id}) as response:
                if response.status == 200:
                    return schemas.LightStateResponse(message="Light turned off", success=True)
                else:
                    return schemas.LightStateResponse(message="Failed to turn off light", success=False)
    except Exception as e:
        return schemas.LightStateResponse(message=str(e), success=False)
