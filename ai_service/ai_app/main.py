from fastapi import FastAPI
from ai_app.routes.ai import router as ai_router

app = FastAPI(
    title="Neura AI Service",
    version="1.0.0"
)

app.include_router(ai_router)

@app.get("/health")
async def health():
    return {"status": "AI healthy"}
