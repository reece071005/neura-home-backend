from zeroconf import Zeroconf, ServiceBrowser
import socket
import time
import asyncio
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import models, schemas, auth
from app.database import get_db
from app.core.encryption import encrypt_secret, decrypt_secret

HOME_ASSISTANT_PORT = 8123
SERVICE_TYPE = "_http._tcp.local."

router = APIRouter(prefix="/hub", tags=["hub"])


class HAListener:
    def __init__(self):
        self.instances: List[Dict[str, object]] = []

    def remove_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            for addr in info.addresses:
                ip = socket.inet_ntoa(addr)
                port = info.port

                # Filter for Home Assistant default port
                if port == HOME_ASSISTANT_PORT:
                    self.instances.append(
                        {
                            "name": name,
                            "ip": ip,
                            "port": port,
                            "base_url": f"http://{ip}:{port}",
                        }
                    )


def _discover_home_assistant_sync(timeout: int = 5) -> list[dict]:
    """Blocking zeroconf discovery; run in a thread from async code."""
    zeroconf = Zeroconf()
    listener = HAListener()
    ServiceBrowser(zeroconf, SERVICE_TYPE, listener)

    # Allow some time for services to be discovered
    time.sleep(timeout)

    zeroconf.close()
    return listener.instances


@router.get("/discover", response_model=list[schemas.HomeAssistantInstance])
async def discover_home_assistant(
    timeout: int = 5,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Discover Home Assistant instances on the local network and return them
    as a list of devices (name, IP, port, base_url).
    """
    instances = await asyncio.to_thread(_discover_home_assistant_sync, timeout)
    return instances


@router.get("/home-assistant-url", response_model=schemas.HomeAssistantUrl)
async def get_home_assistant_url(
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """
    Retrieve the stored Home Assistant base URL.
    Admin-only since this is sensitive configuration.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_url")
    )
    config = result.scalar_one_or_none()

    if not config or not config.value or "url" not in config.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Home Assistant URL not configured",
        )

    return schemas.HomeAssistantUrl(url=config.value["url"])


@router.post("/home-assistant-url")
async def save_home_assistant_url(
    payload: schemas.HomeAssistantUrl,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """
    Save the Home Assistant base URL into the configurations table.
    This is admin-only since it affects system-wide behavior.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_url")
    )
    config = result.scalar_one_or_none()

    if config:
        config.value = dict(config.value or {})
        config.value["url"] = payload.url
    else:
        config = models.Configuration(key="home_assistant_url", value={"url": payload.url})
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return {"key": config.key, "value": config.value}


@router.post("/home-assistant-secret")
async def save_home_assistant_secret(
    payload: schemas.HomeAssistantSecret,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """
    Store the Home Assistant access token / secret in encrypted form.
    Admin-only, since this grants control of the Home Assistant instance.
    """
    encrypted = encrypt_secret(payload.secret)

    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_secret")
    )
    config = result.scalar_one_or_none()

    if config:
        config.value = dict(config.value or {})
        config.value["ciphertext"] = encrypted
    else:
        config = models.Configuration(
            key="home_assistant_secret",
            value={"ciphertext": encrypted},
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return {"key": config.key}


@router.get("/home-assistant-secret", response_model=schemas.HomeAssistantSecretResponse)
async def get_home_assistant_secret(
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """
    Retrieve and decrypt the stored Home Assistant secret.
    Admin-only – treat the returned value as highly sensitive.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "home_assistant_secret")
    )
    config = result.scalar_one_or_none()

    if not config or not config.value or "ciphertext" not in config.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Home Assistant secret not configured",
        )

    secret = decrypt_secret(config.value["ciphertext"])
    return schemas.HomeAssistantSecretResponse(secret=secret)
