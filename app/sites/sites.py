import json
from datetime import datetime

import log
from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
from app.helper import DrissionPageHelper, SiteHelper
from app.sites.engine import SiteEngine
from app.sites.site_limiter import SiteRateLimiter
from app.utils import JsonUtils, RequestUtils, StringUtils
from app.utils.config_tools import get_proxies, get_ua


class Sites:
    site_repo = None

    _sites = []
    _siteByIds = {}
    _siteByUrls = {}
    _site_favicons = {}
    _rss_sites = []
    _brush_sites = []
    _statistic_sites = []
    _signin_sites = []
    _limiters = {}

    _MAX_CONCURRENCY = 10

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.site_repo = SiteRepositoryAdapter()
        # 原始站点列表
        self._sites = []
        # ID存储站点
        self._siteByIds = {}
        # URL存储站点
        self._siteByUrls = {}
        # 开启订阅功能站点
        self._rss_sites = []
        # 开启刷流功能站点：
        self._brush_sites = []
        # 开启统计功能站点：
        self._statistic_sites = []
        # 开启签到功能站点：
        self._signin_sites = []
        # 站点限速器
        self._limiters = {}
        # 站点图标
        self.init_favicons()
        # 站点数据
        self._sites = self.site_repo.get_config_site()
        for site in self._sites:
            # 站点属性
            site_note: dict = self.__get_site_note_items(site.NOTE)  # type: ignore[attr-defined]
            # 站点用途：Q签到、D订阅、S刷流
            site_rssurl = site.RSSURL
            site_signurl = site.SIGNURL
            site_cookie = site.COOKIE
            site_uses = site.INCLUDE or ""
            site_headers = site_note.get("headers")
            uses = []
            if site_uses:
                rss_enable = True if "D" in site_uses and site_rssurl else False
                brush_enable = True if "S" in site_uses and site_rssurl and (site_cookie or site_headers) else False
                statistic_enable = (
                    True
                    if "T" in site_uses and (site_rssurl or site_signurl) and (site_cookie or site_headers)
                    else False
                )
                uses.append("D") if rss_enable else None
                uses.append("S") if brush_enable else None
                uses.append("T") if statistic_enable else None
            else:
                rss_enable = False
                brush_enable = False
                statistic_enable = False
            strict_url = ""
            site_def = SiteEngine.get_instance().get_by_url(site_signurl or site_rssurl or "")
            if site_def and site_def.api:
                strict_url = site_def.api.base_url
            else:
                strict_url = StringUtils.get_base_url(site_signurl or site_rssurl)

            # 判断是否为公开站点（BT站点）
            # 公开站点的判断逻辑：没有signurl和cookie，或者明确标记为public
            is_public = False
            if not site_signurl and not site_cookie:
                is_public = True
            if site_note.get("public") == "Y":
                is_public = True
            if site_note.get("public") == "N":
                is_public = False

            site_info = {
                "id": site.ID,
                "name": site.NAME,
                "pri": site.PRI or 0,
                "rssurl": site_rssurl,
                "signurl": site_signurl,
                "cookie": site_cookie,
                "rule": site_note.get("rule"),
                "download_setting": site_note.get("download_setting"),
                "rss_enable": rss_enable,
                "brush_enable": brush_enable,
                "statistic_enable": statistic_enable,
                "uses": uses,
                "ua": site_note.get("ua") or get_ua(),
                "headers": site_note.get("headers"),
                "parse": True if site_note.get("parse") == "Y" else False,
                "unread_msg_notify": True if site_note.get("message") == "Y" else False,
                "chrome": True if site_note.get("chrome") == "Y" else False,
                "proxy": True if site_note.get("proxy") == "Y" else False,
                "subtitle": True if site_note.get("subtitle") == "Y" else False,
                "limit_interval": site_note.get("limit_interval"),
                "limit_count": site_note.get("limit_count"),
                "limit_seconds": site_note.get("limit_seconds"),
                "strict_url": strict_url,
                "tag": site.NAME if site_note.get("tag") == "Y" else "",
                "public": is_public,
            }
            # 以ID存储
            self._siteByIds[site.ID] = site_info
            # 以域名存储
            site_def = SiteEngine.get_instance().get_by_url(site.SIGNURL or site.RSSURL or "")
            if site_def and site_def.api:
                site_strict_url = StringUtils.get_url_domain(site_def.api.base_url)
            else:
                site_strict_url = StringUtils.get_url_domain(site.SIGNURL or site.RSSURL)
            if site_strict_url:
                self._siteByUrls[site_strict_url] = site_info
            # 初始化站点限速器
            self._limiters[site.ID] = SiteRateLimiter(
                limit_interval=Sites._rate_limit_val(
                    site_note, "limit_interval", multiplier=60, require_fields=["limit_count"]
                ),
                limit_count=Sites._rate_limit_val(site_note, "limit_count", require_fields=["limit_interval"]),
                limit_seconds=Sites._rate_limit_val(site_note, "limit_seconds"),
            )

    def init_favicons(self):
        """
        加载图标到内存
        """
        self._site_favicons = {site.SITE: site.FAVICON for site in self.site_repo.get_site_favicons()}

    def get_sites(self, siteid=None, siteurl=None, siteids=None, rss=False, brush=False, statistic=False, public=False):
        """
        获取站点配置
        """
        if siteid:
            return self._siteByIds.get(int(siteid)) or {}
        if siteurl:
            site_def = SiteEngine.get_instance().get_by_url(siteurl)
            if site_def and site_def.api:
                siteurl = site_def.api.base_url
            return self._siteByUrls.get(StringUtils.get_url_domain(siteurl)) or {}

        ret_sites = []
        for site in self._siteByIds.values():
            if rss and not site.get("rss_enable"):
                continue
            if brush and not site.get("brush_enable"):
                continue
            if statistic and not site.get("statistic_enable"):
                continue
            if not public and site.get("public"):
                continue
            if siteids and str(site.get("id")) not in siteids:
                continue
            ret_sites.append(site)
        if siteid or siteurl:
            return {}
        return ret_sites

    def check_ratelimit(self, site_id):
        """
        检查站点是否触发流控
        :param site_id: 站点ID
        :return: True为触发了流控，False为未触发
        """
        if not self._limiters.get(site_id):
            return False
        state, msg = self._limiters[site_id].check_rate_limit()
        if msg:
            log.warn(f"【Sites】站点 {self._siteByIds[site_id].get('name')} {msg}")
        return state

    def get_sites_by_suffix(self, suffix):
        """
        根据url的后缀获取站点配置
        """
        for key in self._siteByUrls:
            # 使用.分割后再将最后两位(顶级域和二级域)拼起来
            key_parts = key.split(".")
            key_end = ".".join(key_parts[-2:])
            # 将拼起来的结果与参数进行对比
            if suffix == key_end:
                return self._siteByUrls[key]
        return {}

    def get_sites_by_name(self, name):
        """
        根据站点名称获取站点配置
        """
        ret_sites = []
        for site in self._siteByIds.values():
            if site.get("name") == name:
                ret_sites.append(site)
        return ret_sites

    def get_max_site_pri(self):
        """
        获取最大站点优先级
        """
        if not self._siteByIds:
            return 0
        return max([int(site.get("pri")) for site in self._siteByIds.values()])

    def get_site_dict(self, rss=False, brush=False, statistic=False, signin=False):
        """
        获取站点字典
        :param signin: 是否为签到用途，True时过滤掉BT站点（公开站点）
        """
        return [
            {"id": site.get("id"), "name": site.get("name")}
            for site in self.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)
            if not (signin and site.get("public"))
        ]

    def get_site_names(self, rss=False, brush=False, statistic=False):
        """
        获取站点名称
        """
        return [site.get("name") for site in self.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)]

    def get_site_favicon(self, site_name=None):
        if site_name:
            return self._resolve_favicon(site_name)
        result = dict(self._site_favicons)
        for site in self._siteByIds.values():
            name = site.get("name")
            if name and name not in result:
                url = self._favicon_fallback_url(site)
                if url:
                    result[name] = url
        for site_def in SiteEngine.get_instance().all_sites():
            if site_def.favicon and site_def.name not in result:
                result[site_def.name] = site_def.favicon
        return result

    def _resolve_favicon(self, site_name):
        data = self._site_favicons.get(site_name)
        if data:
            return data
        for site in self._siteByIds.values():
            if site.get("name") == site_name:
                return self._favicon_fallback_url(site)
        for site_def in SiteEngine.get_instance().all_sites():
            if site_def.name == site_name and site_def.favicon:
                return site_def.favicon
        return None

    def _favicon_fallback_url(self, site):
        url = site.get("strict_url") or site.get("signurl") or site.get("rssurl") or ""
        site_def = SiteEngine.get_instance().get_by_url(url)
        if site_def and site_def.favicon:
            return site_def.favicon
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        if domain:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        return None

    def get_site_download_setting(self, site_name=None):
        """
        获取站点下载设置
        """
        if site_name:
            for site in self._siteByIds.values():
                if site.get("name") == site_name:
                    return site.get("download_setting")
        return None

    def test_connection(self, site_id):
        """
        测试站点连通性
        :param site_id: 站点编号
        :return: 是否连通、错误信息、耗时
        """
        site_info = self.get_sites(siteid=site_id)
        if not site_info:
            return False, "站点不存在", 0

        is_public = site_info.get("public", False)
        site_cookie = site_info.get("cookie")
        headers = site_info.get("headers")
        ua = site_info.get("ua") or get_ua()
        proxy = site_info.get("proxy")
        chrome = site_info.get("chrome")

        site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl"))
        if not site_url:
            return False, "未配置站点地址", 0

        if is_public:
            start_time = datetime.now()
            res = RequestUtils(proxies=get_proxies() if proxy else None).get_res(url=site_url)
            seconds = round((datetime.now() - start_time).total_seconds(), 3)
            if res and res.status_code == 200:
                return True, "连接成功", seconds
            elif res is not None:
                return False, f"连接失败，状态码：{res.status_code}", seconds
            return False, "无法打开网站", seconds

        if not site_cookie and not headers:
            return False, "未配置站点Cookie或headers", 0

        if JsonUtils.is_valid_json(headers):
            headers = json.loads(headers)
        else:
            headers = {}
        headers.update({"User-Agent": ua})

        # 优先使用引擎统一测试（JSON 定义站点）
        site_def = SiteEngine.get_instance().get_by_url(site_url)
        if site_def:
            user_config = {
                "cookie": site_cookie,
                "ua": ua,
                "headers": headers,
                "proxy": proxy,
            }
            return SiteEngine.get_instance().test_connection(site_url, user_config)

        # 兜底：旧逻辑（无 JSON 定义的 HTML 站点）
        if chrome:
            chrome_inst = DrissionPageHelper()
            start_time = datetime.now()
            html_text = chrome_inst.get_page_html(url=site_url, cookies=site_cookie)
            seconds = round((datetime.now() - start_time).total_seconds(), 3)
            if not html_text:
                return False, "获取站点源码失败", 0
            if SiteHelper.is_logged_in(html_text):
                return True, "连接成功", seconds
            return False, "Cookie失效", seconds

        start_time = datetime.now()
        res = RequestUtils(cookies=site_cookie, headers=headers, proxies=get_proxies() if proxy else None).get_res(
            url=site_url
        )
        seconds = round((datetime.now() - start_time).total_seconds(), 3)
        if res and res.status_code == 200:
            if not SiteHelper.is_logged_in(res.text):
                return False, "Cookie失效", seconds
            return True, "连接成功", seconds
        elif res is not None:
            return False, f"连接失败，状态码：{res.status_code}", seconds
        return False, "无法打开网站", seconds

    @staticmethod
    def __get_site_note_items(note):
        """
        从note中提取站点信息
        """
        infos = {}
        if note:
            infos = json.loads(note)
        return infos

    @staticmethod
    def _rate_limit_val(note: dict, key: str, multiplier: int = 1, require_fields: list | None = None):
        val = note.get(key)
        if not val or not str(val).isdigit():
            return None
        if require_fields:
            for f in require_fields:
                tv = note.get(f)
                if not tv or not str(tv).isdigit():
                    return None
        return int(val) * multiplier

    def add_site(self, name, site_pri, rssurl=None, signurl=None, cookie=None, note=None, rss_uses=None):
        """
        添加站点
        """
        ret = self.site_repo.insert_config_site(
            name=name, site_pri=site_pri, rssurl=rssurl, signurl=signurl, cookie=cookie, note=note, rss_uses=rss_uses
        )
        self.init_config()
        return ret

    def update_site(self, tid, name, site_pri, rssurl, signurl, cookie, note, rss_uses):
        """
        更新站点
        """
        ret = self.site_repo.update_config_site(
            tid=tid,
            name=name,
            site_pri=site_pri,
            rssurl=rssurl,
            signurl=signurl,
            cookie=cookie,
            note=note,
            rss_uses=rss_uses,
        )
        self.init_config()
        return ret

    def delete_site(self, siteid):
        """
        删除站点
        """
        ret = self.site_repo.delete_config_site(siteid)
        self.init_config()
        return ret

    def update_site_cookie(self, siteid, cookie, ua=None):
        """
        更新站点Cookie和UA
        """
        ret = self.site_repo.update_site_cookie_ua(tid=siteid, cookie=cookie, ua=ua)
        self.init_config()
        return ret

    def update_site_note(self, siteid, note):
        """
        更新站点 note
        """
        ret = self.site_repo.update_config_site_note(tid=siteid, note=note)
        self.init_config()
        return ret

    def get_site_note_by_id(self, siteid):
        """
        根据站点id获取站点配置
        """
        sites = self.site_repo.get_site_by_id(tid=siteid)
        if sites:
            site_note = self.__get_site_note_items(sites[0].NOTE)
            return site_note
