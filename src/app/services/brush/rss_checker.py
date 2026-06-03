"""Brush RSS checker - RSS 刷流选种逻辑."""

import json
from typing import Any

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.db.repositories.subscribe_repo_adapter import SubscribeMovieRepositoryAdapter, SubscribeTvRepositoryAdapter
from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.services.rss_processor import RssHelper
from app.media.factory import get_media_service
from app.sites import SiteConf, Sites
from app.utils import ExceptionUtils, JsonUtils


class BrushRssChecker:
    """
    RSS 刷流选种检查器
    职责：解析 RSS、检查选种规则、触发下载。
    """

    def __init__(
        self,
        helper,
        rsshelper: RssHelper | None = None,
        sites: Sites | None = None,
        siteconf: SiteConf | None = None,
        torrents_cache: set | None = None,
    ):
        self._helper = helper
        self._rsshelper = rsshelper or RssHelper()
        self._sites = sites or Sites()
        self._siteconf = siteconf or SiteConf()
        self._torrents_cache = torrents_cache or set()

    @staticmethod
    def _rss_rule_needs_torrent_attr(rss_rule: dict) -> bool:
        """判断 RSS 选种规则是否需要解析种子详情页属性。"""
        if not rss_rule:
            return False
        for key in ("free", "hr", "peercount"):
            val = rss_rule.get(key)
            if val and val not in ("#", "N", None, ""):
                return True
        return False

    def _check_torrent_attr_if_needed(
        self,
        rss_rule: dict,
        page_url: str | None,
        cookie: str | None,
        ua: str | None,
        headers: dict,
        site_proxy: bool,
    ) -> dict:
        """仅在规则需要时解析种子详情页属性，避免无意义请求。"""
        if not self._rss_rule_needs_torrent_attr(rss_rule):
            return {}
        if not page_url:
            return {}
        return self._siteconf.check_torrent_attr(
            torrent_url=page_url, cookie=cookie, ua=ua, headers=headers, proxy=site_proxy
        )

    def check_task_rss(self, taskid: int | None, taskinfo: dict) -> None:
        if not taskid or not taskinfo:
            return

        task_name = taskinfo.get("name")
        site_id = taskinfo.get("site_id")
        rss_url = taskinfo.get("rss_url")
        rss_rule = taskinfo.get("rss_rule") or {}
        cookie = taskinfo.get("cookie")
        rss_free = taskinfo.get("free")
        downloader_id = taskinfo.get("downloader")
        ua = taskinfo.get("ua")
        headers = taskinfo.get("headers")
        if headers and JsonUtils.is_valid_json(headers):
            headers = json.loads(headers)
        else:
            headers = {}
        headers.update({"User-Agent": ua})
        if taskinfo.get("state") != "Y":
            log.info(f"[Brush]刷流任务 {task_name} 已停止下载新种！")
            return

        site_info: Any = self._sites.get_sites(siteid=site_id)
        if not site_info:
            log.error(f"[Brush]刷流任务 {task_name} 的站点已不存在，无法刷流！")
            return

        site_id = site_info.get("id")
        site_name = site_info.get("name")
        site_proxy = site_info.get("proxy")
        if not site_info.get("brush_enable"):
            log.error(f"[Brush]站点 {site_name} 未开启刷流功能，无法刷流！")
            return
        if not rss_url:
            log.error(f"[Brush]站点 {site_name} 未配置RSS订阅地址，无法刷流！")
            return
        if rss_free and (not cookie and not taskinfo.get("headers")):
            log.warn(f"[Brush]站点 {site_name} 未配置Cookie或请求头，无法开启促销刷流")
            return

        if not self._helper._downloader.get_downloader_conf(downloader_id):
            log.error(f"[Brush]任务 {task_name} 下载器不存在，无法刷流！")
            return

        log.info(f"[Brush]开始站点 {site_name} 的刷流任务：{task_name}...")
        if not self._helper.is_allow_new_torrent(taskinfo=taskinfo, dlcount=rss_rule.get("dlcount")):
            log.error(f"[Brush]站点 {site_name} 未开启刷流功能，无法刷流！")
            return
        if not rss_url:
            log.error(f"[Brush]站点 {site_name} 未配置RSS订阅地址，无法刷流！")
            return
        if rss_free and (not cookie and not taskinfo.get("headers")):
            log.warn(f"[Brush]站点 {site_name} 未配置Cookie或请求头，无法开启促销刷流")
            return

        if not self._helper._downloader.get_downloader_conf(downloader_id):
            log.error(f"[Brush]任务 {task_name} 下载器不存在，无法刷流！")
            return

        log.info(f"[Brush]开始站点 {site_name} 的刷流任务：{task_name}...")
        if not self._helper.is_allow_new_torrent(taskinfo=taskinfo, dlcount=rss_rule.get("dlcount")):
            return

        rss_result = self._rsshelper.parse_rssxml(url=rss_url, proxy=bool(site_proxy))
        if rss_result is None:
            log.error(f"[Brush]{task_name} RSS链接已过期，请重新获取！")
            return
        if len(rss_result) == 0:
            log.warn(f"[Brush]{site_name} RSS未下载到数据")
            return

        max_dlcount = rss_rule.get("dlcount")
        success_count = 0
        new_torrent_count = 0
        if max_dlcount:
            downloading_count = self._helper.get_downloading_count(downloader_id) or 0
            new_torrent_count = int(max_dlcount) - int(downloading_count)

        # 预加载订阅数据（用于 exclude_subscribe 规则）
        rss_movies = None
        rss_tvs = None
        if rss_rule and rss_rule.get("exclude_subscribe") not in ("#", "N", None, ""):
            rss_movies = {
                m.id: {"name": m.name, "year": m.year, "tmdbid": m.tmdbid, "fuzzy_match": m.fuzzy_match}
                for m in SubscribeMovieRepositoryAdapter().get_all(state="R")
            }
            rss_tvs = {
                t.id: {
                    "name": t.name,
                    "year": t.year,
                    "tmdbid": t.tmdbid,
                    "fuzzy_match": t.fuzzy_match,
                    "season": t.season,
                    "rss_sites": t.rss_sites,
                }
                for t in SubscribeTvRepositoryAdapter().get_all(state="R")
            }

        media_service = get_media_service()

        for res in rss_result:
            try:
                torrent_name = res.get("title")
                enclosure = res.get("enclosure")
                page_url = res.get("link")
                size = res.get("size")
                pubdate = res.get("pubdate")

                if enclosure not in self._torrents_cache:
                    if len(self._torrents_cache) >= 10000:
                        self._torrents_cache = set(list(self._torrents_cache)[5000:])
                    self._torrents_cache.add(enclosure)
                else:
                    log.debug(f"[Brush]{torrent_name} 已处理过")
                    continue

                torrent_attr = self._check_torrent_attr_if_needed(
                    rss_rule=rss_rule,
                    page_url=page_url,
                    cookie=cookie,
                    ua=ua,
                    headers=headers,
                    site_proxy=bool(site_proxy),
                )

                # 识别媒体信息（用于 exclude_subscribe 规则）
                media_info = None
                if rss_movies is not None or rss_tvs is not None:
                    media_info = media_service.get_media_info(title=torrent_name)

                if not BrushRuleEngine.check_rss_rule(
                    rss_rule=rss_rule,
                    title=torrent_name,
                    torrent_size=size,
                    pubdate=pubdate,
                    torrent_attr=torrent_attr,
                    media_info=media_info,
                    rss_movies=rss_movies,
                    rss_tvs=rss_tvs,
                ):
                    continue
                if not self._helper.is_allow_new_torrent(taskinfo=taskinfo, dlcount=max_dlcount, torrent_size=size):
                    continue
                if self._helper.is_torrent_handled(enclosure=enclosure):
                    log.info(f"[Brush]{torrent_name} 已在刷流任务中")
                    continue

                if self._helper.download_torrent(
                    taskinfo, rss_rule, site_info, torrent_name, enclosure, size, page_url
                ):
                    success_count += 1
                    if max_dlcount and success_count >= new_torrent_count:
                        break
                    if not self._helper.is_allow_new_torrent(taskinfo=taskinfo, dlcount=max_dlcount):
                        break
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue
        log.info(f"[Brush]任务 {task_name} 本次添加了 {success_count} 个下载")
