# -*- coding: utf-8 -*-
"""
DownloadService - 下载编排业务层
将 web/controllers/download.py 中的下载业务逻辑下沉到可独立测试的 Service。
"""
import os
from typing import List, Optional, Tuple

import log
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.indexer_service import IndexerService
from app.media import Media
from app.media.meta import MetaInfo
from app.schemas.download import (
    DownloadResultDTO,
    DownloadingTorrentDTO,
    IndexerStatisticsDTO,
)
from app.services.search_service import Searcher
from app.sites import Sites
from app.services.torrentremover_core import TorrentRemoverService as TorrentRemover
from app.utils import ExceptionUtils, Torrent
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

    def __init__(self,
                 downloader: Optional[Downloader] = None,
                 searcher: Optional[Searcher] = None,
                 media: Optional[Media] = None,
                 sites: Optional[Sites] = None,
                 indexer_service: Optional[IndexerService] = None,
                 torrent_remover: Optional[TorrentRemover] = None):
        self._downloader = downloader or Downloader()
        self._searcher = searcher or Searcher()
        self._media = media or Media()
        self._sites = sites or Sites()
        self._indexer_service = indexer_service or IndexerService()
        self._torrent_remover = torrent_remover or TorrentRemover()

    # ---------- 下载编排 ----------

    def _resolve_download_url(self, page_url: str, enclosure: Optional[str]) -> str:
        """处理 m-team/yemapt 特殊下载链接"""
        if ('m-team' in page_url or 'yemapt' in page_url) and not enclosure:
            return self._downloader.get_download_url(page_url) or ""
        return enclosure or ""

    def download_from_search_results(self, dl_id: int, dl_dir: str, dl_setting: str,
                                      user_name: str) -> DownloadResultDTO:
        """从搜索结果批量下载"""
        results = self._searcher.get_search_result_by_id(dl_id)
        if not results:
            return DownloadResultDTO(success=False, message="未找到搜索结果")

        for res in results:
            enclosure = self._resolve_download_url(res.PAGEURL, res.ENCLOSURE)
            media = self._media.get_media_info(title=res.TORRENT_NAME, subtitle=res.DESCRIPTION)
            if not media:
                continue
            media.set_torrent_info(
                enclosure=enclosure,
                size=res.SIZE,
                site=res.SITE,
                page_url=res.PAGEURL,
                upload_volume_factor=float(res.UPLOAD_VOLUME_FACTOR),
                download_volume_factor=float(res.DOWNLOAD_VOLUME_FACTOR)
            )
            _, ret, ret_msg = self._downloader.download(
                media_info=media,
                download_dir=dl_dir,
                download_setting=dl_setting,
                in_from=SearchType.WEB,
                user_name=user_name
            )
            if not ret:
                return DownloadResultDTO(success=False, message=ret_msg)
        return DownloadResultDTO(success=True, message="")

    def download_from_link(self, site: str, enclosure: str, title: str,
                           description: str, page_url: str, size: str,
                           seeders: str, uploadvolumefactor: str,
                           downloadvolumefactor: str, dl_dir: str,
                           dl_setting: str, user_name: str) -> DownloadResultDTO:
        """从下载链接添加下载"""
        enclosure = self._resolve_download_url(page_url, enclosure)
        if not title or not enclosure:
            return DownloadResultDTO(success=False, message="种子信息有误")

        media = self._media.get_media_info(title=title, subtitle=description)
        if not media:
            return DownloadResultDTO(success=False, message="媒体信息识别失败")

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
            user_name=user_name
        )
        if not ret:
            return DownloadResultDTO(success=False,
                                     message=ret_msg or "如连接正常，请检查下载任务是否存在")
        return DownloadResultDTO(success=True, message="下载成功")

    def download_from_torrent_files_or_urls(self, files: list, urls: list,
                                            dl_dir: str, dl_setting: str,
                                            user_name: str) -> DownloadResultDTO:
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
                if media_info:
                    media_info.site = "WEB"
                self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name
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
                        proxy=site_info.get("proxy") or False
                    )
                    if not file_path:
                        return DownloadResultDTO(success=False,
                                                  message=f"下载种子文件失败： {retmsg}")
                    media_info = self._media.get_media_info(title=os.path.basename(file_path))
                    if media_info:
                        media_info.site = "WEB"
                else:
                    media_info = MetaInfo('')
                    media_info.enclosure = url
                    file_path = None

                self._downloader.download(
                    media_info=media_info,
                    download_dir=dl_dir,
                    download_setting=dl_setting,
                    torrent_file=file_path,
                    in_from=SearchType.WEB,
                    user_name=user_name
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

    def get_downloading_with_media_info(self) -> List[dict]:
        """
        获取正在下载的任务列表，并拼装媒体信息（标题、海报）
        """
        torrents = self._downloader.get_downloading_progress()
        default_downloader_id = self._downloader.default_downloader_id

        for torrent in torrents:
            name = torrent.get("name")
            download_info = self._downloader.get_download_history_by_downloader(
                downloader=default_downloader_id,
                download_id=torrent.get("id")
            )
            if download_info:
                name = download_info.TITLE
                year = download_info.YEAR
                poster_path = download_info.POSTER
                se = download_info.SE
            else:
                media_info = self._media.get_media_info(title=name)
                if not media_info:
                    torrent.update({"title": name, "image": ""})
                    continue
                year = media_info.year
                name = media_info.title or media_info.get_name()
                se = media_info.get_season_episode_string()
                poster_path = media_info.get_poster_image()

            if year:
                title = "%s (%s) %s" % (name, year, se)
            else:
                title = "%s %s" % (name, se)

            torrent.update({"title": title, "image": poster_path or ""})

        return torrents

    # ---------- 索引器统计 ----------

    def get_indexer_statistics(self) -> Tuple[List[IndexerStatisticsDTO], List[list]]:
        """
        获取索引器统计数据及 dataset
        :return: (统计数据列表, 图表数据集)
        """
        return self._indexer_service.get_indexer_statistics()

    # ---------- 删种任务 ----------

    def auto_remove_torrents(self, taskids=None) -> None:
        self._torrent_remover.auto_remove_torrents(taskids=taskids)

    def get_remove_torrents(self, taskid=None) -> Tuple[bool, Optional[list]]:
        return self._torrent_remover.get_remove_torrents(taskid=taskid)

    def get_torrent_remove_tasks(self, taskid=None):
        return self._torrent_remover.get_torrent_remove_tasks(taskid=taskid)

    def update_torrent_remove_task(self, data: dict) -> Tuple[bool, str]:
        return self._torrent_remover.update_torrent_remove_task(data=data)

    def delete_torrent_remove_task(self, taskid) -> bool:
        return self._torrent_remover.delete_torrent_remove_task(taskid=taskid)
