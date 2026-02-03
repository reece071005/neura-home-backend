# app/voice/llm_client.py

import aiohttp
from pydantic import BaseModel, ValidationError
from typing import Optional
from app.core.redis_init import get_redis
import json


LLM_API_URL = "http://host.docker.internal:11434/v1/chat/completions"

class LLMIntentResponse(BaseModel):
    intent: str
    device: Optional[str] = None
    location: Optional[str] = None
    response: Optional[str] = None
    entity_id: Optional[list|str] = None

async def fetch_intent_from_llm(prompt: str, intent_result: dict) -> Optional[LLMIntentResponse]:

    memory = f"""
You are a home automation command parser.

CRITICAL RULES:
- Output ONLY ONE JSON object.
- Do NOT output arrays.
- Do NOT repeat entities.
- Do NOT explain your reasoning.
- Do NOT output text outside JSON.

Output format (EXACT KEYS):
{{
  "intent": "turn_on | turn_off | set | open | close",
  "domain": "light | fan | cover | climate",
  "entity_id": "<ONE entity from the list below>",
  "location": "<normalized location name>",
  "parameters": {{
    "brightness": number | null,
    "temperature": number | null,
    "mode": "heat | cool | auto | off" | null,
    "position": number | null
  }},
  "response": "<short human-friendly sentence>"
}}

Device normalization rules:
- blinds → domain "cover"
- ac → domain "climate"
- window blind → domain "cover"

Available entities (choose ONE):
{intent_result["entity_id_candidates"][0]}
Your output entity_id MUST be copied exactly from this list.
Do not change it in any way.

User command:
{prompt}
"""

    payload = {
        "model": "phi4-instruct",
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": memory
            }
        ]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(LLM_API_URL, json=payload) as resp:
                data = await resp.json()
                print(data)
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(content)
                print(data)
                print(payload)

                # parsing content as JSOn
                parsed = LLMIntentResponse.model_validate_json(content)
                return parsed

        except (aiohttp.ClientError, ValidationError, ValueError) as e:
            print(f"LLM Error: {e}")
            return None
