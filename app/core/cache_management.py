import json
from app.core.redis_init import get_redis
from app.core.homeassistant import DeviceControl

class CacheManagement:
    @staticmethod
    async def update_cache():
        redis = get_redis()
        devices = await DeviceControl.get_all_devices()
        controllable_devices = await DeviceControl.get_controllable_devices()
        await redis.set("devices", json.dumps(devices))
        await redis.set("controllable_devices", json.dumps(controllable_devices))
