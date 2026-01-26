import aiohttp
from app.config import HOME_ASSISTANT_URL, HEADERS
from app import schemas

async def turn_on_light(light_state: schemas.LightState):
    payload = {"entity_id": light_state.entity_id}
    if light_state.brightness is not None:
        payload["brightness"] = light_state.brightness  # only include if provided

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HOME_ASSISTANT_URL}/services/light/turn_on",
                headers=HEADERS,
                json=payload
            ) as response:
                if 200 <= response.status < 300:
                    return schemas.LightStateResponse(message="Light turned on", success=True)

                text = await response.text()
                return schemas.LightStateResponse(
                    message=f"Failed to turn on light (HA {response.status}): {text}",
                    success=False
                )
    except Exception as e:
        return schemas.LightStateResponse(message=str(e), success=False)

async def turn_off_light(light_state: schemas.LightState):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HOME_ASSISTANT_URL}/services/light/turn_off",
                headers=HEADERS,
                json={"entity_id": light_state.entity_id}
            ) as response:
                if 200 <= response.status < 300:
                    return schemas.LightStateResponse(message="Light turned off", success=True)

                text = await response.text()
                return schemas.LightStateResponse(
                    message=f"Failed to turn off light (HA {response.status}): {text}",
                    success=False
                )
    except Exception as e:
        return schemas.LightStateResponse(message=str(e), success=False)

