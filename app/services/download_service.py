"""
DownloadService - 下载编排业务层
将 web/controllers/download.py 中的下载业务逻辑下沉到可独立测试的 Service。
"""

import os

import log
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.infrastructure.cache_system import get_cache_manager
from app.media import MediaService
from app.media.models import MediaInfo
from app.schemas.download import (
    DownloadResultDTO,
    IndexerStatisticsDTO,
)
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.indexer_service import IndexerService
from app.services.search_service import Searcher
from app.services.torrentremover_core import TorrentRemoverService as TorrentRemover
from app.sites import Sites
from app.utils import Torrent
from app.utils.temp_manager import temp_manager
from app.utils.types import SearchType


class DownloadService:
    """
    下载编排业务服务
    负责：
    - 从搜索结果/链接/种子文件的下载编排
    - m-team/yemapt 特殊下载链接处理
    - 正在下载任务的媒体信息拼装
    - 索引器统计数据格式化
    """

    def __init__(
        self,
        downloader: Downloader | None = None,
        searcher: Searcher | None = None,
        media_service: MediaService | None = None,
        sites: Sites | None = None,
        indexer_service: IndexerService | None = None,
        torrent_remover: TorrentRemover | None = None,
    ):
        self._downloader = downloader or Downloader()
        self._searcher = searcher or Searcher()
        self._media = media_service or MediaService()
        self._sites = sites or Sites()
        self._indexer_service = indexer_service or IndexerService()
        self._torrent_remover = torrent_remover or TorrentRemover()

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
        self, dl_id: int, dl_dir: str, dl_setting: str, user_name: str
    ) -> DownloadResultDTO:
        """从搜索结果批量下载"""
        results = self._searcher.get_search_result_by_id(dl_id)
        if not results:
            return DownloadResultDTO(success=False, message="未找到搜索结果")

        for res in results:
            enclosure = self._resolve_download_url(res.PAGEURL, res.ENCLOSURE)
            media = self._media.get_media_info(title=res.TORRENT_NAME, subtitle=res.DESCRIPTION)
            if not media:
                # 识别失败时，用原始种子名创建最小 MediaInfo
                media = MediaInfo()
                media.title = res.TORRENT_NAME
            # 保存站点原始种子名，用于下载历史记录和后续识别
            media.org_string = res.TORRENT_NAME
            media.set_torrent_info(
                enclosure=enclosure,
                size=res.SIZE,
                site=res.SITE,
                page_url=res.PAGEURL,
                upload_volume_factor=float(res.UPLOAD_VOLUME_FACTOR),
                download_volume_factor=float(res.DOWNLOAD_VOLUME_FACTOR),
            )
            _, ret, ret_msg = self._downloader.download(
                media_info=media,
                download_dir=dl_dir,
                download_setting=dl_setting,
                in_from=SearchType.WEB,
                user_name=user_name,
            )
            if not ret:
                return DownloadResultDTO(success=False, message=ret_msg)
        return DownloadResultDTO(success=True, message="")

    def download_from_link(
        self,
        site: str,
        enclosure: str,
        title: str,
        description: str,
        page_url: str,
        size: str,
        seeders: str,
        uploadvolumefactor: str,
        downloadvolumefactor: str,
        dl_dir: str,
        dl_setting: str,
        user_name: str,
    ) -> DownloadResultDTO:
        """从下载链接添加下载"""
        enclosure = self._resolve_download_url(page_url, enclosure)
        if not title or not enclosure:
            return DownloadResultDTO(success=False, message="种子信息有误")

        media = self._media.get_media_info(title=title, subtitle=description)
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
        media.size = size
        media.upload_volume_factor = float(uploadvolumefactor)
        media.download_volume_factor = float(downloadvolumefactor)
        media.seeders = seeders

        _, ret, ret_msg = self._downloader.download(
            media_info=media,
            download_dir=dl_dir,
            download_setting=dl_setting,
            in_from=SearchType.WEB,
            user_name=user_name,
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
    ) -> DownloadResultDTO:
        """从种子文件或 URL 链接添加下载"""
        if not files and not urls:
            return DownloadResultDTO(success=False, message="没有种子文件或者种子链接")

        uploaded_files = []
        try:
            # 处理上传的种子文件
            for file_item in files:
                if not file_item:
                    continue
                file_name = file_item.get("upload", {}).get("filename")
                file_path = temp_manager.get_temp_path(file_name)
                uploaded_files.append(file_path)
                media_info = self._media.get_media_info(title=file_name)
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
                self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name,
                )

            # 处理 URL 链接
            if urls and not isinstance(urls, list):
                urls = [urls]
            for url in urls:
                if not url:
                    continue
                site_info = self._sites.get_sites(siteurl=url) or {}
                if not url.startswith("magnet:"):
                    file_path, _, _, _, retmsg = Torrent().get_torrent_info(
                        url=url,
                        cookie=site_info.get("cookie"),
                        ua=site_info.get("ua"),
                        proxy=site_info.get("proxy") or False,
                    )
                    if not file_path:
                        return DownloadResultDTO(success=False, message=f"下载种子文件失败： {retmsg}")
                    identify_title = title or os.path.basename(file_path)
                    media_info = self._media.get_media_info(title=identify_title, subtitle=description)
                    if not media_info:
                        media_info = MediaInfo()
                        media_info.title = identify_title
                    media_info.org_string = title or os.path.basename(file_path)
                    media_info.site = "WEB"
                else:
                    # magnet 链接：用前端传入的 title/description 识别
                    identify_title = title or url
                    media_info = self._media.get_media_info(title=identify_title, subtitle=description)
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

                self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name,
                )
        finally:
            # 清理上传的临时文件
            for tmp_file in uploaded_files:
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                        log.debug(f"【Web】已删除上传的临时文件: {tmp_file}")
                except Exception as e:
                    log.warn(f"【Web】删除上传的临时文件失败: {tmp_file}, {str(e)}")

        return DownloadResultDTO(success=True, message="添加下载完成！")

    # ---------- 正在下载任务（含媒体信息拼装） ----------

    def get_downloading_with_media_info(self) -> list[dict]:
        """
        获取正在下载的任务列表，并拼装媒体信息（标题、海报）
        """
        torrents = self._downloader.get_downloading_progress()
        default_downloader_id = self._downloader.default_downloader_id

        # 第一步：分两类，有 history 的直接用，没有的批量识别
        need_identify = []  # [(index, torrent, name)]
        for idx, torrent in enumerate(torrents):
            name = torrent.get("name")
            download_id = torrent.get("id")
            download_info = self._downloader.get_download_history_by_downloader(
                downloader=default_downloader_id, download_id=download_id
            )
            if download_info:
                year = download_info.YEAR
                se = download_info.SE
                display_name = download_info.TITLE
                poster = download_info.POSTER
                if year:
                    title = f"{display_name} ({year}) {se}"
                else:
                    title = f"{display_name} {se}"
                torrent.update({"title": title, "image": poster or ""})
            else:
                # 先查缓存
                cache_key = f"dl_task:{name}"
                _cache = get_cache_manager().get("media_info")
                cached = _cache.get(cache_key) if _cache else None
                if cached:
                    self._fill_torrent_info(torrent, cached)
                else:
                    need_identify.append((idx, torrent, name))

        # 第二步：批量识别（减少 API 调用）
        if need_identify:
            items = [{"title": name} for _, _, name in need_identify]
            results = self._media.identify_batch(items)
            for (_, torrent, name), media_info in zip(need_identify, results, strict=False):
                if not media_info or not media_info.title:
                    torrent.update({"title": name, "image": ""})
                    continue
                self._fill_torrent_info(torrent, media_info)
                # 写入缓存
                _cache = get_cache_manager().get("media_info")
                if _cache:
                    _cache.set(f"dl_task:{name}", media_info, ttl=300)
                # 写入下载历史，下次直接从 DB 查
                try:
                    DownloadHistoryRepositoryAdapter().insert_download_history(
                        media_info=media_info,
                        downloader=default_downloader_id,
                        download_id=torrent.get("id"),
                        save_dir=torrent.get("save_path") or "",
                    )
                except Exception as e:
                    log.debug(f"【DownloadService】写入下载历史失败：{e}")

        return torrents

    def _fill_torrent_info(self, torrent, media_info):
        """将 MediaInfo 回填到 torrent 字典"""
        year = media_info.year
        name = media_info.title or media_info.get_name()
        se = media_info.get_season_episode_string()
        poster = media_info.get_poster_image()
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

    def get_remove_torrents(self, taskid=None) -> tuple[bool, list | None]:
        return self._torrent_remover.get_remove_torrents(taskid=taskid)

    def get_torrent_remove_tasks(self, taskid=None):
        return self._torrent_remover.get_torrent_remove_tasks(taskid=taskid)

    def update_torrent_remove_task(self, data: dict) -> tuple[bool, str]:
        return self._torrent_remover.update_torrent_remove_task(data=data)

    def delete_torrent_remove_task(self, taskid) -> bool:
        return self._torrent_remover.delete_torrent_remove_task(taskid=taskid)
