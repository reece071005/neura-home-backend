from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import base64
import os
from app import models, schemas, auth
from app.database import get_db
router = APIRouter(prefix="/userfaces", tags=["userfaces"])

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RESIDENTS_DIR = _PROJECT_ROOT / "residents"
_ALLOWED_EXTS = [".jpg", ".jpeg", ".png", ".webp"]


def _ensure_residents_dir() -> None:
    _RESIDENTS_DIR.mkdir(parents=True, exist_ok=True)


def _ext_for_upload(upload: UploadFile) -> str:
    # Prefer content-type; fall back to filename suffix.
    ct = (upload.content_type or "").lower()
    if ct == "image/jpeg":
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return ".jpg"
    if suffix in {".png", ".webp"}:
        return suffix
    return ""


def _media_type_for_path(path: Path) -> str:
    s = path.suffix.lower()
    if s in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if s == ".png":
        return "image/png"
    if s == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _find_userface_path(username: str) -> Path | None:
    """Find an existing face image on disk for this username."""
    _ensure_residents_dir()
    for ext in _ALLOWED_EXTS:
        candidate = _RESIDENTS_DIR / f"{username}{ext}"
        if candidate.exists():
            return candidate
    return None


@router.get("/get-all-userfaces", response_model=list[schemas.UserfaceResponse])
async def get_userfaces(
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """
    Admin-only endpoint to get all userfaces.

    This scans the ./residents folder and returns one entry per image file
    whose stem matches an existing username.
    """
    _ensure_residents_dir()

    files = [
        p for p in _RESIDENTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _ALLOWED_EXTS
    ]
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No userfaces found")

 
    result = await db.execute(
        select(models.Userface, models.User)
        .join(models.User, models.Userface.user_id == models.User.id)
    )
    rows = result.all()

    responses: list[schemas.UserfaceResponse] = []

    for userface, user in rows:
        file = _find_userface_path(userface.name)
        if not file:
            continue
        media_type = _media_type_for_path(file)
        file_data = file.read_bytes()
        file_data_base64 =  "data:" + media_type + ";base64," + base64.b64encode(file_data).decode("utf-8")

        responses.append(
            schemas.UserfaceResponse(
                user_id=userface.user_id,
                username=user.username,
                name=userface.name,
                image_base64=file_data_base64,
            )
        )

    return responses


@router.get("/me", response_model=schemas.UserfaceResponse)
async def get_my_userfaces(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """List only the current user's userfaces."""
    result = await db.execute(
        select(models.Userface).where(models.Userface.user_id == current_user.id)
    )
    userface = result.scalar_one_or_none()
    if not userface:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No userface found")

    # Use current_user.username since userface may not have username attribute
    file = _find_userface_path(userface.name)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No userface found")
    media_type = _media_type_for_path(file)
    file_data = file.read_bytes()
    file_data_base64 = "data:" + media_type + ";base64," + base64.b64encode(file_data).decode("utf-8")

    return schemas.UserfaceResponse(
        user_id=userface.user_id,
        username=current_user.username,
        name=userface.name,
        image_base64=file_data_base64,
    )

@router.delete('/delete-userface', response_model=schemas.UserfaceDelete)
async def delete_userface(
    target_username:str=Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Delete the current user's userface."""
    if current_user.role == models.UserRole.admin and target_username:
        result_user = await db.execute(select(models.User).where(models.User.username == target_username))
        queried_user = result_user.scalar_one_or_none()
        if not queried_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")
        target_user = queried_user
    else:
        target_user = current_user

    result = await db.execute(select(models.Userface).where(models.Userface.user_id == target_user.id))
    userface = result.scalars().one_or_none()
    if not userface:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No userface found")

    file = _find_userface_path(userface.name)
    if file and file.exists():
        os.remove(file)

    await db.delete(userface)
    await db.commit()
    return schemas.UserfaceDelete(
        username=target_user.username,
        name=userface.name,
        status="Userface deleted successfully",
    )



@router.post(
    "/add-userface",
    response_model=schemas.UserfaceCreate,
    status_code=status.HTTP_201_CREATED,
)
async def add_userface(
    image: UploadFile = File(...),
    face_name: str | None = Form(None),
    username: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Upload a face image and store it under ./residents/.

    - Admin: can upload for any user.
    - Normal user: can upload only for themselves;
    """
    _ensure_residents_dir()

    ext = _ext_for_upload(image)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Use JPEG/PNG/WebP.",
        )

    # Figure out target user and associated username/id
    target_user = current_user
    if current_user.role == models.UserRole.admin and username:
        result_user = await db.execute(select(models.User).where(models.User.username == username))
        queried_user = result_user.scalar_one_or_none()
        if not queried_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")
        target_user = queried_user

    target_username = target_user.username
    target_user_id = target_user.id

    actual_face_name = face_name if face_name else target_username

    filename = f"{actual_face_name}{ext}"
    disk_path = _RESIDENTS_DIR / filename
    rel_path = f"residents/{filename}"

    data = await image.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    disk_path.write_bytes(data)

    result_face = await db.execute(
        select(models.Userface).where(models.Userface.user_id == target_user_id)
    )
    existing_face = result_face.scalar_one_or_none()
    if existing_face:
        # Remove previous image file if path changed
        old_rel_path = existing_face.image_path
        if old_rel_path and old_rel_path != rel_path:
            old_disk_path = _PROJECT_ROOT / old_rel_path
            if old_disk_path.exists():
                try:
                    old_disk_path.unlink()
                except OSError:
                    pass

        existing_face.name = actual_face_name
        existing_face.image_path = rel_path
        db_userface = existing_face
    else:
        db_userface = models.Userface(
            user_id=target_user_id,
            name=actual_face_name,
            image_path=rel_path,
        )
        db.add(db_userface)

    await db.commit()
    await db.refresh(db_userface)

    return schemas.UserfaceCreate(
        username=target_username,
        name=actual_face_name,
        status="Userface created successfully",
    )