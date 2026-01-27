import aiohttp
from app.config import HOME_ASSISTANT_URL, HEADERS
from app import schemas

# Turn on light
async def turn_on_light(light_state: schemas.LightState):
    payload = {"entity_id": light_state.entity_id}
    if light_state.brightness is not None:
        payload["brightness"] = light_state.brightness 

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

# Get all available HA devices (with the area name)
async def get_all_devices():
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch all device states
            async with session.get(f"{HOME_ASSISTANT_URL}/states", headers=HEADERS) as response:
                if response.status != 200:
                    return []
                states_data = await response.json()

            # Fetch area metadata
            async with session.get(f"{HOME_ASSISTANT_URL}/areas", headers=HEADERS) as area_response:
                area_lookup = {}
                if area_response.status == 200:
                    area_data = await area_response.json()
                    area_lookup = {a["area_id"]: a["name"] for a in area_data}

            # Building a device list
            devices = []
            for item in states_data:
                entity_id = item.get("entity_id", "")
                kind = entity_id.split(".")[0]
                name = item.get("attributes", {}).get("friendly_name", "")
                area_id = item.get("area_id", None)
                area_name = area_lookup.get(area_id, "")

                if kind in ["light", "fan", "switch", "cover", "climate"]:
                    devices.append({
                        "entity_id": entity_id,
                        "kind": kind,
                        "name": name,
                        "area": area_name
                    })

            return devices
    except Exception as e:
        print("Failed to get devices:", str(e))
        return []

# General-purpose device control
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

async def get_current_state():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{HOME_ASSISTANT_URL}/states", headers=HEADERS) as response:
                if response.status != 200:
                    return []
                states_data = await response.json()
                return states_data
    except Exception as e:
        print("Failed to get current state:", str(e))
        return []

async def get_camera_snapshot(camera_entity: str):
    """
    Fetch a camera snapshot from Home Assistant.
    
    Args:
        camera_entity: The camera entity ID (e.g., "camera.frontdoor")
    
    Returns:
        Tuple of (image_bytes, content_type) or (None, None) on error
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HOME_ASSISTANT_URL}/camera_proxy/{camera_entity}",
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    return None, None
                
                # Read the image data
                image_data = await response.read()
                content_type = response.headers.get('Content-Type', 'image/jpeg')
                
                return image_data, content_type
    except Exception as e:
        print(f"Failed to get camera snapshot: {str(e)}")
        return None, None