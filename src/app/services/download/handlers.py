"""下载领域事件处理器."""

import log
from app.events import Event, on_event
from app.events.constants import DOWNLOAD_FAILED, DOWNLOAD_STARTED
from app.events.payloads import DownloadFailedPayload, DownloadStartedPayload


@on_event(DOWNLOAD_STARTED)
def handle_download_started(event: Event) -> None:
    """下载开始事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadStartedPayload):
        payload = DownloadStartedPayload(**payload)
    log.info(f"[Event]下载开始: {payload.media_info.get('title')}")


@on_event(DOWNLOAD_FAILED)
def handle_download_failed(event: Event) -> None:
    """下载失败事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadFailedPayload):
        payload = DownloadFailedPayload(**payload)
    log.warn(f"[Event]下载失败: {payload.media_info.get('title')} 原因: {payload.reason}")
