from openai import AsyncOpenAI
from app.config import LLM_KEY
client = AsyncOpenAI(
    api_key=LLM_KEY,
    base_url="https://api.groq.com/openai/v1",
)


async def query_llm(prompt: str) -> str:
    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Neura Home voice assistant. "
                    "Answer shortly and concisely. "
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=1,
    )
    return response.choices[0].message.content

