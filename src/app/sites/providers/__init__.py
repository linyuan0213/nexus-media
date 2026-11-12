"""站点专属 SPA 签名器注册表."""

from collections.abc import Callable
from typing import Any

from app.sites.providers.piggo_spa import signed_headers as piggo_signed_headers

SpaSigner = Callable[..., dict[str, str]]

SPA_SIGNERS: dict[str, SpaSigner] = {
    "piggo": piggo_signed_headers,
}


def get_spa_signer(name: str) -> SpaSigner | None:
    return SPA_SIGNERS.get(str(name or "").strip())


__all__ = ["SPA_SIGNERS", "SpaSigner", "get_spa_signer"]
