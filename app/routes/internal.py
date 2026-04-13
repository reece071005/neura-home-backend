from fastapi import APIRouter, HTTPException

from app import config

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/home-assistant-config", include_in_schema=False)
async def get_home_assistant_config():
    await config.load_home_assistant_config_from_db()

    if not config.HOME_ASSISTANT_URL or not config.ACCESS_TOKEN:
        raise HTTPException(
            status_code=404,
            detail="Home Assistant URL/secret not configured.",
        )

    return {
        "ok": True,
        "url": config.HOME_ASSISTANT_URL,
        "token": config.ACCESS_TOKEN,
    }