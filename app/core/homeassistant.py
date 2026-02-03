import aiohttp
from typing import Optional
from app.config import HOME_ASSISTANT_URL, HEADERS
from app import schemas
from app.core.redis_init import get_redis

class LightControl:
    @staticmethod
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

    @staticmethod
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

class CoverControl:
    @staticmethod
    async def open_cover(cover_entity: str):
        payload = {"entity_id": cover_entity}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{HOME_ASSISTANT_URL}/services/cover/open_cover", headers=HEADERS, json=payload) as response:
                    if 200 <= response.status < 300:
                        return schemas.CoverStateResponse(message="Cover opened", success=True)
                    text = await response.text()
                    return schemas.CoverStateResponse(message=f"Failed to open cover (HA {response.status}): {text}", success=False)
        except Exception as e:
            return schemas.CoverStateResponse(message=str(e), success=False)
    @staticmethod
    async def close_cover(cover_entity: str):
        payload = {"entity_id": cover_entity}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{HOME_ASSISTANT_URL}/services/cover/close_cover", headers=HEADERS, json=payload) as response:
                    if 200 <= response.status < 300:
                        return schemas.CoverStateResponse(message="Cover closed", success=True)
                    text = await response.text()
                    return schemas.CoverStateResponse(message=f"Failed to close cover (HA {response.status}): {text}", success=False)
        except Exception as e:
            return schemas.CoverStateResponse(message=str(e), success=False)


    @staticmethod
    async def set_cover_position(cover_entity: str, position: int):
        payload = {"entity_id": cover_entity, "position": position}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{HOME_ASSISTANT_URL}/services/cover/set_cover_position", headers=HEADERS, json=payload) as response:
                    if 200 <= response.status < 300:
                        return schemas.CoverStateResponse(message="Cover position set", success=True)
                    text = await response.text()
                    return schemas.CoverStateResponse(message=f"Failed to set cover position (HA {response.status}): {text}", success=False)
        except Exception as e:
            return schemas.CoverStateResponse(message=str(e), success=False)

class ClimateControl:
    @staticmethod
    async def control_climate(
        entity_id: str,
        state: Optional[str] = None,                 # "on" / "off" / "toggle"
        hvac_mode: Optional[str] = None,             # "heat", "cool", "heat_cool", "auto", "off", ...
        temperature: Optional[float] = None,         # single target temperature
        fan_mode: Optional[str] = None,              # e.g. "low", "medium", "high"
        swing_mode: Optional[str] = None,            # e.g. "on"/"off" (depends on device)
        swing_horizontal_mode: Optional[str] = None, # e.g. "on"/"off" (depends on device)
    ) -> dict:
        """
        Control a Home Assistant climate entity via all common services.

        - state: climate.turn_on / turn_off / toggle
        - hvac_mode: climate.set_hvac_mode
        - temperature: climate.set_temperature
        - fan_mode: climate.set_fan_mode
        - swing_mode: climate.set_swing_mode
        - swing_horizontal_mode: climate.set_swing_horizontal_mode
        """
        async with aiohttp.ClientSession() as session:
            ok = True
            messages: list[str] = []

            async def call_service(service: str, body: dict) -> None:
                nonlocal ok, messages
                try:
                    async with session.post(
                        f"{HOME_ASSISTANT_URL}/services/climate/{service}",
                        headers=HEADERS,
                        json=body,
                    ) as resp:
                        text = await resp.text()
                        if not (200 <= resp.status < 300):
                            ok = False
                        messages.append(f"climate.{service} -> {resp.status}: {text}")
                except Exception as e:
                    ok = False
                    messages.append(f"climate.{service} failed: {e}")

            # On / off / toggle
            if state in {"on", "off", "toggle"}:
                service = "turn_on" if state == "on" else "turn_off" if state == "off" else "toggle"
                await call_service(service, {"entity_id": entity_id})

            # HVAC mode
            if hvac_mode is not None:
                await call_service("set_hvac_mode", {"entity_id": entity_id, "hvac_mode": hvac_mode})

            # Temperature / heat_cool targets
            if temperature is not None:
                temp_payload: dict = {"entity_id": entity_id}
                if temperature is not None:
                    temp_payload["temperature"] = temperature
                await call_service("set_temperature", temp_payload)

            # Fan mode
            if fan_mode is not None:
                await call_service("set_fan_mode", {"entity_id": entity_id, "fan_mode": fan_mode})

            # Swing mode (vertical)
            if swing_mode is not None:
                await call_service("set_swing_mode", {"entity_id": entity_id, "swing_mode": swing_mode})

            # Swing horizontal mode
            if swing_horizontal_mode is not None:
                await call_service(
                    "set_swing_horizontal_mode",
                    {"entity_id": entity_id, "swing_horizontal_mode": swing_horizontal_mode},
                )
        summary = "; ".join(messages) if messages else ""
        return schemas.ClimateStateResponse(success=ok, message=summary)


class FanControl:
    @staticmethod
    async def control_fan(
        entity_id: str,
        state: Optional[str] = None,              # "on" / "off" / "toggle"
        percentage: Optional[int] = None,       # 0–100
        oscillating: Optional[bool] = None,       # True / False
        direction: Optional[str] = None,          # "forward" / "reverse"
    ) -> schemas.FanStateResponse:
        """
        Control a Home Assistant fan entity using the available fan services:

        - turn_on / turn_off / toggle
        - set_percentage
        - increase_speed / decrease_speed
        - oscillate
        - set_direction
        """

        async with aiohttp.ClientSession() as session:
            ok = True
            messages: list[str] = []

            async def call_service(service: str, payload: dict):
                nonlocal ok, messages
                try:
                    async with session.post(
                        f"{HOME_ASSISTANT_URL}/services/fan/{service}",
                        headers=HEADERS,
                        json=payload,
                    ) as resp:
                        text = await resp.text()
                        if not (200 <= resp.status < 300):
                            ok = False
                        messages.append(f"fan.{service} -> {resp.status}: {text}")
                except Exception as e:
                    ok = False
                    messages.append(f"fan.{service} failed: {e}")

            # On / off / toggle
            if state in {"on", "off", "toggle"}:
                service = (
                    "turn_on" if state == "on" else "turn_off" if state == "off" else "toggle"
                )
                await call_service(service, {"entity_id": entity_id})

            # Set absolute percentage
            if percentage is not None:
                await call_service("set_percentage", {"entity_id": entity_id, "percentage": percentage})

            
            # Oscillation
            if oscillating is not None:
                await call_service("oscillate", {"entity_id": entity_id, "oscillating": oscillating})

            # Direction
            if direction is not None:
                await call_service("set_direction", {"entity_id": entity_id, "direction": direction})

        summary = "; ".join(messages) if messages else ""
        return schemas.FanStateResponse(success=ok, message=summary)
class DeviceControl:
    # Get all available HA devices (with the area name)
    @staticmethod
    async def get_all_devices():
        try:
            async with aiohttp.ClientSession() as session:
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

                    if kind in ["light", "fan", "switch", "cover", "climate", "media_player", "camera", "sensor", "binary_sensor"]:
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


    # Get all controllable devices
    @staticmethod
    async def get_controllable_devices():
        controllable_devices = []
        devices = await DeviceControl.get_all_devices()
        for device in devices:
            if device.get("kind") in ["light", "fan", "cover", "climate"]:
                if 'spot' in device.get("entity_id"):
                    continue
                controllable_devices.append(device.get("entity_id"))
        return controllable_devices


    # Get the current state of all devices
    @staticmethod
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


class CameraControl:
    @staticmethod
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


