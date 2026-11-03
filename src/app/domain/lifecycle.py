"""媒体生命周期统一阶段与状态映射（ADR-026）."""

from __future__ import annotations

from enum import Enum
from typing import Any


class LifecycleStage(str, Enum):
    IDENTIFIED = "identified"
    SUBSCRIBED = "subscribed"
    SEARCHING = "searching"
    DOWNLOAD_QUEUED = "download_queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSFER_QUEUED = "transfer_queued"
    TRANSFERRING = "transferring"
    TRANSFERRED = "transferred"
    SCRAPE_QUEUED = "scrape_queued"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    IN_LIBRARY = "in_library"


class LifecycleStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    DEAD = "dead"


STAGE_ORDER = {stage: index for index, stage in enumerate(LifecycleStage)}
TERMINAL_STATUSES = {
    LifecycleStatus.SUCCEEDED,
    LifecycleStatus.FAILED,
    LifecycleStatus.CANCELLED,
    LifecycleStatus.DEAD,
}


def map_task_status(value: Any) -> LifecycleStatus:
    key = _status_key(value)
    return {
        "queued": LifecycleStatus.QUEUED,
        "running": LifecycleStatus.RUNNING,
        "succeeded": LifecycleStatus.SUCCEEDED,
        "failed": LifecycleStatus.FAILED,
        "cancelled": LifecycleStatus.CANCELLED,
        "dead": LifecycleStatus.DEAD,
    }.get(key, LifecycleStatus.BLOCKED)


def map_torrent_status(value: Any) -> tuple[LifecycleStage, LifecycleStatus]:
    key = _status_key(value)
    if key in {"pending", "queued"}:
        return LifecycleStage.DOWNLOAD_QUEUED, LifecycleStatus.QUEUED
    if key in {"downloading", "checking"}:
        return LifecycleStage.DOWNLOADING, LifecycleStatus.RUNNING
    if key in {"paused", "stopped"}:
        return LifecycleStage.DOWNLOADING, LifecycleStatus.BLOCKED
    if key in {"error", "unknown"}:
        return LifecycleStage.DOWNLOADING, LifecycleStatus.FAILED
    if key in {"uploading"}:
        return LifecycleStage.DOWNLOADED, LifecycleStatus.SUCCEEDED
    return LifecycleStage.DOWNLOADING, LifecycleStatus.BLOCKED


def map_download_state(value: Any) -> tuple[LifecycleStage, LifecycleStatus]:
    key = _status_key(value)
    if key == "queued":
        return LifecycleStage.DOWNLOAD_QUEUED, LifecycleStatus.QUEUED
    if key == "downloading":
        return LifecycleStage.DOWNLOADING, LifecycleStatus.RUNNING
    if key == "completed":
        return LifecycleStage.DOWNLOADED, LifecycleStatus.SUCCEEDED
    if key in {"error", "failed"}:
        return LifecycleStage.DOWNLOADING, LifecycleStatus.FAILED
    return LifecycleStage.DOWNLOADING, LifecycleStatus.BLOCKED


def map_subscribe_state(value: Any) -> tuple[LifecycleStage, LifecycleStatus]:
    key = _status_key(value).upper()
    return {
        "D": (LifecycleStage.SUBSCRIBED, LifecycleStatus.QUEUED),
        "S": (LifecycleStage.SEARCHING, LifecycleStatus.RUNNING),
        "R": (LifecycleStage.SUBSCRIBED, LifecycleStatus.RUNNING),
        "C": (LifecycleStage.DOWNLOADED, LifecycleStatus.SUCCEEDED),
        "E": (LifecycleStage.SUBSCRIBED, LifecycleStatus.FAILED),
        "N": (LifecycleStage.SUBSCRIBED, LifecycleStatus.CANCELLED),
    }.get(key, (LifecycleStage.SUBSCRIBED, LifecycleStatus.BLOCKED))


def stage_rank(stage: LifecycleStage | str) -> int:
    try:
        return STAGE_ORDER[LifecycleStage(str(stage))]
    except (ValueError, KeyError):
        return -1


def _status_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value).lower()
    name = getattr(value, "name", None)
    if name:
        return str(name).lower()
    return str(value).lower()
