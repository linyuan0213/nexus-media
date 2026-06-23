"""下载领域事件处理器."""

import log
from app.events import Event, on_event
from app.events.constants import DOWNLOAD_COMPLETED, DOWNLOAD_FAILED, DOWNLOAD_STARTED
from app.events.payloads import DownloadCompletedPayload, DownloadFailedPayload, DownloadStartedPayload
from app.services.download_event_queue import download_event_queue


@on_event(DOWNLOAD_STARTED)
def handle_download_started(event: Event) -> None:
    """下载开始事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadStartedPayload):
        payload = DownloadStartedPayload(**payload)
    log.info(f"[Event]下载开始: {payload.media_info.get('title')}")
    queue_size_before = download_event_queue.qsize()
    download_event_queue.put(
        {
            "event": DOWNLOAD_STARTED,
            "data": {
                "downloader_id": payload.downloader_id,
                "download_id": payload.download_id,
                "title": payload.media_info.get("title"),
            },
        }
    )
    log.debug(f"[SSE]放入队列后 size={download_event_queue.qsize()} (before={queue_size_before})")


@on_event(DOWNLOAD_FAILED)
def handle_download_failed(event: Event) -> None:
    """下载失败事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadFailedPayload):
        payload = DownloadFailedPayload(**payload)
    log.warn(f"[Event]下载失败: {payload.media_info.get('title')} 原因: {payload.reason}")
    download_event_queue.put(
        {"event": DOWNLOAD_FAILED, "data": {"title": payload.media_info.get("title"), "reason": payload.reason}}
    )


@on_event(DOWNLOAD_COMPLETED)
def handle_download_completed(event: Event) -> None:
    """下载完成事件处理器"""
    payload = event.payload
    if not isinstance(payload, DownloadCompletedPayload):
        payload = DownloadCompletedPayload(**payload)
    log.info(f"[Event]下载完成: {payload.task_id} @ {payload.path}")
    download_event_queue.put(
        {
            "event": DOWNLOAD_COMPLETED,
            "data": {
                "downloader_id": payload.downloader_id,
                "task_id": payload.task_id,
                "path": payload.path,
                "tags": payload.tags,
                "name": payload.name,
            },
        }
    )
