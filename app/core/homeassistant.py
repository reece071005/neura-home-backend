import aiohttp
from app.config import HOME_ASSISTANT_URL, HEADERS
from app import schemas

# Turn on light
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

# Turn off light
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

# Get all available HA devices
async def get_all_devices():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{HOME_ASSISTANT_URL}/states", headers=HEADERS) as response:
                if response.status != 200:
                    return []

                data = await response.json()

                devices = []
                for item in data:
                    entity_id = item.get("entity_id", "")
                    kind = entity_id.split(".")[0]
                    name = item.get("attributes", {}).get("friendly_name", "")

                    if kind in ["light", "fan", "switch", "cover", "climate"]:
                        devices.append({
                            "entity_id": entity_id,
                            "kind": kind,
                            "name": name
                        })

                return devices
    except Exception as e:
        print("Failed to get devices:", str(e))
        return []

# 🔧 General-purpose device control (Step 2)
async def control_device(device: schemas.DeviceControlRequest):
    payload = {"entity_id": device.entity_id}

    # Optional fields
    if device.brightness is not None:
        payload["brightness"] = device.brightness
    if device.temperature is not None:
        payload["temperature"] = device.temperature
    if device.hvac_mode is not None:
        payload["hvac_mode"] = device.hvac_mode
    if device.position is not None:
        payload["position"] = device.position

    service = "turn_on" if device.state == "on" else "turn_off"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HOME_ASSISTANT_URL}/services/{device.domain}/{service}",
                headers=HEADERS,
                json=payload
            ) as response:
                if 200 <= response.status < 300:
                    return {"success": True, "message": f"{device.domain.title()} {service.replace('_', ' ')} successful."}
                text = await response.text()
                return {"success": False, "message": f"HA {response.status}: {text}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
