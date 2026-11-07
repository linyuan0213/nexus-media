"""
DownloadService - 下载编排业务层
将 web/controllers/download.py 中的下载业务逻辑下沉到可独立测试的 Service。
"""

import os
from typing import Any

import log
from app.core.exceptions import DomainError, ServiceError
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.subscribe_repository import SubscribeRepository
from app.domain.enums import SearchType
from app.domain.lifecycle import LifecycleStage, LifecycleStatus
from app.domain.media_types import MediaKind, media_type_registry
from app.domain.mediatypes import MediaType
from app.infrastructure.temp import temp_manager
from app.media.display_image_policy import transform_display_image, unwrap_display_image_url
from app.media.metadata.gateway import MetadataGateway
from app.media.models import MediaInfo
from app.media.poster_resolver import preferred_profile_poster
from app.schemas.download import (
    DownloadResultDTO,
    IndexerStatisticsDTO,
)
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.indexer_service import IndexerService
from app.services.lifecycle_service import LifecycleProjector
from app.services.search_service import Searcher
from app.services.torrentremover_core import TorrentRemoverService as TorrentRemover
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.sites.torrent import Torrent


class DownloadService:
    """
    下载编排业务服务
    负责：
    - 从搜索结果/链接/种子文件的下载编排
    - m-team/yemapt 特殊下载链接处理
    - 正在下载任务的媒体信息拼装
    - 索引器统计数据格式化
    """

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        downloader: Downloader,
        searcher: Searcher,
        sites: SiteCache,
        site_engine: SiteEngine,
        indexer_service: IndexerService,
        torrent_remover: TorrentRemover,
        download_history_repo: DownloadHistoryRepositoryAdapter,
        subscribe_repo: SubscribeRepository | None = None,
        lifecycle: LifecycleProjector | None = None,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._downloader = downloader
        self._searcher = searcher
        self._sites = sites
        self._site_engine = site_engine
        self._indexer_service = indexer_service
        self._torrent_remover = torrent_remover
        self._download_history_repo = download_history_repo
        self._subscribe_repo = subscribe_repo or SubscribeRepository()
        self._lifecycle = lifecycle
        self._metadata_gateway = metadata_gateway
        self._progress_reported: dict[str, int] = {}

    def _gw(self) -> MetadataGateway:
        if self._metadata_gateway is None:
            raise ServiceError("元数据网关不可用")
        return self._metadata_gateway

    # ---------- 下载编排 ----------

    def _resolve_download_url(self, page_url: str, enclosure: str | None) -> str:
        """通过站点引擎解析 API 站点下载链接"""
        if not enclosure:
            return self._downloader.get_download_url(page_url) or ""
        return enclosure or ""

    def resolve_download_url(self, page_url: str, enclosure: str | None) -> str:
        """公开方法：解析站点下载链接"""
        return self._resolve_download_url(page_url, enclosure)

    def download_from_search_results(
        self, dl_id: int, dl_dir: str, dl_setting: str, user_name: str, user_id: int | None = None
    ) -> DownloadResultDTO:
        """从搜索结果批量下载，收集所有结果后返回批量状态."""
        results = self._searcher.get_search_result_by_id(dl_id)
        if not results:
            return DownloadResultDTO(success=False, message="未找到搜索结果")

        success_count = 0
        fail_messages = []
        for res in results:
            enclosure = self._resolve_download_url(res.PAGEURL, res.ENCLOSURE)
            media = self._gw().resolve_by_title(
                res.TITLE or res.TORRENT_NAME,
                subtitle=res.DESCRIPTION,
            )
            if not media:
                # 识别失败时，用搜索记录已有的数据创建最小 MediaInfo
                media = MediaInfo()
                media.title = res.TITLE or res.TORRENT_NAME
                if getattr(res, "ANCHOR_PROVIDER", None) and getattr(res, "ANCHOR_EXTERNAL_ID", None):
                    media.anchor_provider = res.ANCHOR_PROVIDER
                    media.anchor_external_id = res.ANCHOR_EXTERNAL_ID
                    media.identity_id = getattr(res, "IDENTITY_ID", None)
                    media.content_profile = getattr(res, "CONTENT_PROFILE", None) or "default"
                elif str(res.TMDBID or "").isdigit():
                    media.tmdb_id = res.TMDBID
                if res.POSTER:
                    media.poster_path = res.POSTER
            else:
                if getattr(res, "ANCHOR_PROVIDER", None) and getattr(res, "ANCHOR_EXTERNAL_ID", None):
                    media.anchor_provider = res.ANCHOR_PROVIDER
                    media.anchor_external_id = res.ANCHOR_EXTERNAL_ID
                    media.identity_id = getattr(res, "IDENTITY_ID", None)
                    media.content_profile = getattr(res, "CONTENT_PROFILE", None) or "default"
                elif str(res.TMDBID or "").isdigit() and not media.tmdb_id:
                    media.tmdb_id = res.TMDBID
                if res.POSTER and not media.poster_path:
                    media.poster_path = res.POSTER
            poster = unwrap_display_image_url(media.poster_path or "")
            media.poster_path = preferred_profile_poster(
                poster,
                media.content_profile,
                media.anchor_provider,
                media.anchor_external_id,
                media.type,
                self._metadata_gateway,
            )
            # 保存站点原始种子名，用于下载历史记录和后续识别
            media.org_string = res.TORRENT_NAME
            media.set_torrent_info(
                enclosure=enclosure,
                size=res.SIZE,
                site=res.SITE,
                page_url=res.PAGEURL,
                seeders=int(res.SEEDERS or 0),
                peers=int(getattr(res, "PEERS", 0) or 0),
                upload_volume_factor=float(res.UPLOAD_VOLUME_FACTOR if res.UPLOAD_VOLUME_FACTOR is not None else 1.0),
                download_volume_factor=float(
                    res.DOWNLOAD_VOLUME_FACTOR if res.DOWNLOAD_VOLUME_FACTOR is not None else 1.0
                ),
            )
            _, ret, ret_msg = self._downloader.download(
                media_info=media,
                download_dir=dl_dir,
                download_setting=dl_setting,
                in_from=SearchType.WEB,
                user_name=user_name,
                user_id=user_id,
            )
            if ret:
                success_count += 1
            else:
                fail_messages.append(f"{res.TORRENT_NAME}: {ret_msg}")

        if fail_messages:
            return DownloadResultDTO(
                success=False,
                message=f"批量下载完成：{success_count}/{len(results)} 成功\n" + "\n".join(fail_messages),
            )
        return DownloadResultDTO(success=True, message=f"全部下载成功：{success_count}/{len(results)}")

    def download_from_link(
        self,
        site: str,
        enclosure: str,
        title: str,
        description: str,
        page_url: str,
        size: str,
        seeders: str,
        peers: str,
        uploadvolumefactor: str,
        downloadvolumefactor: str,
        dl_dir: str,
        dl_setting: str,
        user_name: str,
        user_id: int | None = None,
    ) -> DownloadResultDTO:
        """从下载链接添加下载"""
        enclosure = self._resolve_download_url(page_url, enclosure)
        if not title or not enclosure:
            return DownloadResultDTO(success=False, message="种子信息有误")

        media = self._gw().resolve_by_title(title, subtitle=description)
        if not media:
            # 识别完全失败时，用原始资源名创建最小 MediaInfo
            media = MediaInfo()
        # 如果识别成功但 TMDB 查询失败导致 title 为空，用传入的 title 回退
        if not media.title:
            media.title = title

        # 保存站点原始资源名称，用于下载历史记录和后续识别
        media.org_string = title
        media.site = site
        media.enclosure = enclosure
        media.page_url = page_url
        media.size = int(size or 0)
        media.upload_volume_factor = float(uploadvolumefactor if uploadvolumefactor is not None else 1.0)
        media.download_volume_factor = float(downloadvolumefactor if downloadvolumefactor is not None else 1.0)
        media.seeders = int(seeders or 0)
        media.peers = int(peers or 0)

        _, ret, ret_msg = self._downloader.download(
            media_info=media,
            download_dir=dl_dir,
            download_setting=dl_setting,
            in_from=SearchType.WEB,
            user_name=user_name,
            user_id=user_id,
        )
        if not ret:
            return DownloadResultDTO(success=False, message=ret_msg or "如连接正常，请检查下载任务是否存在")
        return DownloadResultDTO(success=True, message="下载成功")

    def download_from_torrent_files_or_urls(
        self,
        files: list,
        urls: list,
        dl_dir: str,
        dl_setting: str,
        user_name: str,
        page_url: str | None = None,
        upload_volume_factor: float | None = None,
        download_volume_factor: float | None = None,
        title: str | None = None,
        description: str | None = None,
        site: str | None = None,
        size: int | None = None,
        user_id: int | None = None,
    ) -> DownloadResultDTO:
        """从种子文件或 URL 链接添加下载"""
        if not files and not urls:
            return DownloadResultDTO(success=False, message="没有种子文件或者种子链接")

        uploaded_files = []
        success_count = 0
        failures: list[str] = []
        try:
            # 处理上传的种子文件
            for file_item in files:
                if not file_item:
                    continue
                file_name = file_item.get("upload", {}).get("filename")
                file_path = temp_manager.get_temp_path(file_name)
                uploaded_files.append(file_path)
                media_info = self._gw().resolve_by_title(file_name)
                if not media_info:
                    media_info = MediaInfo()
                    media_info.title = file_name
                media_info.org_string = file_name
                media_info.site = "WEB"
                if page_url:
                    media_info.page_url = page_url
                if upload_volume_factor is not None:
                    media_info.upload_volume_factor = upload_volume_factor
                if download_volume_factor is not None:
                    media_info.download_volume_factor = download_volume_factor
                _, _, errmsg = self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name,
                    user_id=user_id,
                )
                if errmsg:
                    failures.append(f"{file_name}: {errmsg}")
                    log.warn(f"[Download]推送下载器失败(文件): {errmsg}")
                else:
                    success_count += 1
                    log.info(f"[Download]已推送到下载器(文件): {file_name}")

            # 处理 URL 链接
            if urls and not isinstance(urls, list):
                urls = [urls]
            for url in urls:
                if not url:
                    continue
                site_info = self._sites.get_sites(siteurl=url) or {}
                if not isinstance(site_info, dict):
                    site_info = {}
                if not url.startswith("magnet:"):
                    torrent = Torrent(site_engine=self._site_engine)
                    file_path, _, _, _, retmsg = torrent.get_torrent_info(
                        url=url,
                        cookie=site_info.get("cookie"),
                        api_key=site_info.get("api_key"),
                        bearer_token=site_info.get("bearer_token"),
                        ua=site_info.get("ua"),
                        proxy=site_info.get("proxy") or False,
                    )
                    if not file_path:
                        return DownloadResultDTO(success=False, message=f"下载种子文件失败： {retmsg}")
                    identify_title = title or os.path.basename(file_path)
                    media_info = self._gw().resolve_by_title(identify_title, subtitle=description)
                    if not media_info:
                        media_info = MediaInfo()
                        media_info.title = identify_title
                    media_info.org_string = title or os.path.basename(file_path)
                    media_info.site = site_info.get("name") or "WEB"
                    media_info.enclosure = url
                else:
                    # magnet 链接：用前端传入的 title/description 识别
                    identify_title = title or url
                    media_info = self._gw().resolve_by_title(identify_title, subtitle=description)
                    if not media_info:
                        media_info = MediaInfo()
                        media_info.title = identify_title
                    media_info.org_string = title or url
                    media_info.enclosure = url
                    media_info.site = site or "WEB"
                    if size is not None:
                        media_info.size = size
                    file_path = None

                if page_url:
                    media_info.page_url = page_url
                if upload_volume_factor is not None:
                    media_info.upload_volume_factor = upload_volume_factor
                if download_volume_factor is not None:
                    media_info.download_volume_factor = download_volume_factor

                _, _, errmsg = self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name,
                    user_id=user_id,
                )
                if errmsg:
                    failures.append(f"{title or url}: {errmsg}")
                    log.warn(f"[Download]推送下载器失败: {errmsg}")
                else:
                    success_count += 1
                    log.info(f"[Download]已推送到下载器: {title or url}")
        finally:
            # 清理上传的临时文件
            for tmp_file in uploaded_files:
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                        log.debug(f"[Web]已删除上传的临时文件: {tmp_file}")
                except (DomainError, ServiceError):
                    raise
                except Exception as e:
                    log.warn(f"[Web]删除上传的临时文件失败: {tmp_file}, {e!s}")

        if failures and success_count == 0:
            return DownloadResultDTO(success=False, message=f"添加下载失败：{failures[0]}")
        if failures:
            return DownloadResultDTO(success=True, message=f"部分添加成功，{len(failures)} 个失败：{failures[0]}")
        return DownloadResultDTO(success=True, message="添加下载完成！")

    # ---------- 正在下载任务（含媒体信息拼装） ----------

    def get_downloading_with_media_info(self, page: int = 1, page_size: int = 50) -> dict:
        """
        获取正在下载的任务列表，并拼装媒体信息（标题、海报）
        从数据库读取任务列表，按需从下载器获取实时进度
        返回 {"items": [...], "total": N}
        """
        active_tasks = self._download_history_repo.get_active_downloads()
        if not active_tasks:
            return {"items": [], "total": 0}

        # 按下载器分组任务
        downloader_groups: dict[str, list[Any]] = {}
        for task in active_tasks:
            did = task.downloader or ""
            if did not in downloader_groups:
                downloader_groups[did] = []
            downloader_groups[did].append(task)

        result = []
        completed_ids: list[tuple[str, str]] = []
        active_ids: list[tuple[str, str]] = []

        for did, tasks in downloader_groups.items():
            downloader_conf = None
            try:
                downloader_conf = self._downloader.get_downloader_conf(did)
            except (DomainError, ServiceError):
                raise
            except Exception:
                downloader_conf = None
            if not downloader_conf:
                # 下载器配置已不存在：历史任务无法再查询进度，直接标记完成并清理，
                # 避免每次轮询都触发 get_downloader 打印“配置不存在”刷屏。
                for task in tasks:
                    if task.download_id:
                        completed_ids.append((did, task.download_id))
                log.warn(f"[DownloadService]下载器 {did} 配置不存在，{len(tasks)} 个下载任务已标记完成")
                continue
            downloader_name = downloader_conf.get("name") if downloader_conf else did

            # 批量查询这些任务的进度（直接调用客户端，绕过 only_nexus_media 标签过滤）
            ids = [t.download_id for t in tasks if t.download_id]
            _client = self._downloader.get_downloader(did)
            if not _client:
                continue
            try:
                progress_list = _client.get_downloading_progress(ids=ids)
            except (DomainError, ServiceError):
                raise
            except Exception:
                progress_list = None
            if progress_list is None:
                # 查询失败：跳过本轮状态回写，绝不能在错误时把任务标记为完成
                log.warn(f"[DownloadService]下载器 {did} 进度查询失败，跳过本轮状态更新")
                continue
            progress_map = {p.get("id"): p for p in progress_list if p.get("id")}

            for task in tasks:
                try:
                    tid = task.download_id
                    progress = progress_map.get(tid)

                    if not progress:
                        # 任务在下载器中不存在，标记为完成
                        completed_ids.append((did, tid))
                        continue

                    prog_val = progress.get("progress", 0)
                    if prog_val >= 100:
                        # 下载已完成
                        completed_ids.append((did, tid))
                        continue

                    self._project_download_progress(task, prog_val)

                    # 任务还在下载中，确保 state 为 downloading
                    if getattr(task, "state", None) != "downloading":
                        active_ids.append((did, tid))

                    title, image = self._build_display_info(task)
                    result.append(
                        {
                            "id": tid,
                            "name": progress.get("name") or task.torrent or "",
                            "title": title,
                            "image": image,
                            "progress": prog_val,
                            "state": progress.get("state", ""),
                            "speed": progress.get("speed", ""),
                            "size": progress.get("size", ""),
                            "downloader_id": did,
                            "downloader_name": downloader_name,
                            "client_id": downloader_conf.get("type") if downloader_conf else "",
                            "save_path": task.save_path,
                            "labels": progress.get("labels", []),
                            "category": progress.get("category", ""),
                            "content_profile": getattr(task, "content_profile", "") or "",
                        }
                    )
                except (DomainError, ServiceError):
                    raise
                except Exception as e:
                    log.error(f"[DownloadService]处理任务 {task.download_id} 失败：{e}")

        # 批量标记还在下载中的任务
        if active_ids:
            try:
                self._download_history_repo.batch_update_state([(did, tid, "downloading") for did, tid in active_ids])
            except (DomainError, ServiceError):
                raise
            except Exception as e:
                log.debug(f"[DownloadService]批量更新任务状态失败：{e}")

        # 批量标记已完成任务
        if completed_ids:
            try:
                self._download_history_repo.batch_update_state([(did, tid, "completed") for did, tid in completed_ids])
            except (DomainError, ServiceError):
                raise
            except Exception as e:
                log.debug(f"[DownloadService]批量标记任务完成失败：{e}")

        total = len(result)
        start = (page - 1) * page_size
        end = start + page_size
        return {"items": result[start:end], "total": total}

    def _project_download_progress(self, task, progress: Any) -> None:
        """把下载器百分比投影到生命周期；按 10% 步进降频，避免刷事件."""
        if self._lifecycle is None:
            return
        try:
            value = max(0, min(100, int(float(progress))))
        except (TypeError, ValueError):
            return
        key = str(getattr(task, "download_id", "") or getattr(task, "id", "") or "")
        last = self._progress_reported.get(key)
        if last is not None and abs(value - last) < 10:
            return
        self._progress_reported[key] = value
        media = MediaInfo()
        media.title = str(getattr(task, "title", "") or getattr(task, "torrent", "") or "")
        media.year = str(getattr(task, "year", "") or "")
        media.tmdb_id = str(getattr(task, "tmdb_id", "") or "")
        media_ref = self._task_media_ref(task)
        media.media_type_key = media_ref.key
        media.media_kind = media_ref.kind.value
        media.type = self._task_media_type(task)
        media.anchor_provider = getattr(task, "anchor_provider", None)
        media.anchor_external_id = getattr(task, "anchor_external_id", None)
        media.identity_id = getattr(task, "identity_id", None)
        media.content_profile = getattr(task, "content_profile", None) or "default"
        try:
            self._lifecycle.record_media(
                media,
                stage=LifecycleStage.DOWNLOADING,
                status=LifecycleStatus.RUNNING,
                event_type="download.progress",
                progress=value,
                event_key=f"download:{key}",
            )
        except Exception as exc:  # noqa: BLE001 - 进度投影失败不影响下载状态
            log.debug(f"[DownloadService]下载进度投影失败 {key}: {exc}")

    @staticmethod
    def _task_media_ref(task):
        value = str(getattr(task, "media_type", "") or "").strip()
        profile = str(getattr(task, "content_profile", "") or "").strip()
        return media_type_registry.resolve_profile(profile) or media_type_registry.resolve(value, profile)

    @classmethod
    def _task_media_type(cls, task) -> MediaType:
        resolved = cls._task_media_ref(task)
        if resolved.key == MediaType.ANIME.value:
            return MediaType.ANIME
        if resolved.kind == MediaKind.MOVIE:
            return MediaType.MOVIE
        if resolved.kind == MediaKind.EPISODIC:
            return MediaType.TV
        return MediaType.UNKNOWN

    def _build_display_info(self, task) -> tuple[str, str]:
        """根据下载历史任务构建显示标题和海报"""
        year = task.year
        se = task.season_episode
        display_name = task.title
        poster = task.poster or ""
        profile = str(getattr(task, "content_profile", "") or "")
        task_type = str(getattr(task, "type", "") or "").lower()
        if not poster or not profile:
            if not task_type or task_type == "movie":
                try:
                    hint = self._subscribe_repo.get_movie_subscription_hint(
                        getattr(task, "anchor_provider", None),
                        getattr(task, "anchor_external_id", None),
                        display_name,
                        identity_id=getattr(task, "identity_id", None),
                    )
                    if not poster:
                        poster = str(hint.get("image") or "")
                    if not profile:
                        profile = str(hint.get("content_profile") or "")
                except Exception as e:  # noqa: BLE001
                    log.debug(f"[DownloadService]下载任务海报回填失败: {e}")
        task.content_profile = profile or getattr(task, "content_profile", "")
        poster = transform_display_image(str(profile or task.content_profile or ""), poster)
        if year:
            title = f"{display_name} ({year}) {se}"
        else:
            title = f"{display_name} {se}"
        return title, poster

    # ---------- 下载器实时速率统计 ----------

    def get_downloader_speed_statistics(self) -> dict:
        """聚合各下载器实时速率与速度上限，反映真实带宽占用负载"""
        enabled = []
        stats: list[tuple[dict, dict]] = []
        for conf in (self._downloader.get_downloader_conf() or {}).values():
            if not conf.get("enabled"):
                continue
            enabled.append(conf)
            client = self._downloader.get_downloader(str(conf.get("id")))
            if not client:
                continue
            try:
                stat = client.get_transfer_statistics()
            except Exception as e:
                log.warn(f"[DownloadService]下载器 {conf.get('name')} 速率统计失败：{e}")
                stat = None
            if stat:
                stats.append((conf, stat))

        downloaders = [
            {
                "id": conf.get("id"),
                "name": conf.get("name"),
                "download_speed": int(stat.get("download_speed") or 0),
                "upload_speed": int(stat.get("upload_speed") or 0),
                "download_limit": stat.get("download_limit"),
                "upload_limit": stat.get("upload_limit"),
            }
            for conf, stat in stats
        ]

        if not stats:
            return {
                "online": False,
                "online_count": 0,
                "downloader_count": len(enabled),
                "download_speed": 0,
                "upload_speed": 0,
                "download_limit": None,
                "upload_limit": None,
                "downloaders": [],
            }

        download_speed = sum(int(s.get("download_speed") or 0) for _, s in stats)
        upload_speed = sum(int(s.get("upload_speed") or 0) for _, s in stats)
        # 全部在线下载器均配置了速度上限时才有可对比的占用比例
        dl_limits = [int(s["download_limit"]) for _, s in stats if s.get("download_limit")]
        ul_limits = [int(s["upload_limit"]) for _, s in stats if s.get("upload_limit")]
        return {
            "online": True,
            "online_count": len(stats),
            "downloader_count": len(enabled),
            "download_speed": download_speed,
            "upload_speed": upload_speed,
            "download_limit": sum(dl_limits) if len(dl_limits) == len(stats) else None,
            "upload_limit": sum(ul_limits) if len(ul_limits) == len(stats) else None,
            "downloaders": downloaders,
        }

    def _fill_torrent_info(self, torrent, media_info):
        """将 MediaInfo 回填到 torrent 字典"""
        year = media_info.year
        name = media_info.title or media_info.get_name()
        se = media_info.get_season_episode_string()
        poster = media_info.get_poster_image()
        poster = transform_display_image(
            str(getattr(media_info, "content_profile", "") or ""),
            poster,
        )
        if year:
            title = f"{name} ({year}) {se}"
        else:
            title = f"{name} {se}"
        torrent.update({"title": title, "image": poster or ""})

    # ---------- 索引器统计 ----------

    def get_indexer_statistics(self) -> tuple[list[IndexerStatisticsDTO], list[list]]:
        """
        获取索引器统计数据及 dataset
        :return: (统计数据列表, 图表数据集)
        """
        return self._indexer_service.get_indexer_statistics()

    # ---------- 删种任务 ----------

    def auto_remove_torrents(self, taskids=None) -> None:
        self._torrent_remover.auto_remove_torrents(taskids=taskids)

    def get_remove_torrents(self, taskid=None) -> list:
        return self._torrent_remover.get_remove_torrents(taskid=taskid)

    def get_torrent_remove_tasks(self, taskid=None):
        return self._torrent_remover.get_torrent_remove_tasks(taskid=taskid)

    def update_torrent_remove_task(self, data: dict) -> None:
        self._torrent_remover.update_torrent_remove_task(data=data)

    def delete_torrent_remove_task(self, taskid) -> None:
        self._torrent_remover.delete_torrent_remove_task(taskid=taskid)
