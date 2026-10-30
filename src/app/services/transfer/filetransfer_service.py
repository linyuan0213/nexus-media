"""FileTransferService - 文件转移业务 Facade.

保留与原 FileTransfer 兼容的公共 API，核心转移流程保留在 Facade 中，
路径解析、存在性检查、历史管理、清理逻辑委托给独立组件.
"""

import hashlib
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future, wait
from typing import Any

import log
from app.core.constants import RMT_MEDIAEXT, RMT_MIN_FILESIZE
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.subscribe_repository import SubscribeRepository
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.domain.enums import ProgressKey, SyncType
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.bus import EventBus
from app.events.constants import MEDIA_EPISODE_TRANSFERRED, MEDIA_TRANSFER_FINISHED, SUBTITLE_DOWNLOAD, TRANSFER_FAIL
from app.events.payloads import (
    MediaEpisodeTransferredPayload,
    MediaTransferFinishedPayload,
    SubtitleDownloadPayload,
    TransferFailPayload,
)
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.infrastructure.progress import ProgressTracker
from app.infrastructure.queue.memory_queue import MemoryMessageQueue
from app.infrastructure.thread import ThreadExecutor
from app.media import MediaService
from app.media import meta_info as meta_info_fn
from app.media.metadata.parsing import ParserChain
from app.media.metadata.refs import parse_media_ref
from app.media.metadata.registry import registry as metadata_registry
from app.media.parser import RegexParser
from app.message import Message
from app.schemas.media import TransferMediaDTO
from app.services.scrape_queue_service import ScrapeQueueService
from app.services.transfer.cleanup_service import TransferCleanupService
from app.services.transfer.existence_checker import MediaExistenceChecker
from app.services.transfer.history_manager import TransferHistoryManager
from app.services.transfer.library_rename_backend import target_dir_lock_key
from app.services.transfer.path_resolver import TransferPathResolver
from app.services.transfer_engine import TransferEngine
from app.utils import ExceptionUtils, PathUtils, StringUtils

# 多后端镜像上传：后端间写入间隔（秒），避免连续上传压垮后端
MIRROR_BACKEND_DELAY = 1.0

# 文件转移锁：短 TTL + 心跳续期，进程崩溃后最多遗留 3 分钟而不是 1 小时
TRANSFER_LOCK_TTL = 180
TRANSFER_LOCK_HEARTBEAT = 30

# 目录内常见的附加/广告视频（非正片），识别前先排除
_EXTRA_MEDIA_RE = re.compile(
    r"(?:^|[-_.\s\[\(])(?:sample|trailer|preview|teaser|广告|預告|预告)(?:$|[-_.\s\]\)])",
    re.IGNORECASE,
)

_mirror_queue: MemoryMessageQueue | None = None
_mirror_queue_lock = threading.Lock()


def _get_mirror_queue() -> MemoryMessageQueue:
    """镜像上传专用串行队列（单 worker，惰性单例）"""
    global _mirror_queue
    if _mirror_queue is None:
        with _mirror_queue_lock:
            if _mirror_queue is None:
                _mirror_queue = MemoryMessageQueue(max_workers=1, maxsize=1000)
                _mirror_queue.start()
    return _mirror_queue


# 并发转移分组等待上限（秒）；超时按失败处理，避免同池嵌套导致永久挂起
_PARALLEL_WAIT_TIMEOUT = 1800


class FileTransferService:
    """文件转移业务 Facade."""

    def __init__(
        self,
        media_service: MediaService,
        message: Message,
        scrape_queue_service: ScrapeQueueService,
        thread_executor: ThreadExecutor,
        history_manager: TransferHistoryManager,
        progress: ProgressTracker,
        event_bus: EventBus,
        engine: TransferEngine,
        sync_path_repo: SyncPathRepositoryAdapter,
        path_resolver: TransferPathResolver,
        existence_checker: MediaExistenceChecker,
        cleanup_service: TransferCleanupService,
        download_repo=None,
        subscribe_repo=None,
        metadata_service=None,
    ):
        self.media = media_service
        self.message = message
        self._scrape_queue_service = scrape_queue_service
        self._thread_executor = thread_executor
        self.progress = progress
        self._event_bus = event_bus
        self._engine = engine
        self._default_operation: str = "copy"
        self._min_filesize = RMT_MIN_FILESIZE
        self._filesize_cover = False
        self._ignored_paths: re.Pattern[str] | None = None
        self._ignored_files: re.Pattern[str] | None = None
        self._sync_repo = sync_path_repo

        self._path_resolver = path_resolver
        self._existence = existence_checker
        self._history = history_manager
        self._download_repo = download_repo or DownloadHistoryRepositoryAdapter()
        self._subscribe_repo = subscribe_repo or SubscribeRepository()
        self._cleanup = cleanup_service
        self._metadata_service = metadata_service

        # 从配置读取媒体处理参数
        media = settings.get("media")
        if media:
            min_filesize = media.get("min_filesize")
            if isinstance(min_filesize, int):
                self._min_filesize = min_filesize * 1024 * 1024
            elif isinstance(min_filesize, str) and min_filesize.isdigit():
                self._min_filesize = int(min_filesize) * 1024 * 1024
            ignored_paths = media.get("ignored_paths")
            if ignored_paths:
                ignored_paths = ignored_paths.removesuffix(";")
                self._ignored_paths = re.compile(r"{}".format(re.sub(r";", r"|", ignored_paths)))
            ignored_files = media.get("ignored_files")
            if ignored_files:
                ignored_files = ignored_files.removesuffix(";")
                self._ignored_files = re.compile(r"{}".format(re.sub(r";", r"|", ignored_files)))
            self._filesize_cover = media.get("filesize_cover")

        self._default_operation = (settings.get("pt") or {}).get("rmt_mode", "copy") or "copy"

    # ---------- 路径相关委托方法（公共 API 兼容） ----------

    def _apply_subscription_hint(self, media) -> None:
        """转移前复用订阅记录里的海报与画像，避免通知/历史丢图."""
        if media is None or self._subscribe_repo is None:
            return
        media_type = getattr(media, "type", None)
        type_value = str(getattr(media_type, "value", media_type) or "").lower()
        if type_value and type_value != MediaType.MOVIE.value:
            return
        provider = str(getattr(media, "anchor_provider", "") or "")
        external = str(getattr(media, "anchor_external_id", "") or "")
        keyword = str(getattr(media, "keyword", "") or getattr(media, "title", "") or "").strip()
        try:
            hint = self._subscribe_repo.get_movie_subscription_hint(
                provider,
                external,
                keyword,
                identity_id=getattr(media, "identity_id", None),
            )
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Rmt]订阅海报提示查询失败: {e}")
            return
        if not hint:
            return
        if not str(getattr(media, "poster_path", "") or "") and hint.get("image"):
            media.poster_path = hint["image"]
        if (
            not str(getattr(media, "content_profile", "") or "")
            or str(getattr(media, "content_profile", "")) == "default"
        ) and hint.get("content_profile"):
            media.content_profile = hint["content_profile"]
        if not getattr(media, "anchor_provider", None) and hint.get("anchor_provider"):
            media.anchor_provider = hint["anchor_provider"]
        if not getattr(media, "anchor_external_id", None) and hint.get("anchor_external_id"):
            media.anchor_external_id = hint["anchor_external_id"]
        if hint.get("metadata_ref") and not getattr(media, "provider_data", None):
            media.provider_data = {"metadata_ref": hint["metadata_ref"]}

    def _resolve_owner_user_id(self, path: str | None, media=None) -> int | None:
        """解析入库事件的归属用户（转移通知定向用）。

        优先按源路径查下载历史；历史被清理后回退按订阅（TMDB+季/电影 TMDB）反查，
        避免用户级入库消息退化为系统级广播。
        """
        if path and self._download_repo is not None:
            try:
                row = self._download_repo.get_download_history_by_path(path)
                if row is not None and row.USER_ID is not None:
                    return int(row.USER_ID)
            except Exception:  # noqa: BLE001
                log.debug("[FileTransfer]按路径解析归属失败，回退订阅反查")
        if media is None or self._subscribe_repo is None:
            return None
        try:
            tmdb_id = str(getattr(media, "tmdb_id", "") or "")
            if tmdb_id:
                if getattr(media, "type", None) == MediaType.MOVIE:
                    return self._subscribe_repo.find_movie_owner_user_id(tmdb_id)
                season = media.get_season_string() if hasattr(media, "get_season_string") else None
                return self._subscribe_repo.find_tv_owner_user_id(tmdb_id, season)
            provider = str(getattr(media, "anchor_provider", "") or "")
            external = str(getattr(media, "anchor_external_id", "") or "")
            if provider and external:
                return self._subscribe_repo.find_owner_by_anchor(
                    provider, external, getattr(media, "type", None) or MediaType.MOVIE
                )
            return None
        except Exception:  # noqa: BLE001
            log.debug("[FileTransfer]按订阅解析归属失败")
            return None

    def is_target_dir_path(self, path):
        return self._path_resolver.is_target_dir_path(path)

    def get_dest_path_by_info(self, dest, meta_info):
        return self._path_resolver.get_dest_path_by_info(dest, meta_info, self.media)

    def get_no_exists_medias(self, meta_info, season=None, total_num=None):
        # 先查转移历史 DB：已转移过的剧集视为已存在
        # 仅信任源路径仍存在的历史记录（调试/测试残留的假记录源已删除，不参与判断）
        if meta_info.type != MediaType.MOVIE and meta_info.tmdb_id and season and total_num:
            try:
                match = re.search(r"\d+", str(season))
                season_num = int(match.group()) if match else int(season)
                season_str = f"S{season_num:02d}"
                history = self._history.get_transfer_info_by(tmdbid=meta_info.tmdb_id, season=season_str)
                transferred: set[int] = set()
                if history:
                    for h in history:
                        if not getattr(h, "source_path", "") or not os.path.exists(str(getattr(h, "source_path", ""))):
                            continue
                        # 目标硬链接/文件必须实际存在，否则视为缺失（如目标被删除）→ 触发重新硬链接
                        backend = getattr(h, "dst_backend", None) or "local"
                        if not self._history_dest_exists(h, backend):
                            continue
                        se = h.season_episode or ""
                        parts = [part.strip() for part in se.replace("S", "").split("E")]
                        if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) == season_num:
                            ep = parts[1]
                            if "-" in ep:
                                a, b = ep.split("-")
                                transferred.update(range(int(a), int(b) + 1))
                            elif ep.isdigit():
                                transferred.add(int(ep))
                if transferred:
                    all_episodes = set(range(1, total_num + 1))
                    return list(all_episodes - transferred)
            except Exception:
                log.debug("[FileTransfer]历史查询失败，回退文件扫码")

        # 回退：文件系统扫码
        return self._existence.get_no_exists_medias(meta_info, meta_info_fn, season, total_num)

    def get_best_target_path(self, mtype, in_path=None, size=0):
        return self._path_resolver.get_best_target_path(mtype, in_path, size)

    def get_moive_dest_path(self, media_info):
        return self._path_resolver.get_movie_dest_path(media_info, self.media)

    def get_tv_dest_path(self, media_info):
        return self._path_resolver.get_tv_dest_path(media_info, self.media)

    # ---------- 历史记录委托方法（公共 API 兼容） ----------

    def get_transfer_info_by(self, tmdbid, season=None, season_episode=None):
        return self._history.get_transfer_info_by(tmdbid, season, season_episode)

    def get_transfer_info_by_path(self, dest_path, filename=None):
        return self._history.get_transfer_info_by_path(dest_path, filename)

    def get_transfer_info_by_id(self, logid):
        return self._history.get_transfer_info_by_id(logid)

    def get_transfer_history(self, search, page, rownum, media_type=None):
        return self._history.get_transfer_history(search, page, rownum, media_type)

    def update_transfer_history_poster(self, logid: int | None, poster: str) -> None:
        return self._history.update_transfer_history_poster(logid=logid, poster=poster)

    def delete_transfer_log_by_id(self, logid):
        return self._history.delete_transfer_log_by_id(logid)

    def delete_transfer_logs(self, logids: list[int]) -> None:
        return self._history.delete_transfer_logs(logids)

    def delete_transfer(self):
        return self._history.delete_transfer()

    def delete_transfer_unknown(self, tid):
        return self._history.delete_transfer_unknown(tid)

    def delete_transfer_unknowns(self, tids: list[int]) -> None:
        return self._history.delete_transfer_unknowns(tids)

    def get_unknown_info_by_id(self, tid):
        return self._history.get_unknown_info_by_id(tid)

    def update_transfer_unknown_state(self, path):
        return self._history.update_transfer_unknown_state(path)

    def delete_transfer_blacklist(self, path):
        return self._history.delete_transfer_blacklist(path)

    def truncate_transfer_blacklist(self):
        return self._history.truncate_transfer_blacklist()

    def get_transfer_statistics(self, days=30):
        return self._history.get_transfer_statistics(days)

    def get_transfer_series_statistics(self, days=30):
        return self._history.get_transfer_series_statistics(days)

    def get_transfer_unknown_paths(self):
        return self._history.get_transfer_unknown_paths()

    def get_transfer_unknown_paths_by_page(self, search, page, rownum):
        return self._history.get_transfer_unknown_paths_by_page(search, page, rownum)

    # ---------- 清理服务委托方法 ----------

    def delete_history(self, logids, flag=None):
        lock_key = f"transfer:delete:{hashlib.md5(str(logids).encode(), usedforsecurity=False).hexdigest()}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            log.info("[Rmt]删除历史任务正在执行，跳过")
            return None
        try:
            return self._cleanup.delete_history(logids, flag)
        finally:
            lock.release()

    def delete_records(self, logids: list[int]) -> list[dict]:
        lock_key = f"transfer:delete-records:{hashlib.md5(str(logids).encode(), usedforsecurity=False).hexdigest()}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        if not lock.acquire():
            return [{"id": int(logid), "status": "failed", "message": "删除任务正在执行"} for logid in logids]
        try:
            return self._cleanup.delete_records(logids)
        finally:
            lock.release()

    def delete_record_files(self, logids: list[int], targets: list[str]) -> list[dict]:
        lock_key = f"transfer:delete-files:{hashlib.md5(str(logids).encode(), usedforsecurity=False).hexdigest()}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        if not lock.acquire():
            return [
                {"id": int(logid), "target": target, "status": "failed", "message": "删除任务正在执行"}
                for logid in logids
                for target in targets
            ]
        try:
            return self._cleanup.delete_record_files(logids, targets)
        finally:
            lock.release()

    def check_record_files(self, logids: list[int], targets: list[str] | None = None) -> list[dict]:
        return self._cleanup.check_record_files(logids, targets)

    def delete_media_file(self, filedir, filename, backend_id="local"):
        return self._cleanup.delete_media_file(filedir, filename, backend_id)

    # ---------- 过滤与工具方法 ----------

    def check_ignore(self, file_list):
        """检查过滤文件列表中忽略项目."""
        if not file_list:
            return [], ""
        ignored_paths = self._ignored_paths
        if ignored_paths:
            try:
                file_list = [f for f in file_list if not re.findall(ignored_paths, os.path.dirname(f))]
                if not file_list:
                    return [], "排除文件路径转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"[Rmt]文件路径转移忽略词设置有误：{err!s}")

        ignored_files = self._ignored_files
        if ignored_files:
            try:
                file_list = [f for f in file_list if not re.findall(ignored_files, os.path.basename(f))]
                if not file_list:
                    return [], "排除文件名转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"[Rmt]文件名转移忽略词设置有误：{err!s}")

        return file_list, ""

    def link_sync_file(self, src_path, in_file, target_dir, operation):
        """对文件做纯链接处理，不做识别重命名（监控模块调用）."""
        rel = os.path.relpath(in_file, src_path)
        if rel.startswith(".."):
            rel = os.path.basename(in_file)
        new_file = os.path.join(target_dir, rel)
        new_file_list, msg = self.check_ignore(file_list=[new_file])
        if not new_file_list:
            return 0, msg
        else:
            new_file = new_file_list[0]
        new_dir = os.path.dirname(new_file)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir, exist_ok=True)
        try:
            self._engine._execute(in_file, new_file, operation)
            return 0, ""
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            log.error(f"[Rmt]link_sync_file 失败：{e}")
            return 1, str(e)

    # ---------- 核心转移流程（保留在 Facade） ----------

    @staticmethod
    def _start_lock_heartbeat(
        lock,
        ttl_seconds: int = TRANSFER_LOCK_TTL,
        interval: float = TRANSFER_LOCK_HEARTBEAT,
    ) -> threading.Thread:
        """后台续期转移锁；进程崩溃后停止续期，锁在 TTL 后自动释放."""

        def _beat() -> None:
            while lock.owned:
                time.sleep(interval)
                if not lock.owned or not lock.extend(ttl_seconds):
                    return

        thread = threading.Thread(target=_beat, daemon=True, name="filetransfer-lock-heartbeat")
        thread.start()
        return thread

    def transfer_media(
        self,
        in_from,
        in_path,
        operation=None,
        files=None,
        target_dir=None,
        unknown_dir=None,
        provider_data=None,
        media_type=None,
        season=None,
        episode=None,
        min_filesize=None,
        udf_flag=False,
        root_path=False,
        src_backend=None,
        dst_backend=None,
        fallback_episode=None,
    ) -> tuple[bool, str]:
        """识别并转移一个文件、多个文件或者目录."""
        if not in_path or not (src_backend.exists(in_path) if src_backend is not None else os.path.exists(in_path)):
            return self._finish_transfer(False, f"文件转移失败，目录或文件不存在：{in_path}")

        # 分布式锁：多实例同时处理同一文件/目录时互斥
        lock_key = f"filetransfer:media:{hashlib.md5(in_path.encode(), usedforsecurity=False).hexdigest()}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=TRANSFER_LOCK_TTL)
        acquired = lock.acquire()
        if not acquired:
            log.info(f"[Rmt]{in_path} 正在其他实例转移中，跳过")
            return self._finish_transfer(False, f"文件正在转移中：{in_path}")

        self._start_lock_heartbeat(lock)

        with lock:
            if not operation:
                operation = self._default_operation

            self.progress.start(ProgressKey.FileTransfer)
            assert operation is not None
            log.info(f"[Rmt]开始处理：{in_path}，转移方式：{operation}")

            # 刷新路径解析配置（媒体库路径变更后无需重启即可生效）
            self._path_resolver.refresh()

            episode = episode if episode else (None, False)

            # ---------- 阶段 1：发现文件 ----------
            bluray_disk_dir, file_list = self._discover_files(in_path, files, episode, min_filesize, src_backend)
            if file_list is None:
                return self._finish_transfer(False, "输入路径错误")
            if not file_list:
                return self._finish_transfer(
                    bluray_disk_dir is not None, "目录下未找到媒体文件" if bluray_disk_dir is None else ""
                )

            # ---------- 阶段 2：过滤 ----------
            file_list, msg = self.check_ignore(file_list=file_list)
            if not file_list:
                return self._finish_transfer(True, msg)

            if in_from == SyncType.MON:
                file_list = list(filter(self._history.is_transfer_notin_blacklist, file_list))
                if not file_list:
                    log.debug("[Rmt]所有文件均已成功转移过")
                    return self._finish_transfer(True, "没有新文件需要处理")

            # ---------- 阶段 3：查下载记录 + 批量识别 ----------
            dl_season = None
            dl_episode = None
            if not provider_data:
                provider_data, media_type, dl_season, dl_episode = self._lookup_download_record(in_path)

            # 先用插件 ParserProfile 短路识别，避免已识别文件再走一次 TMDB。
            policy = str((settings.get("media") or {}).get("metadata_default_policy") or "tmdb_primary")
            parser_chain = ParserChain()
            profile_medias = {}
            unprofiled_files = []
            primary_medias = {}
            for _path in file_list:
                parsed_profile = None
                try:
                    parsed_profile = parser_chain.extract(os.path.basename(_path))
                except Exception:
                    parsed_profile = None
                if parsed_profile is None or not getattr(parsed_profile, "content_profile", None):
                    # 普通媒体：非 TMDB 主源先按策略识别，命中则完全跳过 TMDB。
                    if self._metadata_service is not None and not policy.startswith("tmdb_"):
                        try:
                            candidate = meta_info_fn(os.path.basename(_path))
                            if self._metadata_service.identify_anchor(candidate, policy=policy):
                                primary_medias[_path] = candidate
                                continue
                        except Exception as exc:  # noqa: BLE001
                            log.debug(f"[Rmt]主源预识别失败: {exc}")
                    unprofiled_files.append(_path)
                    continue
                parsed_code = getattr(parsed_profile, "anchor_external_id", "") or getattr(
                    parsed_profile, "content_id", ""
                )
                _info = meta_info_fn(
                    str(parsed_code or os.path.splitext(os.path.basename(_path))[0]),
                    mtype=getattr(parsed_profile, "type", None) or MediaType.MOVIE,
                )
                _info.org_string = os.path.basename(_path)
                _info.content_profile = parsed_profile.content_profile
                _info.anchor_provider = getattr(parsed_profile, "anchor_provider", "") or ""
                _info.anchor_external_id = str(parsed_code or "")
                if parsed_code:
                    _info.title = str(parsed_code)
                profile_medias[_path] = _info

            medias = {**primary_medias, **profile_medias}
            if unprofiled_files:
                identified = self.media.get_media_info_on_files(
                    unprofiled_files,
                    provider_data,
                    media_type,
                    season,
                    episode[0],
                    backend=src_backend,
                )
                if identified:
                    medias.update(identified)
            if not medias:
                return self._finish_transfer(False, "搜索媒体信息出错")

            for _info in medias.values():
                self._apply_subscription_hint(_info)
            for _path, _info in medias.items():
                if not getattr(_info, "org_string", ""):
                    _info.org_string = os.path.basename(_path)
                if not getattr(_info, "title", ""):
                    _info.title = os.path.splitext(os.path.basename(_path))[0]
                if self._metadata_service is not None:
                    started = time.perf_counter()
                    try:
                        self._metadata_service.identify_anchor(_info, policy=policy)
                        _snapshot = self._metadata_service.compose_for_media(
                            _info,
                            policy=policy,
                            with_episodes=True,
                            persist=True,
                            max_age_seconds=1800,
                        )
                        if _snapshot is not None:
                            _info.snapshot = _snapshot
                            self._apply_snapshot_to_media(_info, _snapshot)
                        log.debug(f"[Rmt]元数据合成完成 {_info.title}：{time.perf_counter() - started:.2f}s")
                    except Exception as exc:  # noqa: BLE001
                        log.debug(f"[Rmt]主源识别失败: {exc}")

            # 订阅/下载历史已知季集时兜底：文件名解析失败的动漫单集用订阅记录的集号补齐，
            # 避免"无法从文件名中识别出集数"导致订阅下载的剧集无法入库
            fallback_season = season if season is not None else dl_season
            fallback_ep = fallback_episode if fallback_episode is not None else dl_episode
            if fallback_season is not None or fallback_ep is not None:
                for _path, _info in medias.items():
                    if fallback_season is not None and _info.begin_season is None and _info.type != MediaType.MOVIE:
                        _info.begin_season = fallback_season
                    if fallback_ep is not None and _info.begin_episode is None:
                        _info.begin_episode = fallback_ep
                log.info(f"[Rmt]按订阅/下载记录补齐季集: S{fallback_season or '-'}E{fallback_ep or '-'}")

            self.progress.update(ptype=ProgressKey.FileTransfer, text=f"共 {len(medias)} 个文件需要处理...")

            # ---------- 阶段 4：逐个文件转移 ----------
            result = self._transfer_files_loop(
                medias,
                in_from,
                in_path,
                operation,
                target_dir,
                unknown_dir,
                bluray_disk_dir,
                episode,
                udf_flag,
                src_backend,
                dst_backend,
            )

            # ---------- 阶段 5：后处理 ----------
            return self._transfer_post_process(result, in_from, in_path, operation, root_path)

    # ---------- 转移流水线私有方法 ----------

    def _finish_transfer(self, status, message):
        self.progress.update(
            ptype=ProgressKey.FileTransfer, value=100, text=f"转移{'成功' if status else '失败'}：{message}！"
        )
        self.progress.end(ProgressKey.FileTransfer)
        return status, message

    def _get_bluray_dir(self, in_path: str, src_backend=None) -> str | None:
        """识别蓝光原盘根目录，支持本地与远程源（后端感知）"""
        if src_backend is None:
            return PathUtils.get_bluray_dir(in_path)
        norm = os.path.normpath(in_path).replace("\\", "/")
        exists = src_backend.exists
        try:
            if exists(f"{norm}/BDMV/index.bdmv"):
                return norm
            if norm.endswith("BDMV") and exists(f"{norm}/index.bdmv"):
                return os.path.dirname(norm)
            if norm.endswith("STREAM") and exists(f"{os.path.dirname(norm)}/index.bdmv"):
                return PathUtils.get_parent_paths(norm, 2)
            # 多碟：一级子目录含 BDMV/index.bdmv（如 剧名/Disc1/BDMV）
            for fi in src_backend.list_dir(norm):
                if fi.is_dir and exists(f"{fi.path.rstrip('/')}/BDMV/index.bdmv"):
                    return norm
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Rmt]蓝光目录检测失败: {e}")
        return None

    @staticmethod
    def _is_virtual_provider(provider: str) -> bool:
        desc = getattr(metadata_registry.get_provider(provider), "descriptor", None)
        return bool(getattr(desc, "virtual", False)) or provider == "content_id"

    def _apply_snapshot_to_media(self, media_info, snapshot) -> None:
        """把快照结果回填到 MediaInfo，供转移通知与命名使用."""

        def _record_poster(record):
            if not record:
                return []
            images = record.get("images") if isinstance(record, dict) else getattr(record, "images", {})
            return (images or {}).get("poster") or []

        def _poster_value(asset, key, default=None):
            if isinstance(asset, dict):
                return asset.get(key, default)
            return getattr(asset, key, default)

        fields = getattr(snapshot, "fields", {}) or {}
        snapshot_profile = str(getattr(snapshot, "content_profile", "") or "")
        if snapshot_profile and (
            not str(getattr(media_info, "content_profile", "") or "")
            or str(getattr(media_info, "content_profile", "")) == "default"
        ):
            media_info.content_profile = snapshot_profile
        for key in ("title", "year"):
            value = fields.get(key)
            value = getattr(value, "value", value)
            if value:
                setattr(media_info, key, value)
        images = getattr(snapshot, "images", {}) or {}
        poster = images.get("poster") or []
        extra = getattr(snapshot, "extra", {}) or {}
        source = extra.get("source_provider") or next(
            (value for key, value in extra.items() if str(key).endswith(".source_provider")),
            None,
        )
        if not poster and self._metadata_service is not None:
            # 部分插件快照只带字段，图片在单独 lookup 中；用 refs 找一张真实海报。
            for ref in getattr(snapshot, "refs", []) or []:
                provider = str(getattr(ref, "provider", "") or "")
                external_id = str(getattr(ref, "external_id", "") or "")
                if (
                    not provider
                    or not external_id
                    or self._is_virtual_provider(provider)
                    or provider in {"tmdb", "imdb"}
                ):
                    continue
                try:
                    record = self._metadata_service.lookup(
                        provider=provider,
                        external_id=external_id,
                        media_type=getattr(snapshot, "media_type", None),
                        scope=str(getattr(media_info, "content_profile", "") or "default"),
                        content_profile=str(getattr(media_info, "content_profile", "") or ""),
                        allow_private=True,
                    )
                    poster = _record_poster(record)
                    if poster:
                        source = _poster_value(poster[0], "provider") or provider
                        break
                except Exception:
                    continue
        if not poster and self._metadata_service is not None:
            source_ref = str(
                extra.get("source_ref")
                or next(
                    (value for key, value in extra.items() if str(key).endswith(".source_ref")),
                    "",
                )
            )
            if not source_ref:
                primary = str(getattr(snapshot, "primary_provider", "") or "")
                external = str(getattr(media_info, "anchor_external_id", "") or "")
                if primary and external:
                    source_ref = f"{primary}:{external}"
            if ":" in source_ref:
                lookup_provider, lookup_external = source_ref.split(":", 1)
                try:
                    record = self._metadata_service.lookup(
                        provider=lookup_provider,
                        external_id=lookup_external,
                        media_type=getattr(snapshot, "media_type", None) or getattr(media_info, "type", None),
                        scope=str(getattr(media_info, "content_profile", "") or "default"),
                        content_profile=str(getattr(media_info, "content_profile", "") or ""),
                    )
                    poster = _record_poster(record)
                    if poster:
                        source = _poster_value(poster[0], "provider") or source
                except Exception as exc:  # noqa: BLE001
                    log.debug(f"[Rmt]主来源海报补全失败: {exc}")
        if poster:
            media_info.poster_path = _poster_value(poster[0], "url") or str(poster[0])
        if not poster:
            # 没有竖版海报时用插件快照的横版剧照，至少不要推 TMDB 占位图。
            for kind in ("fanart", "backdrop"):
                assets = images.get(kind) or []
                if not assets:
                    continue
                image_url = _poster_value(assets[0], "url") or str(assets[0])
                if image_url:
                    media_info.fanart_backdrop = image_url
                    media_info.fanart_poster = image_url
                    break
        if (not source or self._is_virtual_provider(str(source))) and poster:
            source = _poster_value(poster[0], "provider")
        if not source or self._is_virtual_provider(str(source)):
            for ref in getattr(snapshot, "refs", []) or []:
                provider = str(getattr(ref, "provider", "") or "")
                if provider and not self._is_virtual_provider(provider):
                    source = provider
                    break
        if source:
            media_info.anchor_provider = str(source)
        elif getattr(snapshot, "primary_provider", ""):
            media_info.anchor_provider = str(snapshot.primary_provider)

    def _discover_files(self, in_path, files, episode, min_filesize, src_backend=None):
        """发现待处理文件列表，返回 (bluray_disk_dir, file_list). 支持远程源（src_backend 非空）。"""
        bluray_disk_dir = None
        if not files:
            if src_backend is None and os.path.isdir(in_path) and PathUtils.is_incomplete_media_dir(in_path):
                log.info(f"[Rmt]{in_path} 下载未完成，跳过")
                return None, []
            if src_backend is not None:
                # 远程源：先判断是否蓝光原盘（整个盘作为一个媒体）
                bluray_disk_dir = self._get_bluray_dir(in_path, src_backend)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info(f"[Rmt]当前为蓝光原盘文件夹：{in_path!s}")
                    return bluray_disk_dir, file_list
                # 非蓝光：后端目录列举（文件名即媒体标识，无需下载）
                src_stat = src_backend.stat(in_path)
                is_dir = src_stat is not None and src_stat.is_dir
                if is_dir:
                    if os.path.splitext(os.path.normpath(in_path).rstrip(os.sep))[-1].lower() in RMT_MEDIAEXT:
                        log.info(f"[Rmt]{in_path} 为下载未完成目录，跳过")
                        return None, []
                    now_filesize = self._resolve_discovery_filesize(min_filesize)
                    file_list = self._filter_obvious_extras(
                        self._list_backend_media_files(src_backend, in_path, RMT_MEDIAEXT, now_filesize)
                    )
                    if not file_list:
                        log.warn(
                            f"[Rmt]{in_path} 目录下未找到媒体文件，"
                            f"最小文件大小限制为 {StringUtils.str_filesize(now_filesize)}"
                        )
                else:
                    if os.path.splitext(in_path)[-1].lower() not in RMT_MEDIAEXT:
                        log.warn(f"[Rmt]不支持的媒体文件格式，不处理：{in_path}")
                        return None, []
                    size = getattr(src_stat, "size", 0) or 0
                    if size and size < self._resolve_discovery_filesize(min_filesize):
                        log.info(f"[Rmt]{in_path} 小于最小文件大小限制，跳过")
                        return None, []
                    file_list = [in_path]
            elif os.path.isdir(in_path):
                if PathUtils.is_invalid_path(in_path):
                    return None, None
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info(f"[Rmt]当前为蓝光原盘文件夹：{in_path!s}")
                else:
                    now_filesize = self._resolve_discovery_filesize(min_filesize)
                    file_list = self._filter_obvious_extras(
                        PathUtils.get_dir_files(
                            in_path=in_path, episode_format=episode[0], exts=RMT_MEDIAEXT, filesize=now_filesize
                        )
                    )
                    if not file_list:
                        log.warn(
                            f"[Rmt]{in_path} 目录下未找到媒体文件，"
                            f"最小文件大小限制为 {StringUtils.str_filesize(now_filesize)}"
                        )
            else:
                if os.path.splitext(in_path)[-1].lower() not in RMT_MEDIAEXT:
                    log.warn(f"[Rmt]不支持的媒体文件格式，不处理：{in_path}")
                    return None, []
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                else:
                    try:
                        if os.path.getsize(in_path) < self._resolve_discovery_filesize(min_filesize):
                            log.info(f"[Rmt]{in_path} 小于最小文件大小限制，跳过")
                            return None, []
                    except OSError:
                        return None, []
                    file_list = [in_path]
        else:
            file_list = self._filter_explicit_files(files, min_filesize, src_backend)
        return bluray_disk_dir, file_list

    def _filter_explicit_files(self, files, min_filesize, src_backend=None) -> list[str]:
        """显式文件列表同样执行下载完整性/最小大小校验，避免广告文件进入识别."""
        if not files:
            return []
        size_limit = self._resolve_discovery_filesize(min_filesize)
        kept: list[str] = []
        for path in files:
            if not path:
                continue
            if src_backend is None:
                if os.path.isdir(path):
                    if PathUtils.is_incomplete_media_dir(path):
                        log.info(f"[Rmt]{path} 下载未完成，跳过")
                        continue
                    kept.append(path)
                    continue
                if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT:
                    try:
                        if os.path.getsize(path) < size_limit:
                            log.info(f"[Rmt]{path} 小于最小文件大小限制，跳过")
                            continue
                    except OSError:
                        continue
                kept.append(path)
                continue
            stat = src_backend.stat(path)
            is_dir = stat is not None and stat.is_dir
            if is_dir:
                ext = os.path.splitext(os.path.normpath(path).rstrip(os.sep))[-1].lower()
                if RMT_MEDIAEXT and ext in RMT_MEDIAEXT:
                    log.info(f"[Rmt]{path} 为下载未完成目录，跳过")
                    continue
                kept.append(path)
                continue
            if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT:
                size = getattr(stat, "size", 0) or 0
                if size and size < size_limit:
                    log.info(f"[Rmt]{path} 小于最小文件大小限制，跳过")
                    continue
            kept.append(path)
        return kept

    def _resolve_discovery_filesize(self, min_filesize) -> int:
        """解析本次转移的最小文件大小（MB 配置 → 字节）."""
        if min_filesize is None:
            return self._min_filesize
        return PathUtils.resolve_min_filesize(min_filesize, default_bytes=self._min_filesize)

    @staticmethod
    def _filter_obvious_extras(file_list: list[str]) -> list[str]:
        """多文件目录中排除 Sample/Trailer 等附加视频，避免它们被当作正片."""
        if len(file_list) <= 1:
            return file_list
        kept = [path for path in file_list if not _EXTRA_MEDIA_RE.search(os.path.basename(path))]
        return kept or file_list

    def _list_backend_media_files(self, backend, dir_path: str, exts, min_size: int) -> list[str]:
        """递归列举后端目录下的媒体文件（按扩展名与最小大小过滤）"""
        files: list[str] = []
        try:
            stack = [dir_path]
            while stack:
                current = stack.pop()
                for finfo in backend.list_dir(current):
                    if finfo.is_dir:
                        stack.append(finfo.path)
                        continue
                    ext = os.path.splitext(finfo.path)[1].lower()
                    if exts and ext not in exts:
                        continue
                    if min_size and finfo.size and finfo.size < min_size:
                        continue
                    files.append(finfo.path)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Rmt]后端目录递归列举失败: {e}")
        return files

    def _pick_record_by_filename(self, in_path, records):
        """聚合目录命中多条下载记录时，按文件名与记录的 TORRENT/TITLE 相似度消歧，唯一最佳才采用。"""
        file_name = os.path.basename(in_path)
        scored = []
        for rec in records or []:
            torrent = getattr(rec, "TORRENT", None) or getattr(rec, "torrent", "") or ""
            title = getattr(rec, "TITLE", None) or getattr(rec, "title", "") or ""
            score = max(StringUtils.similarity(file_name, torrent), StringUtils.similarity(file_name, title))
            scored.append((score, rec))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_rec = scored[0]
        if best_score < 0.35:
            return None
        # 歧义只在“不同 TMDBID”之间比较：同一部剧的多条记录（如同一剧的 E01/E02）不算歧义
        best_tmdb = str(getattr(best_rec, "TMDBID", "") or "")
        second_distinct = 0.0
        for score, rec in scored[1:]:
            if str(getattr(rec, "TMDBID", "") or "") != best_tmdb:
                second_distinct = score
                break
        if second_distinct and (best_score - second_distinct) < 0.05:
            return None
        return best_rec

    def _lookup_download_record(self, in_path):
        download_info = self._history.download_repo.get_download_history_by_path(in_path)
        if download_info and os.path.isdir(in_path):
            # 目录路径命中多条下载记录（聚合目录）：若都指向同一部剧则用其 tmdb 提示，
            # 否则按文件名消歧，仍无法唯一确定才跳过，避免错误套用
            count = self._history.download_repo.count_download_history_by_path(in_path)
            if count and count > 1:
                records = self._history.download_repo.get_download_history_list_by_path(in_path) or []
                tmdb_ids = {str(r.TMDBID) for r in records if getattr(r, "TMDBID", None)}
                if records and len(tmdb_ids) == 1:
                    download_info = records[0]
                else:
                    download_info = self._pick_record_by_filename(in_path, records)
                    if download_info is None:
                        log.debug(f"[Rmt]{in_path} 命中 {count} 条下载记录，聚合目录且无法按文件名消歧，跳过")
                        return None, None, None, None
        if not download_info and os.path.isfile(in_path):
            parent = os.path.dirname(in_path)
            # 文件回退父目录时，父目录若是聚合目录（多条下载记录），按文件名消歧；无法唯一确定才跳过
            parent_count = self._history.download_repo.count_download_history_by_path(parent)
            if parent_count and parent_count > 1:
                records = self._history.download_repo.get_download_history_list_by_path(parent) or []
                tmdb_ids = {str(r.TMDBID) for r in records if getattr(r, "TMDBID", None)}
                if records and len(tmdb_ids) == 1:
                    download_info = records[0]
                else:
                    download_info = self._pick_record_by_filename(in_path, records)
                    if download_info is None:
                        log.debug(
                            f"[Rmt]{in_path} 父目录 {parent} 命中 {parent_count} 条下载记录，无法按文件名消歧，跳过"
                        )
                        return None, None, None, None
            else:
                download_info = self._history.download_repo.get_download_history_by_path(parent)
        if download_info and str(download_info.TMDBID or ""):
            log.info(f"[Rmt]{in_path} 找到下载记录，TMDBID：{download_info.TMDBID}")
            parsed_type = MediaType.from_string(download_info.TYPE)
            media_type = parsed_type
            dl_season, dl_episode = None, None
            se = getattr(download_info, "SE", "") or ""
            if se:
                se_parsed = RegexParser().parse(str(se))
                if se_parsed:
                    dl_season = se_parsed.season
                    dl_episode = se_parsed.episode
            return (
                self.media.get_tmdb_info(mtype=media_type, tmdbid=download_info.TMDBID),
                media_type,
                dl_season,
                dl_episode,
            )
        return None, None, None, None

    def _transfer_files(
        self,
        medias,
        in_from,
        in_path,
        operation,
        target_dir,
        unknown_dir,
        bluray_disk_dir,
        episode,
        udf_flag,
        src_backend,
        dst_backend,
    ):
        """按目标目录分组并发转移，同一目录内串行避免重命名冲突."""
        if bluray_disk_dir or len(medias) <= 1 or self._thread_executor is None:
            return self._transfer_files_loop(
                medias,
                in_from,
                in_path,
                operation,
                target_dir,
                unknown_dir,
                bluray_disk_dir,
                episode,
                udf_flag,
                src_backend,
                dst_backend,
            )

        groups = defaultdict(dict)
        for file_item, media in medias.items():
            dist_path = target_dir or self._path_resolver.get_best_target_path(
                mtype=media.type,
                in_path=in_path,
                size=getattr(media, "size", 0),
                media=media,
                media_service=self.media,
            )
            if not dist_path:
                dist_path = ""
            groups[dist_path][file_item] = media

        def _transfer_group(group_medias: dict) -> dict:
            return self._transfer_files_loop(
                group_medias,
                in_from,
                in_path,
                operation,
                target_dir,
                unknown_dir,
                bluray_disk_dir,
                episode,
                udf_flag,
                src_backend,
                dst_backend,
            )

        results = self._run_parallel(list(groups.values()), _transfer_group)
        return self._merge_transfer_results([r for r in results if r is not None])

    def _merge_transfer_results(self, results: list[dict]) -> dict:
        """合并多组文件转移结果."""
        merged = {
            "total_count": 0,
            "failed_count": 0,
            "alert_count": 0,
            "alert_messages": [],
            "message_medias": {},
            "success_flag": True,
            "error_message": "",
            "exist_filenum": 0,
        }
        seen_messages = set()
        for result in results:
            merged["total_count"] += result.get("total_count", 0)
            merged["failed_count"] += result.get("failed_count", 0)
            merged["alert_count"] += result.get("alert_count", 0)
            for msg in result.get("alert_messages", []):
                if msg not in seen_messages:
                    seen_messages.add(msg)
                    merged["alert_messages"].append(msg)
            merged["message_medias"].update(result.get("message_medias", {}))
            merged["exist_filenum"] += result.get("exist_filenum", 0)
            if not result.get("success_flag", True):
                merged["success_flag"] = False
            if not merged["error_message"] and result.get("error_message"):
                merged["error_message"] = result.get("error_message")
        return merged

    def _run_parallel(self, items: list, func: Callable[[Any], Any]) -> list[Any]:
        """对无依赖任务使用线程池并发执行；失败隔离，返回结果列表."""
        if not items or self._thread_executor is None:
            return [func(item) for item in items]

        def _wrapper(item):
            try:
                return func(item)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                # 返回失败结果而非 None：避免合并时被过滤后默认成功（导致失败被写黑名单、永不重试）
                return self._failure_result(err)

        futures: list[Future] = [self._thread_executor.submit(_wrapper, item) for item in items]
        # 加超时：同池嵌套提交时避免所有 worker 阻塞在 wait() 造成进程级死锁挂起
        _done, not_done = wait(futures, timeout=_PARALLEL_WAIT_TIMEOUT)
        if not_done:
            log.error(f"[Rmt]转移并发任务超时，{len(not_done)} 个子任务未完成，按失败处理")
        results = []
        for future in futures:
            if future in not_done:
                results.append(self._failure_result(TimeoutError("transfer group timeout")))
            else:
                results.append(future.result())
        return results

    @staticmethod
    def _failure_result(err: Exception) -> dict:
        """构造与成功结果同构的失败结果字典."""
        return {
            "total_count": 0,
            "failed_count": 1,
            "alert_count": 1,
            "alert_messages": [str(err)],
            "message_medias": {},
            "success_flag": False,
            "error_message": str(err),
            "exist_filenum": 0,
        }

    def _transfer_files_loop(
        self,
        medias,
        in_from,
        in_path,
        operation,
        target_dir,
        unknown_dir,
        bluray_disk_dir,
        episode,
        udf_flag,
        src_backend,
        dst_backend,
    ):
        failed_count = 0
        alert_count = 0
        alert_messages = []
        total_count = 0
        total_exist_filenum = 0
        message_medias = {}
        success_flag = True
        error_message = ""

        for file_item, media in medias.items():
            try:
                total_count += 1
                if not udf_flag and re.search(r"[./\s\[]+Sample[/\.\s\]]+", file_item, re.IGNORECASE):
                    log.warn(f"[Rmt]{file_item} 可能是预告片，跳过...")
                    continue

                file_name = os.path.basename(file_item)
                self.progress.update(
                    ptype=ProgressKey.FileTransfer,
                    value=round(total_count / len(medias) * 100) - (0.5 / len(medias) * 100),
                    text=f"正在处理：{file_name} ...",
                )

                reg_path = bluray_disk_dir if bluray_disk_dir else file_item

                profile_ref = bool(
                    media
                    and getattr(media, "content_profile", "") not in (None, "", "default")
                    and getattr(media, "anchor_external_id", "")
                )
                media_ref = str(getattr(media, "tmdb_id", "") or "").strip()
                anchor_ref = bool(
                    media and getattr(media, "anchor_provider", "") and getattr(media, "anchor_external_id", "")
                )
                parsed_media_ref = parse_media_ref(media_ref)
                legacy_ref = bool(parsed_media_ref)
                if (
                    not media
                    or (not media.provider_data and not profile_ref and not legacy_ref and not anchor_ref)
                    or not media.get_title_string()
                    or media.get_title_string().strip().isdigit()
                    or len(media.get_title_string().strip()) < 2
                    or (not profile_ref and not legacy_ref and not anchor_ref and not media_ref)
                ):
                    fc, ac, am = self._handle_unrecognized_file(
                        file_item,
                        reg_path,
                        in_path,
                        unknown_dir,
                        operation,
                        target_dir,
                        udf_flag,
                        alert_messages,
                        src_backend,
                    )
                    failed_count += fc
                    alert_count += ac
                    alert_messages = am
                    if fc > 0:
                        success_flag = False
                    if udf_flag:
                        return {
                            "total_count": total_count,
                            "failed_count": failed_count,
                            "alert_count": alert_count,
                            "alert_messages": alert_messages,
                            "message_medias": message_medias,
                            "success_flag": False,
                            "error_message": "无法识别媒体信息",
                        }
                    continue

                if src_backend is not None:
                    st = src_backend.stat(file_item)
                    media.size = st.size if st else 0
                else:
                    media.size = os.path.getsize(file_item)
                dist_path = target_dir or self._path_resolver.get_best_target_path(
                    mtype=media.type,
                    in_path=in_path,
                    size=media.size,
                    media=media,
                    media_service=self.media,
                )
                if not dist_path:
                    log.error("[Rmt]文件转移失败，目的路径不存在！")
                    failed_count += 1
                    alert_count += 1
                    alert_messages.append("目的路径不存在")
                    continue
                resolved_backend = dst_backend or self._path_resolver.resolve_dst_backend(dist_path, media.type)
                if not os.path.exists(dist_path) and not resolved_backend:
                    return {
                        "total_count": total_count,
                        "failed_count": failed_count,
                        "alert_count": alert_count,
                        "alert_messages": alert_messages,
                        "message_medias": message_medias,
                        "success_flag": False,
                        "error_message": f"目录不存在：{dist_path}",
                    }

                fc, ac, am, exist_filenum, new_file, ret_file_path, ret_dir_path = self._do_transfer_file(
                    file_item,
                    media,
                    dist_path,
                    bluray_disk_dir,
                    operation,
                    reg_path,
                    target_dir,
                    udf_flag,
                    alert_messages,
                    src_backend,
                    resolved_backend,
                )
                failed_count += fc
                alert_count += ac
                alert_messages = am
                total_exist_filenum += exist_filenum
                # 失败或已存在（转移历史/目标文件已存在）都不进入成功处理与消息聚合
                if fc > 0:
                    success_flag = False
                if fc > 0 or exist_filenum > 0:
                    continue

                file_ext = os.path.splitext(file_item)[-1]
                raw_tmdb_id = str(media.tmdb_id or "").strip()
                if raw_tmdb_id.isdigit():
                    media.set_provider_data(
                        self.media.get_tmdb_info(
                            mtype=media.type,
                            tmdbid=raw_tmdb_id,
                            append_to_response="all",
                        )
                    )
                snapshot = (
                    self._metadata_service.latest_snapshot_for_media(media)
                    if self._metadata_service is not None
                    else None
                )
                out_path = new_file if not bluray_disk_dir else ret_dir_path
                season_episode = media.get_season_episode_string() if out_path else media.get_season_string()
                media_dto = TransferMediaDTO(
                    title=media.title or "",
                    type_value=media.type.value if media.type else "",
                    category=media.category or "",
                    tmdb_id=int(raw_tmdb_id) if raw_tmdb_id.isdigit() else 0,
                    year=media.year or "",
                    season_episode=season_episode,
                    poster=media.get_poster_image() or "",
                    identity_id=getattr(snapshot, "identity_id", None),
                    anchor_provider=getattr(media, "anchor_provider", None),
                    anchor_external_id=getattr(media, "anchor_external_id", None),
                    content_profile=getattr(media, "content_profile", None),
                )

                self._history.insert_transfer_history(
                    in_from=in_from,
                    rmt_mode=operation,
                    in_path=reg_path,
                    out_path=out_path or "",
                    dest=dist_path,
                    media_info=media_dto,
                    dst_backend=getattr(resolved_backend, "id", None) or "local",
                )

                # 转移成功：若该文件曾进入未识别列表，标记为已识别（不再依赖手动指定季集标志）
                self._history.update_transfer_unknown_state(reg_path)

                if media.type == MediaType.MOVIE:
                    media.user_id = self._resolve_owner_user_id(reg_path, media)
                else:
                    message_key = f"{media.get_title_string()}-{media.get_season_string()}"
                    if not message_medias.get(message_key):
                        message_medias[message_key] = media
                        media.user_id = self._resolve_owner_user_id(reg_path, media)
                    if not message_medias[message_key].is_in_episode(media.get_episode_list()):
                        message_medias[message_key].total_episodes += media.total_episodes
                        message_medias[message_key].size += media.size

                # 刮削必须在转移完成事件前落盘：Emby/Jellyfin 收到事件后立即扫描，
                # 异步队列会造成“先入库、后出元数据”的空窗。
                scrape_ok = self._scrape_queue_service.scrape_file_now(
                    media=media,
                    dir_path=ret_dir_path,
                    file_name=self._scrape_file_base_name(ret_file_path, ret_dir_path),
                    file_ext=file_ext,
                    dst_backend=dst_backend,
                )
                if not scrape_ok:
                    # 同步刮削失败时投递一次后台重试，并把失败显式暴露在日志中；
                    # 不能静默当作成功，否则媒体库会长期保持空元数据。
                    log.error(f"[Rmt]刮削未完成，已提交后台重试：{ret_file_path}")
                    self._scrape_queue_service.submit_file_scrape(
                        media=media,
                        dir_path=ret_dir_path,
                        file_name=self._scrape_file_base_name(ret_file_path, ret_dir_path),
                        file_ext=file_ext,
                        dst_backend=dst_backend,
                    )
                elif media.type == MediaType.MOVIE:
                    # 刮削成功后才提示“已入库”，避免刮削失败仍显示成功。
                    self.message.send_transfer_movie_message(
                        in_from, media, exist_filenum, self._path_resolver.movie_category_flag or False
                    )

                self._publish_subtitle_download(media, ret_file_path, file_ext, bool(bluray_disk_dir))
                self._publish_transfer_finished(in_path, file_item, out_path, dist_path, media)
                # TV/动漫单集转移完成事件（驱动订阅进度更新）
                if media.type in (MediaType.TV, MediaType.ANIME) and media.get_episode_list():
                    self._publish_episode_transferred(media)

                self.progress.update(
                    ptype=ProgressKey.FileTransfer,
                    value=round(total_count / len(medias) * 100),
                    text=f"{file_name} 转移完成",
                )

            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"[Rmt]文件转移时发生错误：{err!s}")
                failed_count += 1
                success_flag = False
                if not error_message:
                    error_message = str(err)

        return {
            "total_count": total_count,
            "failed_count": failed_count,
            "alert_count": alert_count,
            "alert_messages": alert_messages,
            "message_medias": message_medias,
            "success_flag": success_flag,
            "error_message": error_message,
            "exist_filenum": total_exist_filenum,
        }

    @staticmethod
    def _scrape_file_base_name(ret_file_path: str | None, ret_dir_path: str | None) -> str:
        """刮削 NFO 基础名：文件取去扩展名的文件名，目录（蓝光原盘）取目录名。

        直接用含扩展名的文件名会导致生成 `xxx.mkv.nfo`，媒体库无法识别并自行生成 movie.nfo。
        """
        if ret_file_path:
            return os.path.splitext(os.path.basename(ret_file_path))[0]
        return os.path.basename(ret_dir_path or "")

    def _publish_subtitle_download(self, media, ret_file_path, file_ext, bluray):
        self._thread_executor.submit(
            self._event_bus.publish,
            Event(
                event_type=SUBTITLE_DOWNLOAD,
                payload=SubtitleDownloadPayload(
                    media_info=media.to_dict(),
                    file=ret_file_path,
                    file_ext=file_ext,
                    bluray=bluray,
                ),
            ),
        )

    def _publish_transfer_finished(self, in_path, file_item, out_path, dist_path, media):
        self._thread_executor.submit(
            self._event_bus.publish,
            Event(
                event_type=MEDIA_TRANSFER_FINISHED,
                payload=MediaTransferFinishedPayload(
                    in_path=in_path,
                    file=file_item,
                    target_path=out_path,
                    dest=dist_path,
                    media_info=media.to_dict(),
                ),
            ),
        )

    def _publish_episode_transferred(self, media):
        self._thread_executor.submit(
            self._event_bus.publish,
            Event(
                event_type=MEDIA_EPISODE_TRANSFERRED,
                payload=MediaEpisodeTransferredPayload(
                    tmdb_id=media.tmdb_id,
                    title=media.title,
                    season=media.get_season_seq(),
                    episodes=media.get_episode_list(),
                    total_episodes=media.total_episodes,
                    media_type=media.type.value if media.type else None,
                ),
            ),
        )

    def _handle_unrecognized_file(
        self,
        file_item,
        reg_path,
        in_path,
        unknown_dir,
        operation,
        target_dir,
        udf_flag,
        alert_messages,
        src_backend=None,
    ):
        file_name = os.path.basename(file_item)
        error = "无法识别媒体信息"
        # 已在未识别列表：跳过（无论 STATE），避免每周期重复识别报错/重复通知
        if self._history.is_transfer_unknown_exists(reg_path):
            return 1, 0, alert_messages
        insert = self._history.is_need_insert_transfer_unknown(reg_path)
        if not insert:
            return 1, 0, alert_messages
        log.warn(f"[Rmt]{file_name} {error}！")
        self.progress.update(ptype=ProgressKey.FileTransfer, text=error)
        self._history.insert_transfer_unknown(reg_path, target_dir, operation)
        if error not in alert_messages:
            alert_messages = alert_messages + [error]
        if unknown_dir:
            log.warn(f"[Rmt]{file_name} 按原文件名转移到未识别目录：{unknown_dir}")
            new_file = os.path.join(unknown_dir, os.path.basename(file_item))
            self._engine.transfer(file_item, new_file, operation, src_backend=src_backend)
        elif self._path_resolver.unknown_path:
            p = self._path_resolver._get_best_unknown_path(in_path)
            if p:
                log.warn(f"[Rmt]{file_name} 按原文件名转移到未识别目录：{p}")
                new_file = os.path.join(p, os.path.basename(file_item))
                self._engine.transfer(file_item, new_file, operation, src_backend=src_backend)
        else:
            log.error(f"[Rmt]{file_name} {error}！")
        return 1, 1, alert_messages

    @staticmethod
    def _target_exists(path: str, dst_backend) -> bool:
        """目标文件是否存在：存储后端（远端）用 backend.exists，本地用 os.path.exists"""
        if dst_backend is not None:
            try:
                return bool(dst_backend.exists(path))
            except Exception:  # noqa: BLE001
                return os.path.exists(path)
        return os.path.exists(path)

    @classmethod
    def _history_dest_exists(cls, history, dst_backend) -> bool:
        """转移历史的目标文件是否仍存在（DEST 可能是库根，文件名在剧集子目录）."""
        dest_path = str(getattr(history, "dest_path", "") or "")
        dest_filename = str(getattr(history, "dest_filename", "") or "")
        if not dest_path or not dest_filename:
            return False
        if cls._target_exists(os.path.join(dest_path, dest_filename), dst_backend):
            return True
        if str(dst_backend or "local") != "local" or not os.path.isdir(dest_path):
            return False
        for _root, _dirs, files in os.walk(dest_path):
            if dest_filename in files:
                return True
        return False

    @staticmethod
    def _episode_in_history(history, episode) -> bool:
        """判断某集是否已存在于转移历史（支持 S01E01 与 S01E01-E05 格式）."""
        try:
            target = int(episode)
        except (TypeError, ValueError):
            return False
        for h in history or []:
            se = str(getattr(h, "season_episode", None) or "")
            match = re.search(r"E(\d+)(?:\s*-\s*E?(\d+))?", se)
            if not match:
                continue
            try:
                begin = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else begin
            except (TypeError, ValueError):
                continue
            if begin <= target <= end:
                return True
        return False

    def _with_library_target_lock(
        self,
        backend_id: Any,
        target_dir: str | None,
        action: Callable[[], None],
    ) -> bool:
        """与批量重命名共享目标目录锁；竞争时跳过本次写入."""
        if not target_dir:
            action()
            return True
        lock = get_lock_manager().create_lock(target_dir_lock_key(backend_id, target_dir), ttl_seconds=1800)
        if not lock.acquire():
            if lock.last_error is not None:
                log.warn(f"[Rmt]目标锁后端不可用，继续执行：{target_dir} ({lock.last_error})")
                action()
                return True
            log.warn(f"[Rmt]目标目录正在被其他任务修改，跳过：{target_dir}")
            return False
        try:
            action()
            return True
        finally:
            lock.release()

    def _source_transferred_path(self, source_full_path: str, dst_backend=None) -> str:
        """同一源文件已有成功转移记录且目标仍存在时返回目标路径."""
        if not source_full_path:
            return ""
        try:
            row = self._history.get_by_source(os.path.normpath(source_full_path))
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Rmt]源文件转移记录查询失败: {e}")
            return ""
        if not row or not self._history_dest_exists(row, dst_backend):
            return ""
        return os.path.join(str(row.dest_path), str(row.dest_filename))

    def _do_transfer_file(
        self,
        file_item,
        media,
        dist_path,
        bluray_disk_dir,
        operation,
        reg_path,
        target_dir,
        udf_flag,
        alert_messages,
        src_backend=None,
        dst_backend=None,
    ):
        # 源文件级去重：同一个文件已成功转移且目标仍存在时跳过，多版本文件互不影响。
        if not udf_flag:
            transferred_path = self._source_transferred_path(reg_path, dst_backend)
            if transferred_path:
                log.warn(f"[Rmt]文件已转移，跳过重复转移：{reg_path} -> {transferred_path}")
                return (
                    0,
                    0,
                    alert_messages,
                    1,
                    transferred_path,
                    transferred_path,
                    os.path.dirname(transferred_path),
                )

        dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self._existence.is_media_exists(
            dist_path, media, dst_backend
        )
        file_ext = os.path.splitext(file_item)[-1]
        new_file = ret_file_path
        exist_filenum = 0

        # 结合转移历史去重：该 tmdb+季+集已转移过则跳过，
        # 避免目标路径规则变化（如分类子目录调整）导致重复入库。
        # 仅信任源路径仍存在的历史记录：调试/测试残留（源已删除，如 /tmp 假记录）不参与去重，
        # 避免真实文件被误判"已转移"而跳过实际转移
        if media.type != MediaType.MOVIE and media.tmdb_id and media.begin_season and media.begin_episode is not None:
            try:
                season_str = f"S{media.begin_season:02d}"
                history = self._history.get_transfer_info_by(tmdbid=media.tmdb_id, season=season_str) or []
                valid_history = [
                    h
                    for h in history
                    if getattr(h, "source_path", "")
                    and os.path.exists(str(getattr(h, "source_path", "")))
                    and self._history_dest_exists(h, dst_backend)
                ]
                if valid_history and self._episode_in_history(valid_history, media.begin_episode):
                    log.warn(
                        f"[Rmt]剧集已在转移历史中（{media.get_season_episode_string()}），跳过："
                        f"{ret_file_path or file_item}"
                    )
                    # 仅当目标文件真实存在（本地或存储后端）时才写黑名单，
                    # 防止误判（历史记录无效/目标缺失）把真实文件永久黑名单化
                    if ret_file_path and self._target_exists(ret_file_path, dst_backend):
                        self._history.insert_transfer_blacklist(file_item)
                    return 0, 0, alert_messages, 1, new_file, ret_file_path, ret_dir_path
            except Exception as e:  # noqa: BLE001
                log.debug(f"[Rmt]转移历史去重查询失败: {e}")

        if dir_exist_flag:
            if bluray_disk_dir:
                log.warn(f"[Rmt]蓝光原盘目录已存在：{ret_dir_path}")
                return 1, 0, alert_messages, 0, new_file, ret_file_path, ret_dir_path
            if file_exist_flag and ret_file_path:
                exist_filenum = 1
                if udf_flag:
                    # 仅手动转移允许覆盖已存在文件；自动同步（监控/目录同步）跳过
                    old = ret_file_path
                    base, _ = os.path.splitext(ret_file_path)
                    new_file = f"{base}{file_ext}"
                    log.info(f"[Rmt]文件 {old} 已存在，覆盖为 {new_file} ...")
                    acquired = self._with_library_target_lock(
                        getattr(dst_backend, "id", None) or "local",
                        ret_dir_path,
                        lambda: self._engine.transfer(
                            file_item,
                            new_file,
                            operation,
                            over_flag=True,
                            old_file=old,
                            src_backend=src_backend,
                            dst_backend=dst_backend,
                        ),
                    )
                    if not acquired:
                        return 0, 0, alert_messages, 1, new_file, ret_file_path, ret_dir_path
                    self._replicate_to_enabled_backends(media, new_file, dst_backend)
                    return 0, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path
                else:
                    log.warn(f"[Rmt]文件 {ret_file_path} 已存在，跳过")
                    return 0, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path
        else:
            if not ret_dir_path:
                return self._record_fail(
                    file_item,
                    reg_path,
                    target_dir,
                    operation,
                    udf_flag,
                    alert_messages,
                    "识别失败，无法从文件名中识别出季集信息",
                )
            elif not dst_backend:
                os.makedirs(ret_dir_path, exist_ok=True)

        if bluray_disk_dir:
            if not ret_dir_path:
                return self._record_fail(
                    file_item,
                    reg_path,
                    target_dir,
                    operation,
                    udf_flag,
                    alert_messages,
                    "识别失败，无法获取蓝光目录路径",
                )
            acquired = self._with_library_target_lock(
                getattr(dst_backend, "id", None) or "local",
                ret_dir_path,
                lambda: self._engine.transfer_bluray_dir(
                    file_item, ret_dir_path, operation, src_backend=src_backend, dst_backend=dst_backend
                ),
            )
            if not acquired:
                return 0, 0, alert_messages, 1, new_file, ret_file_path, ret_dir_path
        elif not ret_file_path:
            return self._record_fail(
                file_item,
                reg_path,
                target_dir,
                operation,
                udf_flag,
                alert_messages,
                "识别失败，无法从文件名中识别出集数",
            )
        else:
            ret_file_path = f"{ret_file_path}{file_ext}"
            new_file = ret_file_path
            acquired = self._with_library_target_lock(
                getattr(dst_backend, "id", None) or "local",
                ret_dir_path,
                lambda: self._engine.transfer(
                    file_item,
                    ret_file_path,
                    operation,
                    over_flag=False,
                    src_backend=src_backend,
                    dst_backend=dst_backend,
                ),
            )
            if not acquired:
                return 0, 0, alert_messages, 1, new_file, ret_file_path, ret_dir_path
        # 多后端镜像：复制到其他已启用且缺失该文件的后端
        self._replicate_to_enabled_backends(media, new_file, dst_backend)
        return 0, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path

    def _replicate_to_enabled_backends(self, media, transferred_path, primary_backend) -> None:
        """转移成功后，将该媒体镜像到其他已启用且缺失该文件的后端。

        通过串行后台队列（单 worker）执行，避免并发上传打爆多个后端。
        """
        try:
            dest_pairs = self._path_resolver.list_enabled_dest_backends(media.type)
            if not dest_pairs:
                return
            primary_id = str(getattr(primary_backend, "id", "")) if primary_backend is not None else "local"
            file_name = os.path.basename(transferred_path or "")
            if not file_name:
                return
            targets = [
                (dest_root, backend)
                for dest_root, backend in dest_pairs
                if str(getattr(backend, "id", "")) != primary_id
            ]
            if not targets:
                return
            mirror_queue = _get_mirror_queue()
            mirror_queue.submit(
                self._mirror_upload,
                media,
                transferred_path,
                primary_backend,
                targets,
                file_name,
                name=f"mirror:{file_name}",
            )
        except Exception as e:  # noqa: BLE001
            log.warn(f"[Rmt]多后端镜像任务提交失败: {e}")

    def _mirror_upload(self, media, transferred_path, primary_backend, targets: list, file_name: str) -> None:
        """后台串行执行镜像上传（同一时间仅一个后端写入）"""
        for dest_root, backend in targets:
            backend_id = str(getattr(backend, "id", ""))
            try:
                dest_dir = self._path_resolver.get_dest_path_by_info(dest_root, media, self.media)
            except Exception as e:  # noqa: BLE001
                log.debug(f"[Rmt]镜像目标路径计算失败: {e}")
                continue
            if not dest_dir:
                continue
            dest_file = os.path.join(dest_dir, file_name)
            try:
                if backend.exists(dest_file):
                    continue
                if primary_backend is None:
                    with open(transferred_path, "rb") as src:
                        backend.write_stream(dest_file, src)
                else:
                    with primary_backend.read_stream(transferred_path) as src:
                        backend.write_stream(dest_file, src)
                log.info(f"[Rmt]已镜像到后端 {backend_id}: {dest_file}")
            except Exception as e:  # noqa: BLE001
                log.warn(f"[Rmt]镜像到后端 {backend_id} 失败: {e}")
            # 后端间间隔，避免连续上传压垮后端
            time.sleep(MIRROR_BACKEND_DELAY)

    def _record_fail(self, file_item, reg_path, target_dir, operation, udf_flag, alert_messages, msg):
        self.progress.update(ptype=ProgressKey.FileTransfer, text=msg)
        insert = self._history.is_need_insert_transfer_unknown(reg_path)
        if insert:
            self._history.insert_transfer_unknown(reg_path, target_dir, operation)
        if msg not in alert_messages and insert:
            alert_messages = alert_messages + [msg]
        return 1, 1 if insert else 0, alert_messages, 0, None, None, None

    def _transfer_post_process(self, result, in_from, in_path, operation, root_path) -> tuple[bool, str]:
        if result["message_medias"]:
            self.message.send_transfer_tv_message(
                result["message_medias"],
                in_from,
                result.get("exist_filenum", 0),
                self._path_resolver.tv_category_flag or False,
            )

        total_count = result["total_count"]
        failed_count = result["failed_count"]
        alert_count = result["alert_count"]
        alert_messages = result["alert_messages"]
        success_flag = result["success_flag"]
        error_message = result["error_message"]

        # 兜底：部分失败分支只把原因写进 alert_messages，未写 error_message，
        # 会让上游日志出现「转移失败：」（原因为空），无法定位问题
        if not success_flag and not error_message:
            error_message = (
                "、".join(dict.fromkeys(alert_messages)) if alert_messages else f"{failed_count} 个文件转移失败"
            )

        log.info(f"[Rmt]{in_path} 处理完成，总数：{total_count}，失败：{failed_count}")
        if alert_count > 0:
            reason = "、".join(alert_messages)
            self._event_bus.publish(
                Event(
                    event_type=TRANSFER_FAIL,
                    payload=TransferFailPayload(path=in_path, count=alert_count, reason=reason),
                )
            )
            self.message.send_transfer_fail_message(in_path, alert_count, reason)
        elif failed_count == 0:
            if (
                operation == "move"
                and os.path.exists(in_path)
                and os.path.isdir(in_path)
                and not root_path
                and not PathUtils.get_dir_files(in_path=in_path, exts=RMT_MEDIAEXT)
                and not PathUtils.get_dir_files(in_path=in_path, exts=[".!qb", ".part"])
            ):
                log.info(f"[Rmt]目录下已无媒体文件，移动模式下删除目录：{in_path}")
                shutil.rmtree(in_path)
        return self._finish_transfer(success_flag, error_message)

    def transfer_manually(self, s_path, t_path, operation):
        """全量转移，用于使用命令调用."""
        if not s_path:
            return
        if not os.path.exists(s_path):
            log.warn(f"[Rmt]源目录不存在：{s_path}")
            return

        lock_key = f"filetransfer:manual:{hashlib.md5(s_path.encode(), usedforsecurity=False).hexdigest()}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=3600)
        acquired = lock.acquire()
        if not acquired:
            log.warn(f"[Rmt]源目录正在转移中：{s_path}")
            return

        try:
            if t_path and not os.path.exists(t_path):
                log.warn(f"[Rmt]目的目录不存在：{t_path}")
                return
            log.info(f"[Rmt]转移模式为：{operation}")
            log.info(f"[Rmt]正在转移以下目录中的全量文件：{s_path}")
            paths = [
                path
                for path in PathUtils.get_dir_level1_medias(s_path, RMT_MEDIAEXT)
                if not PathUtils.is_invalid_path(path)
            ]

            def _transfer_one(path: str) -> None:
                ret, ret_msg = self.transfer_media(
                    in_from=SyncType.MAN, in_path=path, target_dir=t_path, operation=operation
                )
                if not ret:
                    log.error(f"[Rmt]{path} 处理失败：{ret_msg}")

            self._run_parallel(paths, _transfer_one)
        finally:
            lock.release()

    def get_sync_backend_by_dest(self, dest: str) -> str:
        """根据目的目录查找对应同步配置的目标后端."""
        if not dest:
            return "local"
        try:
            for entity in self._sync_repo.get_all():
                if str(entity.dest or "") == dest:
                    return str(entity.dst_backend or "local") or "local"
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            log.error("[Rmt]获取同步配置失败，无法根据目的目录识别目标后端，默认使用 local")
        return "local"
