"""User-Agent 设备信息提取（无需第三方依赖）."""

import re
from typing import Any


def describe_user_agent(user_agent: str | None) -> dict[str, str]:
    ua = str(user_agent or "")
    lower = ua.lower()

    if "ipad" in lower or "tablet" in lower:
        device_type = "tablet"
    elif "iphone" in lower or "android" in lower or "mobile" in lower:
        device_type = "mobile"
    elif any(token in lower for token in ("bot", "spider", "crawler")):
        device_type = "bot"
    else:
        device_type = "desktop"

    if "iphone" in lower:
        model = "iPhone"
    elif "ipad" in lower:
        model = "iPad"
    elif "android" in lower:
        match = re.search(r"android[^;)]*;\s*([^;)]+?)(?:\s+build|\))", ua, re.I)
        model = match.group(1).strip() if match else "Android"
    elif "windows" in lower:
        model = "Windows PC"
    elif "macintosh" in lower or "mac os" in lower:
        model = "Mac"
    elif "linux" in lower:
        model = "Linux"
    else:
        model = "Unknown"

    if "windows nt" in lower:
        os_name = "Windows"
    elif "iphone" in lower or "ipad" in lower:
        os_name = "iOS"
    elif "android" in lower:
        os_name = "Android"
    elif "mac os x" in lower or "macintosh" in lower:
        os_name = "macOS"
    elif "linux" in lower:
        os_name = "Linux"
    else:
        os_name = "Unknown"

    if "edg/" in lower:
        browser = "Edge"
    elif "firefox/" in lower:
        browser = "Firefox"
    elif "chrome/" in lower or "crios/" in lower:
        browser = "Chrome"
    elif "safari/" in lower:
        browser = "Safari"
    elif "curl/" in lower:
        browser = "curl"
    else:
        browser = "Unknown"

    return {
        "device_type": device_type,
        "device_model": model,
        "os": os_name,
        "browser": browser,
    }


def device_summary(device: dict[str, Any]) -> str:
    parts = [str(device.get(key) or "").strip() for key in ("device_model", "os", "browser")]
    return " · ".join(part for part in parts if part and part != "Unknown")
