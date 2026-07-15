"""Utilities for image recognition."""

import base64

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient


def fetch_image_b64(image_url: str, cookie: str | None = None, ua: str | None = None) -> str:
    """Download an image and return its base64 representation."""
    headers = {"User-Agent": ua} if ua else {}
    auth = CookieAuth(cookie) if cookie else None
    with HttpClient() as client:
        response = client.get(image_url, headers=headers, auth=auth)
    return base64.b64encode(response.content).decode()
