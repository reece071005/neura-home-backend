# app/voice/llm_client.py

import aiohttp
from pydantic import BaseModel, ValidationError
from typing import Optional

LLM_API_URL = "http://localhost:8080/completion"

class LLMIntentResponse(BaseModel):
    intent: str
    device: Optional[str] = None
    location: Optional[str] = None
    brightness: Optional[int] = None
    response: Optional[str] = None

async def fetch_intent_from_llm(prompt: str) -> Optional[LLMIntentResponse]:
    payload = {
        "prompt": prompt,
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
