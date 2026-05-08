# -*- coding: utf-8 -*-
"""
站点引擎 — 统一站点定义加载与功能入口

消除散落在 20+ 个文件中的 'if m-team in url' 逻辑，
通过声明式 JSON 站点定义提供统一的搜索、下载、字幕等功能入口。
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse
from lxml import etree

import log
import traceback

from app.sites import engine_tools
from app.sites import engine_download
from app.sites import engine_connection
from app.sites import engine_user_info
from app.utils import RequestUtils, JsonUtils
from app.utils.config_tools import get_proxies


# ---- 数据模型 ----

@dataclass
class DownloadConfig:
    """下载链接配置"""
    type: str = "api"
    method: str = "GET"
    path: str = ""
    body: Optional[Dict[str, str]] = None
    response_key: str = "data"
    params: Optional[Dict[str, str]] = None
    download_url: Optional[str] = None
    selectors: Optional[dict] = None


@dataclass
class SubtitleConfig:
    """字幕下载配置"""
    type: str = "api"
    list_endpoint: Optional[Dict] = None
    genlink_endpoint: Optional[Dict] = None
    download_endpoint: Optional[Dict] = None


@dataclass
class SiteApiConfig:
    """站点 API 配置"""
    base_url: str = ""
    auth: Dict = field(default_factory=dict)
    endpoints: Dict = field(default_factory=dict)


@dataclass
class SiteHtmlConfig:
    """HTML 站点配置"""
    search: Dict = field(default_factory=dict)
    torrents: Dict = field(default_factory=dict)
    category: Dict = field(default_factory=dict)
    conf: Dict = field(default_factory=dict)
    browse: Optional[Dict] = None
    parser_type: str = "flat"


@dataclass
class SiteDefinition:
    """站点完整定义"""
    id: str = ""
    name: str = ""
    domain: str = ""
    domain_aliases: List[str] = field(default_factory=list)
    tid_pattern: str = r"\d+"
    encoding: str = "UTF-8"
    public: bool = False
    favicon: str = ""
    language: Optional[str] = None
    api: Optional[SiteApiConfig] = None
    html: Optional[SiteHtmlConfig] = None
    download: Optional[DownloadConfig] = None
    torrent_attr: Optional[dict] = None
    subtitle: Optional[SubtitleConfig] = None
    detail_page_url: str = ""
    user_info: Optional[dict] = None

    def match_url(self, url: str) -> bool:
        if not url or not self.domain:
            return False
        url_lower = url.lower()
        if self.domain.lower() in url_lower:
            return True
        for alias in self.domain_aliases:
            if alias.lower() in url_lower:
                return True
        return False

    @classmethod
    def from_dict(cls, data: dict) -> "SiteDefinition":
        d = cls()
        d.id = data.get("id", "")
        d.name = data.get("name", data.get("id", ""))
        d.domain = data.get("domain", "")
        d.domain_aliases = data.get("domain_aliases", [])
        d.tid_pattern = data.get("tid_pattern", r"\d+")
        d.encoding = data.get("encoding", "UTF-8")
        d.public = data.get("public", False)
        d.favicon = data.get("favicon", "")
        d.language = data.get("language")
        d.detail_page_url = data.get("detail_page_url", "")
        if data.get("api"):
            api = data["api"]
            endpoints = api.get("endpoints", {})
            d.api = SiteApiConfig(
                base_url=api.get("base_url", ""),
                auth=api.get("auth", {}),
                endpoints=endpoints,
            )
        if data.get("html"):
            html = data["html"]
            d.html = SiteHtmlConfig(
                search=html.get("search", {}),
                torrents=html.get("torrents", {}),
                category=html.get("category", {}),
                conf=html.get("conf", {}),
                browse=html.get("browse"),
                parser_type=html.get("parser_type", "flat"),
            )
        if data.get("download"):
            dl = data["download"]
            d.download = DownloadConfig(
                type=dl.get("type", "api"),
                method=dl.get("method", "GET"),
                path=dl.get("path", ""),
                body=dl.get("body"),
                response_key=dl.get("response_key", "data"),
                params=dl.get("params"),
                download_url=dl.get("download_url"),
                selectors=dl.get("selectors"),
            )
        if data.get("torrent_attr"):
            d.torrent_attr = data["torrent_attr"]
        if data.get("subtitle"):
            sub = data["subtitle"]
            d.subtitle = SubtitleConfig(
                type=sub.get("type", "api"),
                list_endpoint=sub.get("list"),
                genlink_endpoint=sub.get("genlink"),
                download_endpoint=sub.get("download"),
            )
        if data.get("user_info"):
            d.user_info = data["user_info"]
        return d


# ---- 站点引擎 ----

class SiteEngine:
    """站点引擎单例"""

    _DEFAULT_DEFINITIONS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "sites"
    )

    def __init__(self, definitions_dir: Optional[str] = None):
        self._sites: Dict[str, SiteDefinition] = {}
        self._auth_cache: Dict[str, str] = {}
        self._user_info_factories = []
        if definitions_dir is None:
            definitions_dir = self._DEFAULT_DEFINITIONS_DIR
        if definitions_dir and os.path.isdir(definitions_dir):
            for subdir in ("api", "html"):
                subpath = os.path.join(definitions_dir, subdir)
                if os.path.isdir(subpath):
                    self._load(subpath)

    def _load(self, directory: str):
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(directory, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                site_def = SiteDefinition.from_dict(data)
                self._sites[site_def.id] = site_def
                log.debug(f"【SiteEngine】加载站点定义: {site_def.name} ({site_def.id})")
            except Exception:
                log.warn(f"【SiteEngine】加载站点定义失败: {fname}\n{traceback.format_exc()}")

    def register(self, site_def: SiteDefinition):
        self._sites[site_def.id] = site_def

    def get_by_id(self, site_id: str) -> Optional[SiteDefinition]:
        return self._sites.get(site_id)

    def get_by_url(self, url: str) -> Optional[SiteDefinition]:
        for site in self._sites.values():
            if site.match_url(url):
                return site
        return None

    def all_sites(self) -> List[SiteDefinition]:
        return list(self._sites.values())

    def normalize_domain(self, url: str) -> str:
        site = self.get_by_url(url)
        return site.domain if site else self._base_from_url(url)

    def is_tid_based_dedup(self, url: str) -> bool:
        site = self.get_by_url(url)
        return site.tid_pattern != "" if site else False

    # ---- 详情页 ----

    def resolve_detail_url(self, url: str, tid: str) -> str:
        site = self.get_by_url(url)
        if site and site.detail_page_url:
            return site.detail_page_url.format(tid=tid)
        return f"{self._base_from_url(url)}/detail/{tid}"

    # ---- 下载链接 ----

    def resolve_download_url(self, page_url: str, user_config: Optional[dict] = None) -> Optional[str]:
        site = self.get_by_url(page_url)
        if not site:
            return None
        user_config = user_config or {}
        if site.download:
            if site.download.type == "html":
                return engine_download.resolve_html_download(self, page_url, site, user_config)
            tid = self._extract_tid(page_url, site)
            if not tid:
                return None
            base = site.api.base_url.rstrip("/") if site.api else self._base_from_url(page_url)
            path = site.download.path.format(tid=tid)
            url = f"{base}{path}" if path.startswith("/") else path
            if site.download.type == "api":
                return engine_download.resolve_download_api(self, url, site, user_config, tid)
            elif site.download.type == "api_chained":
                return engine_download.resolve_download_chained(self, url, site, user_config, tid)
            elif site.download.type == "template":
                return site.download.path.format(tid=tid)
            return url
        if site.html:
            return engine_download.resolve_html_download(self, page_url, site, user_config)
        return None

    # ---- 种子属性检查 ----

    def resolve_torrent_attr(self, torrent_url, cookie=None, ua=None, headers=None, proxy=False):
        ret = {"free": False, "2xfree": False, "hr": False, "peer_count": 0}
        site = self.get_by_url(torrent_url)
        if not site:
            return ret
        user_config = {"cookie": cookie or "", "ua": ua or "", "proxy": proxy, "headers": headers or {}}

        if site.api and site.torrent_attr:
            tid = self._extract_tid(torrent_url, site)
            if not tid:
                return ret
            cfg = site.torrent_attr
            base = site.api.base_url.rstrip("/")
            path = cfg.get("path", "").format(tid=tid)
            url = f"{base}{path}" if path.startswith("/") else path
            body = {k: v.format(tid=tid) for k, v in (cfg.get("body") or {}).items()}
            headers = engine_tools._build_headers(self, site, user_config)
            headers.pop("Content-Type", None)
            res = RequestUtils(headers=headers, proxies=get_proxies() if proxy else None,
                               timeout=30).post_res(url=url, data=body)
            if res and res.status_code == 200:
                text = res.text
                free_path = cfg.get("response", {}).get("free_key", "")
                free_val = cfg.get("response", {}).get("free_value", "")
                if free_path:
                    if str(JsonUtils.get_json_object(text, free_path)) == free_val:
                        ret["free"] = True
                peer_path = cfg.get("response", {}).get("peer_count_key", "")
                if peer_path:
                    val = JsonUtils.get_json_object(text, peer_path)
                    peer_type = cfg.get("response", {}).get("peer_count_type", "int")
                    if peer_type == "str":
                        ret["peer_count"] = str(val) if val else ""
                    else:
                        ret["peer_count"] = int(val) if val else 0
            return ret

        if site.html and site.html.conf:
            conf = site.html.conf
            detail_url = site.detail_page_url.format(tid=self._extract_tid(torrent_url, site) or "")
            if not detail_url.startswith("http"):
                detail_url = f"{site.domain.rstrip('/')}/{detail_url.lstrip('/')}"
            html_txt = self._fetch_page(detail_url, user_config)
            if not html_txt:
                return ret
            if JsonUtils.is_valid_json(html_txt):
                for xp in conf.get("2XFREE", []):
                    if str(JsonUtils.get_json_object(html_txt, xp.split('=')[0])) == xp.split('=')[1]:
                        ret["free"] = True
                        ret["2xfree"] = True
                for xp in conf.get("FREE", []):
                    if str(JsonUtils.get_json_object(html_txt, xp.split('=')[0])) == xp.split('=')[1]:
                        ret["free"] = True
                for xp in conf.get("HR", []):
                    if JsonUtils.get_json_object(html_txt, xp):
                        ret["hr"] = True
                for xp in conf.get("PEER_COUNT", []):
                    val = JsonUtils.get_json_object(html_txt, xp)
                    ret["peer_count"] = int(val) if str(val) else 0
            else:
                doc = etree.HTML(html_txt)
                if doc is not None:
                    for xp in conf.get("2XFREE", []):
                        if doc.xpath(xp):
                            ret["free"] = True
                            ret["2xfree"] = True
                    for xp in conf.get("FREE", []):
                        if doc.xpath(xp):
                            ret["free"] = True
                    for xp in conf.get("HR", []):
                        if doc.xpath(xp):
                            ret["hr"] = True
                    for xp in conf.get("PEER_COUNT", []):
                        els = doc.xpath(xp)
                        if els:
                            txt = ''.join(els[0].itertext())
                            ret["peer_count"] = int(''.join(c for c in txt if c.isdigit()) or 0)
        return ret

    def _fetch_page(self, url, user_config):
        cookie = user_config.get("cookie", "")
        ua = user_config.get("ua", "")
        headers = {"User-Agent": ua} if ua else {}
        res = RequestUtils(cookies=cookie if cookie else None,
                           headers=headers, proxies=get_proxies() if user_config.get("proxy") else None,
                           timeout=30).get_res(url=url)
        if res and res.status_code == 200:
            res.encoding = res.apparent_encoding
            return res.text
        return None

    # ---- 连接测试 ----

    def test_connection(self, url: str, user_config: Optional[dict] = None) -> tuple:
        site = self.get_by_url(url)
        if not site:
            return False, "未找到站点定义", 0
        user_config = user_config or {}
        if site.api:
            test_cfg = site.api.endpoints.get("test_connection")
            if not test_cfg:
                return False, "站点未配置连接测试端点", 0
            start = time.time()
            result = engine_tools._call_endpoint(self, test_cfg, site, user_config, {})
            latency = int((time.time() - start) * 1000)
            return (True, "连接成功", latency) if result is not None else (False, "连接失败", latency)
        if site.html:
            return engine_connection.test_html_connection(self, site, user_config)
        return False, "未配置 API 或 HTML 端点", 0

    # ---- 用户信息 ----

    def register_user_info_factory(self, factory):
        self._user_info_factories.append(factory)

    def get_user_info(self, url, site_name, site_cookie, html_text=None,
                      site_headers=None, ua="", emulate=False, proxy=False, session=None):
        for factory in self._user_info_factories:
            result = factory(url, site_name, site_cookie,
                             html_text=html_text, site_headers=site_headers,
                             ua=ua, emulate=emulate, proxy=proxy, session=session)
            if result:
                return result
        return None

    def prefetch_user_profile(self, url, site_cookie, site_headers=None,
                              ua="", proxy=False, session=None):
        return engine_user_info.prefetch_user_profile(self, url, site_cookie,
                                                       site_headers=site_headers,
                                                       ua=ua, proxy=proxy, session=session)

    # ---- 字幕 ----

    def resolve_subtitle(self, page_url: str, torrent_id: str, subtitle_dir: str,
                         user_config: Optional[dict] = None) -> int:
        site = self.get_by_url(page_url)
        if not site or not site.subtitle:
            return 0
        user_config = user_config or {}
        tid = self._extract_tid(page_url, site) or torrent_id
        list_cfg = site.subtitle.list_endpoint
        genlink_cfg = site.subtitle.genlink_endpoint
        dl_cfg = site.subtitle.download_endpoint
        if not list_cfg or not dl_cfg:
            return 0
        subs = engine_tools._call_endpoint(self, list_cfg, site, user_config, {"tid": tid}) or []
        if not isinstance(subs, list):
            return 0
        cnt = 0
        for sub in subs:
            sid = sub.get("id", "") if isinstance(sub, dict) else ""
            if not sid:
                continue
            genlink_vars = {"tid": tid, "subtitle_id": sid}
            link = engine_tools._call_endpoint(self, genlink_cfg, site, user_config, genlink_vars) if genlink_cfg else None
            if link:
                dl_cfg_path = dl_cfg.get("path", "").format(tid=tid, subtitle_id=sid)
                dl_url = f"{site.api.base_url.rstrip('/')}/{dl_cfg_path.lstrip('/')}"
                if engine_tools._call_endpoint(self,
                                               {"method": "GET", "path": dl_url}, site, user_config, {},
                                               credential=str(sid), download_dir=subtitle_dir, download=True):
                    cnt += 1
            else:
                if engine_tools._call_endpoint(self, dl_cfg, site, user_config, {"tid": tid, "subtitle_id": sid},
                                               credential=str(sid), download_dir=subtitle_dir, download=True):
                    cnt += 1
        return cnt

    # ---- 内部工具 (委托给 engine_tools) ----

    def _call_endpoint(self, cfg, site, user_config, template_vars,
                       credential="", download_dir="", download=False):
        return engine_tools._call_endpoint(self, cfg, site, user_config, template_vars,
                                           credential=credential, download_dir=download_dir, download=download)

    def _build_headers(self, site, user_config):
        return engine_tools._build_headers(self, site, user_config)

    def _resolve_auth_token(self, site, user_config, token_type):
        return engine_tools._resolve_auth_token(self, site, user_config, token_type)

    def _fetch_csrf_token(self, site, user_config):
        return engine_tools._fetch_csrf_token(self, site, user_config)

    def _fetch_passkey(self, site, user_config):
        return engine_tools._fetch_passkey(self, site, user_config)

    @staticmethod
    def _extract_tid(page_url: str, site: Optional[SiteDefinition] = None) -> Optional[str]:
        if not page_url:
            return None
        pattern = site.tid_pattern if site else r"\d+"
        match = re.findall(pattern, page_url)
        return match[-1] if match else None

    @staticmethod
    def _base_from_url(url: str) -> str:
        parts = urlparse(url)
        return f"{parts.scheme}://{parts.netloc}"

    def get_auth_token(self, site_id, token_type):
        cache_key = f"{site_id}:{token_type}"
        return self._auth_cache.get(cache_key)

    _engine_instance: Optional["SiteEngine"] = None

    @classmethod
    def get_instance(cls, definitions_dir: str = None) -> "SiteEngine":
        if cls._engine_instance is None:
            cls._engine_instance = cls(definitions_dir)
        return cls._engine_instance
