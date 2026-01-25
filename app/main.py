from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import engine, Base
from app.routes import auth, users, homecontrollers, voice

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context to handle startup/shutdown tasks."""
    # Run DB migrations / create tables on startup
    async with engine.begin() as conn:  # type: AsyncEngine
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Place for any async shutdown logic if needed


app = FastAPI(
    title="Neura API",
    description="FastAPI application with PostgreSQL and JWT authentication",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(homecontrollers.router)
app.include_router(voice.router)


@app.get("/")
async def read_root():
    """Root endpoint"""
    return {"message": "Welcome to Neura API"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
