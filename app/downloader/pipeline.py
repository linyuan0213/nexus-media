# -*- coding: utf-8 -*-
"""
下载流水线

将 download_core.py 中的 download() 拆分为清晰的阶段化流水线：
1. 种子获取（Fetch）   — 从 URL 或文件获取种子内容
2. 配置解析（Resolve） — 确定下载设置、标签、暂停状态
3. 添加任务（Add）     — 调用下载器添加任务
4. 后续处理（Post）    — 历史记录、字幕、消息

位于 app/downloader/ 层，不依赖 app/services/。
"""
import json
import os
import re
from typing import Optional, Tuple
from urllib.parse import urlsplit

import log
from app.core.constants import RMT_MEDIAEXT, PT_TAG
from app.downloader.client._base import _IDownloadClient
from app.helper import ThreadHelper
from app.media import MetaInfo
from app.mediaserver import MediaServer
from app.message import Message
from app.plugin_framework.event_compat import EventManager
from app.sites import Sites, SiteSubtitle, SiteConf
from app.sites.engine import SiteEngine
from app.utils import Torrent, StringUtils, ExceptionUtils, RequestUtils, JsonUtils
from app.utils.types import MediaType, DownloaderType, SearchType, EventType
from app.utils.config_tools import get_proxies


class DownloadPipeline:
    """
    下载流水线

    将下载过程拆分为四个独立的阶段，每个阶段可单独测试和维护。

    使用方式：
        pipeline = DownloadPipeline(client_factory=..., ...)
        downloader_id, download_id, error = pipeline.execute(media_info=..., ...)
    """

    def __init__(self,
                 client_factory=None,
                 message: Optional[Message] = None,
                 mediaserver: Optional[MediaServer] = None,
                 filetransfer=None,
                 sites: Optional[Sites] = None,
                 siteconf: Optional[SiteConf] = None,
                 sitesubtitle: Optional[SiteSubtitle] = None,
                 eventmanager: Optional[EventManager] = None):
        self._client_factory = client_factory
        self._message = message or Message()
        self._mediaserver = mediaserver or MediaServer()
        self._filetransfer = filetransfer
        self._sites = sites or Sites()
        self._siteconf = siteconf or SiteConf()
        self._sitesubtitle = sitesubtitle or SiteSubtitle()
        self._eventmanager = eventmanager or EventManager()

    def execute(self,
                media_info,
                is_paused=None,
                tag=None,
                download_dir=None,
                download_setting=None,
                downloader_id=None,
                upload_limit=None,
                download_limit=None,
                torrent_file=None,
                in_from=None,
                user_name=None,
                proxy=None) -> Tuple[Optional[str], Optional[str], str]:
        """
        执行完整下载流水线

        :return: (downloader_id, download_id, error_msg)
        """
        title = media_info.org_string or media_info.get_title_string() or media_info.title or "未知"

        self._eventmanager.send_event(EventType.DownloadAdd, {
            "media_info": media_info.to_dict(),
            "is_paused": is_paused, "tag": tag,
            "download_dir": download_dir, "download_setting": download_setting,
            "downloader_id": downloader_id, "torrent_file": torrent_file
        })

        # ---------- 阶段1：获取种子内容 ----------
        fetch = self._stage_fetch(media_info=media_info, torrent_file=torrent_file, proxy=proxy)
        if not fetch:
            return None, None, "下载链接为空"
        content, file_path, dl_files_folder, dl_files, retmsg, site_info, torrent_attr = fetch

        if retmsg:
            log.warn("【DownloadPipeline】%s" % retmsg)
        if not content:
            self._fail(media_info, in_from, retmsg)
            return None, None, retmsg

        # ---------- 阶段2：解析下载设置 ----------
        resolved = self._stage_resolve(
            media_info=media_info, download_setting=download_setting,
            downloader_id=downloader_id, tag=tag, is_paused=is_paused,
            site_info=site_info, torrent_attr=torrent_attr
        )
        download_attr = resolved["download_attr"]
        download_setting_name = download_attr.get('name')
        downloader_id = resolved["downloader_id"]
        tags = resolved["tags"]
        is_paused = resolved["is_paused"]
        upload_limit = upload_limit or download_attr.get("upload_limit")
        download_limit = download_limit or download_attr.get("download_limit")
        ratio_limit = download_attr.get("ratio_limit")
        seeding_time_limit = download_attr.get("seeding_time_limit")
        category = download_attr.get("category")

        downloader_conf = self._client_factory.get_downloader_conf(downloader_id)
        downloader = self._client_factory.get_client(downloader_id)
        if not downloader or not downloader_conf:
            msg = "请检查下载设置所选下载器是否有效且启用"
            self._fail(media_info, in_from, msg)
            return None, None, f"下载设置 {download_setting_name} 所选下载器失效"
        downloader_name = downloader_conf.get("name")

        if not download_dir:
            download_info = self._client_factory.get_download_dir_info(
                media_info, downloader_conf.get("download_dir"))
            download_dir = download_info.get('path')
            if not category:
                category = download_info.get('category')

        # ---------- 阶段3：添加任务 ----------
        download_id = self._stage_add(
            downloader=downloader, downloader_type=downloader.get_type(),
            content=content, title=title, is_paused=is_paused,
            download_dir=download_dir, tags=tags, category=category,
            upload_limit=upload_limit, download_limit=download_limit,
            ratio_limit=ratio_limit, seeding_time_limit=seeding_time_limit,
            cookie=site_info.get("cookie"), url=media_info.enclosure or torrent_file or ""
        )
        if not download_id:
            return downloader_id, None, f"下载器 {downloader_name} 添加下载任务失败"

        if downloader.get_type() == DownloaderType.QB and download_id == "EXISTS":
            return downloader_id, None, ""

        # ---------- 阶段4：后续处理 ----------
        self._stage_post(
            media_info=media_info, downloader_id=downloader_id,
            download_id=download_id, page_url=media_info.page_url,
            dl_files_folder=dl_files_folder, dl_files=dl_files,
            download_dir=download_dir, downloader_name=downloader_name,
            download_setting_name=download_setting_name,
            site_info=site_info, torrent_attr=torrent_attr,
            in_from=in_from, user_name=user_name,
        )

        if not media_info.enclosure and file_path:
            try:
                Torrent().delete_torrent_file(file_path)
            except Exception:
                pass

        return downloader_id, download_id, ""

    # ---------- 阶段1：种子获取 ----------

    def _stage_fetch(self, media_info, torrent_file=None, proxy=None):
        site_info, dl_files_folder, dl_files, retmsg = {}, "", [], ""
        torrent_attr = {}
        file_path = None
        content = None

        if torrent_file:
            content, dl_files_folder, dl_files, retmsg = Torrent().read_torrent_content(torrent_file)
            file_path = torrent_file
        else:
            url = media_info.enclosure
            if media_info.page_url and not media_info.enclosure:
                site_info = self._sites.get_sites(siteurl=media_info.page_url)
                url = SiteEngine.get_instance().resolve_download_url(
                    page_url=media_info.page_url,
                    user_config={
                        "cookie": site_info.get("cookie", ""),
                        "ua": site_info.get("ua", ""),
                        "headers": site_info.get("headers", {}),
                        "proxy": site_info.get("proxy"),
                    })
            if not url:
                return None
            if url.startswith("magnet:"):
                content = url
            else:
                site_info = self._sites.get_sites(siteurl=url)
                cookie = site_info.get("cookie")
                site_def = SiteEngine.get_instance().get_by_url(url)
                if site_def and site_def.api and site_def.api.auth.get("type") == "api_key":
                    cookie = None
                headers = site_info.get("headers")
                headers = json.loads(headers) if headers else {}
                if media_info.page_url and site_info.get("id"):
                    torrent_attr = self._siteconf.check_torrent_attr(
                        torrent_url=media_info.page_url,
                        cookie=cookie, ua=site_info.get("ua"),
                        headers=headers,
                        proxy=proxy if proxy is not None else site_info.get("proxy"))
                file_path, content, dl_files_folder, dl_files, retmsg = Torrent().get_torrent_info(
                    url=url, cookie=cookie, ua=site_info.get("ua"),
                    referer=media_info.page_url if not site_info.get("referer") else site_info.get("referer"),
                    proxy=proxy if proxy is not None else site_info.get("proxy"))

        return content, file_path, dl_files_folder, dl_files, retmsg, site_info, torrent_attr

    # ---------- 阶段2：配置解析 ----------

    def _stage_resolve(self, media_info, download_setting, downloader_id, tag,
                       is_paused, site_info, torrent_attr):
        if not download_setting and media_info.site:
            download_setting = self._sites.get_site_download_setting(media_info.site)
        if download_setting == "-2":
            download_attr = {}
        elif download_setting:
            download_attr = self._client_factory.get_download_setting(download_setting) \
                or self._client_factory.get_download_setting(self._client_factory.default_download_setting_id)
        else:
            download_attr = self._client_factory.get_download_setting(self._client_factory.default_download_setting_id)

        if not downloader_id:
            downloader_id = download_attr.get("downloader")

        tags = download_attr.get("tags")
        if tags:
            tags = str(tags).split(";")
            if tag:
                if isinstance(tag, list):
                    tags.extend(tag)
                else:
                    tags.append(tag)
        else:
            if tag:
                tags = tag if isinstance(tag, list) else [tag]
            else:
                tags = []
        if torrent_attr and torrent_attr.get('hr'):
            tags.append("HR")
        if site_info and site_info.get("tag"):
            tags.append(site_info.get("tag"))
        site_tag = site_info.get("tag") if site_info else None
        if tags:
            tags.sort(key=lambda x: (0 if x == "NASTOOL" else 1 if x == site_tag else 2, x))

        if is_paused is None:
            is_paused = StringUtils.to_bool(download_attr.get("is_paused"))
        else:
            is_paused = bool(is_paused)

        return {"download_attr": download_attr, "downloader_id": downloader_id,
                "tags": tags, "is_paused": is_paused}

    # ---------- 阶段3：添加任务 ----------

    def _stage_add(self, downloader, downloader_type, content, title,
                   is_paused, download_dir, tags, category,
                   upload_limit, download_limit, ratio_limit, seeding_time_limit,
                   cookie, url):
        print_url = content if isinstance(content, str) else url
        log.info(f"【DownloadPipeline】{'添加任务并暂停' if is_paused else '添加任务'}：%s，目录：%s，Url：%s"
                 % (title, download_dir, print_url))

        if downloader_type == DownloaderType.TR:
            ret = downloader.add_torrent(content, is_paused=is_paused,
                                         download_dir=download_dir, cookie=cookie)
            if ret:
                downloader.change_torrent(tid=ret.hashString, tag=tags,
                                          upload_limit=upload_limit, download_limit=download_limit,
                                          ratio_limit=ratio_limit, seeding_time_limit=seeding_time_limit)
                return ret.hashString
        elif downloader_type == DownloaderType.QB:
            exists, _ = downloader.check_torrent_exists(content)
            if exists:
                log.info("【DownloadPipeline】下载器中已存在该任务，跳过添加")
                return "EXISTS"
            torrent_tag = "NT" + StringUtils.generate_random_str(5)
            tags = tags + [torrent_tag] if tags else [torrent_tag]
            ret = downloader.add_torrent(content, is_paused=is_paused,
                                         download_dir=download_dir, tag=tags,
                                         category=category, content_layout="Original",
                                         upload_limit=upload_limit, download_limit=download_limit,
                                         ratio_limit=ratio_limit, seeding_time_limit=seeding_time_limit,
                                         cookie=cookie)
            if ret:
                download_id = downloader.get_torrent_id_by_tag(torrent_tag)
                if not download_id:
                    _, torrent_hash = downloader.check_torrent_exists(content)
                    if torrent_hash:
                        return "EXISTS"
                    log.warn("【DownloadPipeline】下载器添加任务成功但无法获取任务ID")
                    return None
                return download_id
        else:
            ret = downloader.add_torrent(content, is_paused=is_paused,
                                         tag=tags, download_dir=download_dir, category=category)
            if ret:
                return ret
        return None

    # ---------- 阶段4：后续处理 ----------

    def _stage_post(self, media_info, downloader_id, download_id, page_url,
                    dl_files_folder, dl_files, download_dir, downloader_name,
                    download_setting_name, site_info, torrent_attr, in_from, user_name):
        if not self._client_factory:
            return

        visit_dir = self._client_factory.get_download_visit_dir(download_dir)
        save_dir = subtitle_dir = None
        if visit_dir:
            if dl_files_folder:
                save_dir = os.path.join(visit_dir, dl_files_folder)
                subtitle_dir = save_dir
            elif dl_files:
                save_dir = os.path.join(visit_dir, dl_files[0])
                subtitle_dir = visit_dir
            elif media_info.enclosure and media_info.enclosure.startswith("magnet:"):
                save_dir = None
                subtitle_dir = visit_dir
            else:
                save_dir = None
                subtitle_dir = visit_dir
                downloader = self._client_factory.get_client(downloader_id)
                if downloader:
                    downloader.delete_torrents(ids=download_id, delete_file=True)
                self._fail(media_info, in_from, "请检查下载任务保存目录是否正确")
                return

        from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
        DownloadHistoryRepositoryAdapter().insert_download_history(
            media_info=media_info, downloader=downloader_id,
            download_id=download_id, save_dir=save_dir)

        if page_url and subtitle_dir and site_info and site_info.get("subtitle"):
            ThreadHelper().start_thread(
                self._sitesubtitle.download,
                (media_info, site_info.get("id"), site_info.get("cookie"),
                 site_info.get("ua"), subtitle_dir))

        if in_from:
            media_info.user_name = user_name
            media_info.hit_and_run = bool(torrent_attr and torrent_attr.get('hr'))
            self._message.send_download_message(
                in_from=in_from, can_item=media_info,
                download_setting_name=download_setting_name, downloader_name=downloader_name)

    # ---------- 辅助 ----------

    def _fail(self, media_info, in_from, reason):
        self._eventmanager.send_event(EventType.DownloadFail, {
            "media_info": media_info.to_dict(), "reason": reason})
        if in_from:
            self._message.send_download_fail_message(media_info, f"添加下载任务失败：{reason}")
