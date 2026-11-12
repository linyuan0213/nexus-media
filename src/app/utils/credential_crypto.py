"""站点凭据加解密（位于 utils，供 db 仓储使用）."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import settings


def _credential_fernet_key() -> str:
    secret = settings.get("security").get("jwt_secret") or settings.get("app").get("web_secret_key") or ""
    if not secret:
        raise RuntimeError("未配置 security.jwt_secret，无法加密站点凭据")
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return Fernet(_credential_fernet_key()).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return Fernet(_credential_fernet_key()).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
        return ""
