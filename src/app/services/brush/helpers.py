"""Brush helpers - 刷流任务共享辅助方法."""

import ast
import json
import time
from datetime import datetime
from datetime import time as dtime
from typing import Any
from urllib.parse import urlsplit

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.media import meta_info
from app.message import Message
from app.sites import SiteConf
from app.sites.engine import SiteEngine, get_tid_by_url
from app.sites.site_cache import SiteCache
from app.utils import JsonUtils, StringUtils


class BrushTaskHelper:
    """
    刷流任务辅助工具类
    封装 RSS 检查、删种、停种等子流程共享的辅助方法。
    """

    def __init__(
        self,
        repo,
        downloader,
        sites: "SiteCache",
        siteconf: SiteConf,
        message: Message,
        site_engine: SiteEngine,
    ):
        self._repo: Any = repo
        self._downloader: Any = downloader
        self._sites = sites
        self._siteconf = siteconf
        self._message: Message = message
        self._site_engine = site_engine

    @staticmethod
    def parse_json_rule(val, default=None):
        """安全解析规则字段，兼容 Python 单引号字典格式"""
        if default is None:
            default = {}
        if not val:
            return default
        val = str(val).strip()
        if not val or val in ("''", '""', "'", '"'):
            return default
        try:
            return json.loads(val)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            pass
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            inner = val[1:-1]
            try:
                return json.loads(inner)
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception:
                pass
            try:
                return json.loads(ast.literal_eval(inner))
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception:
                pass
        try:
            return json.loads(ast.literal_eval(val))
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            pass
        return default

    @staticmethod
    def is_in_time_range(time_range: str = ""):
        if not time_range.strip():
            return True
        try:
            periods = time_range.split(",")
            for period in periods:
                start_str, end_str = period.split("-")
                start_hour, start_minute = map(int, start_str.split(":"))
                end_hour, end_minute = map(int, end_str.split(":"))
                start_time = dtime(start_hour, start_minute)
                end_time = dtime(end_hour, end_minute)
                now = datetime.now().time()
                if start_time < end_time:
                    if start_time <= now <= end_time:
                        return True
                else:
                    if now >= start_time or now <= end_time:
                        return True
            return False
        except ValueError:
            log.warn("[Brush]时间段格式错误，应为 'HH:MM-HH:MM'")
            return False

    def _get_site_engine(self):
        return self._site_engine

    def is_torrent_handled(self, enclosure: str | None) -> bool:
        if not enclosure:
            return False
        engine = self._get_site_engine()
        if engine.is_tid_based_dedup(enclosure):
            tid = get_tid_by_url(enclosure, site_engine=engine)
            domain = engine.normalize_domain(enclosure)
            all_torrents = self._repo.get_brushtask_torrents_by_domain(domain)
            return any(get_tid_by_url(t.ENCLOSURE, site_engine=engine) == tid for t in all_torrents)
        return self._repo.get_brushtask_torrent_by_enclosure(enclosure) is not None

    def get_torrent_attr(self, site_info: dict, enclosure: str):
        if not site_info:
            return None, {}
        ua = site_info.get("ua")
        headers = site_info.get("headers")
        if JsonUtils.is_valid_json(headers):
            headers = json.loads(str(headers))
        else:
            headers = {}
        headers.update({"User-Agent": ua})
        site_proxy = site_info.get("proxy")
        site_cookie = site_info.get("cookie")
        split_url = urlsplit(site_info.get("rssurl"))
        site_base_url = f"{split_url.scheme}://{split_url.netloc}"

        engine = self._get_site_engine()
        tid = get_tid_by_url(enclosure, site_engine=engine)
        torrent_url = f"{site_base_url}{engine.resolve_detail_url(enclosure, tid or '')}"

        torrent_attr = self._siteconf.check_torrent_attr(
            torrent_url=torrent_url, cookie=site_cookie, ua=ua, headers=headers, proxy=bool(site_proxy)
        )
        return torrent_url, torrent_attr

    def is_allow_new_torrent(self, taskinfo, dlcount, torrent_size=None):
        if not taskinfo:
            return False
        seed_size = taskinfo.get("seed_size") or None
        time_range = taskinfo.get("time_range") or ""
        task_name = taskinfo.get("name")
        downloader_id = taskinfo.get("downloader")
        downloader_name = taskinfo.get("downloader_name")
        total_size = self._repo.get_brushtask_totalsize(taskinfo.get("id"))

        if torrent_size and seed_size:
            if float(torrent_size) + int(total_size) >= (float(seed_size) + 5) * 1024**3:
                log.warn(
                    f"[Brush]刷流任务 {task_name} 当前保种体积 {round(int(total_size) / (1024**3), 1)}GB，"
                    f"种子大小 {round(int(torrent_size) / (1024**3), 1)}GB，不添加刷流任务"
                )
                return False
        if seed_size:
            if float(seed_size) * 1024**3 <= int(total_size):
                log.warn(
                    f"[Brush]刷流任务 {task_name} 当前保种体积 {round(int(total_size) / 1024 / 1024 / 1024, 1)}GB，不再新增下载"
                )
                return False

        if dlcount:
            downloading_count = self.get_downloading_count(downloader_id)
            if downloading_count is None:
                log.error(f"[Brush]任务 {task_name} 下载器 {downloader_name} 无法连接")
                return False
            if int(downloading_count) >= int(dlcount):
                log.warn(
                    f"[Brush]下载器 {downloader_name} 正在下载任务数：{downloading_count}，超过设定上限，暂不添加下载"
                )
                return False

        if not self.is_in_time_range(time_range=time_range):
            log.warn(f"[Brush]任务 {task_name} 不在所选时间段 {time_range} 内，暂不添加下载")
            return False
        return True

    def get_downloading_count(self, downloader_id):
        torrents = self._downloader.get_downloading_torrents(downloader_id=downloader_id) or []
        return len(torrents)

    def download_torrent(self, taskinfo, rss_rule, site_info, title, enclosure, size, page_url):
        if not enclosure:
            return False
        if self._sites.check_ratelimit(site_info.get("id")):
            return False

        taskid = taskinfo.get("id")
        taskname = taskinfo.get("name")
        transfer = taskinfo.get("transfer")
        sendmessage = taskinfo.get("sendmessage")
        downloader_id = taskinfo.get("downloader")
        download_limit = rss_rule.get("downspeed")
        upload_limit = rss_rule.get("upspeed")
        download_dir = taskinfo.get("savepath")

        hr_tag = []
        if rss_rule.get("hr"):
            _, torrent_attr = self.get_torrent_attr(site_info, enclosure)
            if torrent_attr.get("hr"):
                hr_tag = ["HR"]
        tag = taskinfo.get("label").split(",") if taskinfo.get("label") else []
        if not transfer:
            tag = tag + ["已整理"] + hr_tag if tag else ["已整理"] + hr_tag

        mi = meta_info(title=title)
        mi.set_torrent_info(site=site_info.get("name"), enclosure=enclosure, size=size)
        _, download_id, retmsg = self._downloader.download(
            media_info=mi,
            tag=tag,
            downloader_id=downloader_id,
            download_dir=download_dir,
            download_setting="-2",
            download_limit=download_limit,
            upload_limit=upload_limit,
        )
        if not download_id:
            log.warn(
                f"[Brush]{taskname} 添加下载任务出错：{title}，"
                f"错误原因：{retmsg or '下载器添加任务失败'}，"
                f"种子链接：{enclosure}"
            )
            return False
        else:
            log.info(f"[Brush]成功添加下载：{title}")
            if sendmessage:
                downloader_cfg = self._downloader.get_downloader_conf(downloader_id)
                downlaod_name = downloader_cfg.get("name") if downloader_cfg else ""
                msg_title = f"[刷流任务 {taskname} 新增下载]"
                msg_text = (
                    f"下载器名：{downlaod_name}\n"
                    f"种子名称：{title}\n"
                    f"种子大小：{StringUtils.str_filesize(size)}\n"
                    f"添加时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                )
                self._message.send_brushtask_added_message(title=msg_title, text=msg_text)

        if self._repo.insert_brushtask_torrent(
            brush_id=taskid,
            title=title,
            enclosure=enclosure,
            downloader=downloader_id,
            download_id=download_id,
            size=size,
        ):
            self._repo.add_brushtask_download_count(brush_id=taskid)
        else:
            log.info(f"[Brush]{title} 已下载过")
        return True
