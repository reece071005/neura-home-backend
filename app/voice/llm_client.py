# app/voice/llm_client.py

import aiohttp
from pydantic import BaseModel, ValidationError
from typing import Optional
from app.core.redis_init import get_redis
import json

LLM_API_URL = "http://localhost:8080/completion"

class LLMIntentResponse(BaseModel):
    intent: str
    device: Optional[str] = None
    location: Optional[str] = None
    brightness: Optional[int] = None
    response: Optional[str] = None

async def fetch_intent_from_llm(prompt: str) -> Optional[LLMIntentResponse]:
    redis = get_redis()
    controllable_devices = await redis.get("controllable_devices")
    controllable_devices = json.loads(controllable_devices)
    memory = f"""You are a helpful assistant that can help with home automation tasks. You can control lights, fans, and other devices. You can also answer questions and help with tasks.
    Output only in json format.
    You can control the following devices:
    - lights
    - fans
    - ac (always put as climate)

    available device entities:
    {controllable_devices}

    """
    payload = {
        "prompt": memory + prompt,
        "n_predict": 256
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(LLM_API_URL, json=payload) as resp:
                data = await resp.json()
                content = data.get("content", "")

                # parsing content as JSOn
                parsed = LLMIntentResponse.model_validate_json(content)
                return parsed

        except (aiohttp.ClientError, ValidationError, ValueError) as e:
            print(f"LLM Error: {e}")
            return None
