"""浏览器失败诊断：保存失败截图并记录挑战/失败指标。"""

from __future__ import annotations

import base64
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import log
from app.core.settings import settings
from app.domain.browser_operation import BROWSER_METRICS, BrowserOperationContext


def capture_failure_screenshot(
    session: Any,
    context: BrowserOperationContext,
    reason: str,
    *,
    tab_name: str | None = None,
) -> str | None:
    """尽力保存失败现场截图；失败不影响主流程。"""
    BROWSER_METRICS.record_failure(context.operation)
    try:
        data = session.screenshot(tab_name=tab_name, full_page=True)
        raw = base64.b64decode(str((data or {}).get("png_base64") or ""))
        if not raw:
            return None
        folder = Path(settings.data_path) / "browser_failures"
        os.makedirs(folder, exist_ok=True)
        safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "_", reason)[:40].strip("_") or "failure"
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{context.operation}_{context.trace_id[:8]}_{safe_reason}.png"
        path = folder / name
        path.write_bytes(raw)
        log.warn(f"[BrowserFailure] {context.fields(reason=reason, screenshot=str(path))}")
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log.debug(f"[BrowserFailure] 截图失败 {context.fields(reason=reason, error=type(exc).__name__)}")
        return None
