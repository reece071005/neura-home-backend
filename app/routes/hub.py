import time
import asyncio
import aiohttp
from typing import List, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import models, schemas, auth
from app.database import get_db
from app.core.encryption import encrypt_secret, decrypt_secret
from app.config import load_home_assistant_config_from_db
from app.core.cache_management import CacheManagement

router = APIRouter(prefix="/hub", tags=["hub"])


async def get_admin_or_none_for_home_assistant(
    db: AsyncSession = Depends(get_db),
    optional_admin: Optional[models.User] = Depends(auth.get_current_admin_user_optional),
) -> Optional[models.User]:
    """
    For initial setup (no Home Assistant config in DB): allow unauthenticated access (returns None).
    Once HA is configured: require admin; 401 if no/invalid token.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_url")
    )
    config = result.scalar_one_or_none()
    has_url = (
        config is not None
        and config.value
        and isinstance(config.value, dict)
        and config.value.get("url")
    )
    if not has_url:
        return None
    if optional_admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view or change Home Assistant configuration",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return optional_admin


def _normalize_url(url: str) -> str:
    """Strip trailing slash for consistent storage."""
    return url.rstrip("/") if url else url


async def _validate_home_assistant_url(url: str) -> str:
    """
    Verify the URL is reachable by requesting the Home Assistant API root.
    Raises HTTPException if the URL is invalid or unreachable.

    Returns the normalized base URL (without a trailing slash).
    """
    base = _normalize_url(url)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL cannot be empty",
        )
    # If the URL already points at the API (e.g. ends with /api or /api/),
    check_url = base
    if base.endswith("/api/"):
        check_url = base[:-1]  # remove trailing slash
    elif base.endswith("/api"):
        check_url = base
    else:
        check_url = f"{base}/api"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(check_url) as resp:
                # 200 (API running), 401 (auth required), 405 (method) all indicate valid HA
                if resp.status >= 500:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Home Assistant returned server error (HTTP {resp.status})",
                    )
                return check_url
    except aiohttp.ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not reach Home Assistant at {url}: {e!s}",
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeout connecting to Home Assistant at {url}",
        )


@router.get("/home-assistant", response_model=schemas.HomeAssistantConfigResponse)
async def get_home_assistant_config(
    db: AsyncSession = Depends(get_db),
    _admin: Optional[models.User] = Depends(get_admin_or_none_for_home_assistant),
):
    """
    Retrieve the stored Home Assistant URL and secret (if configured).
    No auth required when HA is not yet configured (initial setup); admin-only once configured.
    """
    # URL
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_url")
    )
    url_config = result.scalar_one_or_none()
    url = None
    if url_config and url_config.value and "url" in url_config.value:
        url = url_config.value["url"]

    # Secret
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_secret")
    )
    secret_config = result.scalar_one_or_none()
    secret = None
    if secret_config and secret_config.value and "ciphertext" in secret_config.value:
        secret = decrypt_secret(secret_config.value["ciphertext"])

    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Home Assistant not configured",
        )

    return schemas.HomeAssistantConfigResponse(url=url, secret=secret)


@router.post("/home-assistant", response_model=schemas.HomeAssistantConfigResponse)
async def save_home_assistant_config(
    payload: schemas.HomeAssistantConfig,
    db: AsyncSession = Depends(get_db),
    _admin: Optional[models.User] = Depends(get_admin_or_none_for_home_assistant),
):
    """
    Save the Home Assistant URL and optionally the secret.
    Validates that the URL is reachable before saving.
    No auth required when HA is not yet configured (initial setup); admin-only once configured.
    """
    updated_url = await _validate_home_assistant_url(payload.url)
    url_value = _normalize_url(updated_url)

    # Save URL
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_url")
    )
    url_config = result.scalar_one_or_none()
    if url_config:
        url_config.value = dict(url_config.value or {})
        url_config.value["url"] = url_value
    else:
        url_config = models.Configuration(key="home_assistant_url", value={"url": url_value})
        db.add(url_config)

    # Save secret only if provided
    if payload.secret is not None:
        encrypted = encrypt_secret(payload.secret)
        result = await db.execute(
            select(models.Configuration).where(models.Configuration.key == "home_assistant_secret")
        )
        secret_config = result.scalar_one_or_none()
        if secret_config:
            secret_config.value = dict(secret_config.value or {})
            secret_config.value["ciphertext"] = encrypted
        else:
            secret_config = models.Configuration(
                key="home_assistant_secret",
                value={"ciphertext": encrypted},
            )
            db.add(secret_config)

    await db.commit()
    await db.refresh(url_config)

    # Reload in-process Home Assistant configuration so subsequent requests
    # immediately use the new URL/credentials without needing an app restart.
    await load_home_assistant_config_from_db()
    await CacheManagement.update_cache()

    return schemas.HomeAssistantConfigResponse(url=url_value, secret=payload.secret)
