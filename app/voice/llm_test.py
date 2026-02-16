from openai import OpenAI
import os

client = OpenAI(
    api_key='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',
    base_url="https://api.groq.com/openai/v1",
)
response = client.chat.completions.create(
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
            "content": "what is the price of bitcoin now?"
        }
    ],
    temperature=1
)

print(response.choices[0].message.content)