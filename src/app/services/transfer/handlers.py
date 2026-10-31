"""转移领域事件处理器."""

import os
from typing import Any

import log
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.domain.entities.transfer_task import SourceType, TransferTask
from app.downloader.client_factory import DownloadClientFactory
from app.events import Event, on_event
from app.events.bus import EventBus
from app.events.constants import DOWNLOAD_COMPLETED, MEDIA_TRANSFER_FINISHED, SUBTITLE_DOWNLOAD, TRANSFER_FAIL
from app.events.payloads import (
    DownloadCompletedPayload,
    MediaTransferFinishedPayload,
    SubtitleDownloadPayload,
    TransferFailPayload,
)
from app.media.parser import RegexParser
from app.services.transfer_pipeline import TransferPipeline


@on_event(MEDIA_TRANSFER_FINISHED)
def handle_media_transfer_finished(event: Event) -> None:
    """媒体转移完成事件处理器"""
    payload = event.payload
    if not isinstance(payload, MediaTransferFinishedPayload):
        payload = MediaTransferFinishedPayload(**payload)
    log.info(f"[Event]媒体转移完成: {payload.dest}")


@on_event(SUBTITLE_DOWNLOAD)
def handle_subtitle_download(event: Event) -> None:
    """字幕下载事件处理器"""
    payload = event.payload
    if not isinstance(payload, SubtitleDownloadPayload):
        payload = SubtitleDownloadPayload(**payload)
    log.info(f"[Event]字幕下载请求: {payload.file}")


@on_event(TRANSFER_FAIL)
def handle_transfer_fail(event: Event) -> None:
    """转移失败事件处理器"""
    payload = event.payload
    if not isinstance(payload, TransferFailPayload):
        payload = TransferFailPayload(**payload)
    log.warn(f"[Event]转移失败: {payload.path} 原因: {payload.reason}")


def handle_download_completed(
    event: Event,
    download_client_factory: DownloadClientFactory | None = None,
    transfer_pipeline: TransferPipeline | None = None,
    download_history_repo: Any = None,
    media_cache: Any = None,
    sync_path_repo: Any = None,
) -> None:
    """下载完成事件处理器 — 触发文件转移."""
    payload = event.payload
    if not isinstance(payload, DownloadCompletedPayload):
        payload = DownloadCompletedPayload(**payload)
    try:
        client_factory = download_client_factory or DownloadClientFactory()
        downloader_conf = client_factory.get_downloader_conf(payload.downloader_id)
        if not downloader_conf:
            log.warn(f"[Event]下载器配置不存在: {payload.downloader_id}")
            return

        # 从下载历史中读取订阅时记录的 TMDB 信息，供转移/刮削直接使用
        tmdb_info = None
        media_type = ""
        season = None
        fallback_episode = None
        try:
            if download_history_repo:
                history = download_history_repo.get_by_downloader(payload.downloader_id, payload.task_id)
            else:
                history = DownloadHistoryRepositoryAdapter().get_by_downloader(payload.downloader_id, payload.task_id)
            if history and history.tmdb_id:
                tmdb_id = history.tmdb_id
                media_type = history.media_type or ""
                if media_cache:
                    tmdb_info = media_cache.get_tmdb_info(mtype=media_type, tmdbid=tmdb_id)
                if history.season_episode:
                    parsed = RegexParser().parse(str(history.season_episode))
                    if parsed:
                        if parsed.season:
                            season = parsed.season
                        if parsed.episode:
                            fallback_episode = parsed.episode
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Event]读取下载历史TMDB信息失败: {e}")

        if season is None and payload.name:
            parsed = RegexParser().parse(str(payload.name))
            if parsed and parsed.season:
                season = parsed.season

        name = downloader_conf.get("name", "")
        operation = str(downloader_conf.get("rmt_mode") or "")
        target_dir = None
        unknown_dir = None
        # 下载器完成事件也必须遵循同步目录配置，否则会按媒体类型
        # 落入默认媒体库，而不是同步配置指定的目标库。
        if sync_path_repo is not None:
            try:
                path_norm = os.path.normpath(str(payload.path))
                candidates = [
                    cfg
                    for cfg in sync_path_repo.get_all()
                    if getattr(cfg, "enabled", False)
                    and path_norm.startswith(os.path.normpath(str(cfg.source)).rstrip(os.sep) + os.sep)
                ]
                if candidates:
                    cfg = max(candidates, key=lambda c: len(str(c.source)))
                    target_dir = str(cfg.dest or "") or None
                    unknown_dir = str(cfg.unknown or "") or None
                    if cfg.operation:
                        operation = str(cfg.operation)
            except Exception as e:  # noqa: BLE001 - 配置解析失败仍可按默认路径转移
                log.debug(f"[Event]解析同步目录失败: {e}")
        client = client_factory.get_client(payload.downloader_id)

        def _post_process(task: TransferTask, success: bool, msg: str) -> None:
            if not success:
                log.warn(f"[Event]任务 {payload.task_id} 转移失败: {msg}")
                if client:
                    client.set_torrents_status(ids=payload.task_id, tags=payload.tags)
                return
            if operation == "move":
                log.info(f"[Event]移动模式下删除种子: {payload.task_id}")
                if client:
                    client.delete_torrents(delete_file=True, ids=payload.task_id)
            else:
                if client:
                    client.set_torrents_status(ids=payload.task_id, tags=payload.tags)

        if transfer_pipeline is None:
            raise RuntimeError("transfer_pipeline is required")
        task = TransferTask(
            source_type=SourceType.DOWNLOADER,
            source_id=name,
            file_paths=[payload.path],
            operation=operation,
            target_dir=target_dir,
            unknown_dir=unknown_dir,
            provider_data=tmdb_info,
            media_type=media_type,
            season=season,
            fallback_episode=fallback_episode,
            post_process=_post_process,
        )
        success, message = transfer_pipeline.process(task)
        if success:
            log.info(f"[Event]下载完成转移成功: {payload.path}")
        else:
            log.warn(f"[Event]下载完成转移失败: {payload.path} — {message}")
    except Exception as e:
        log.error(f"[Event]处理下载完成事件失败: {e!s}")


def register_download_completed_handler(
    event_bus: EventBus,
    transfer_pipeline: TransferPipeline,
    download_client_factory: DownloadClientFactory | None = None,
    download_history_repo: Any = None,
    media_cache: Any = None,
    sync_path_repo: Any = None,
) -> None:
    """注册下载完成事件处理器，外部显式注入依赖。"""

    def _handler(event: Event) -> None:
        handle_download_completed(
            event,
            download_client_factory=download_client_factory,
            transfer_pipeline=transfer_pipeline,
            download_history_repo=download_history_repo,
            media_cache=media_cache,
            sync_path_repo=sync_path_repo,
        )

    event_bus.subscribe(DOWNLOAD_COMPLETED, _handler)
