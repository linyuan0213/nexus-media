"""Provider registration helpers."""

from app.infrastructure.ocr.providers.base import Provider
from app.infrastructure.ocr.providers.remote import RemoteProvider


def default_providers() -> list[Provider]:
    """Return the default set of provider instances."""
    return [RemoteProvider()]


__all__ = ["Provider", "RemoteProvider", "default_providers"]
