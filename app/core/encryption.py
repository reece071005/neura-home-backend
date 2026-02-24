import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.auth import SECRET_KEY


def _get_fernet() -> Fernet:
    """
    Derive a Fernet key from the application's SECRET_KEY.

    This lets us encrypt/decrypt sensitive configuration values (like
    Home Assistant access tokens) without storing them in plain text.
    """
    # Derive a 32-byte key from SECRET_KEY and convert to urlsafe base64
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt a secret string and return a URL-safe ciphertext."""
    f = _get_fernet()
    token = f.encrypt(plain_text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt a previously encrypted secret string."""
    f = _get_fernet()
    try:
        plain = f.decrypt(cipher_text.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stored secret cannot be decrypted with current key",
        )

