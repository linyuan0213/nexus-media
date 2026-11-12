"""站点静态定义与配置解析（不包含运行时引擎）."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DownloadConfig:
    """下载链接配置"""

    type: str = "api"
    method: str = "GET"
    path: str = ""
    body: dict[str, str] | None = None
    response_key: str = "data"
    params: dict[str, str] | None = None
    download_url: str | None = None
    selectors: dict | None = None
    presigned: bool = False


@dataclass
class SubtitleConfig:
    """字幕下载配置"""

    type: str = "api"
    list_endpoint: dict | None = None
    genlink_endpoint: dict | None = None
    download_endpoint: dict | None = None


@dataclass
class SiteApiConfig:
    """站点 API 配置；profiles 允许多套协议共存."""

    base_url: str = ""
    auth: dict = field(default_factory=dict)
    endpoints: dict = field(default_factory=dict)
    profiles: dict[str, "SiteApiConfig"] = field(default_factory=dict)
    default_profile: str = ""
    capabilities: dict[str, list[str]] = field(default_factory=dict)
    http2: bool = False
    torrent_attr: dict | None = None
    download: Any = None


@dataclass
class SiteHtmlConfig:
    """HTML 站点配置"""

    search: dict = field(default_factory=dict)
    torrents: dict = field(default_factory=dict)
    category: dict = field(default_factory=dict)
    conf: dict = field(default_factory=dict)
    browse: dict | None = None
    parser_type: str = "flat"
    test_connection: str | None = None


@dataclass
class SiteDefinition:
    """站点完整定义"""

    id: str = ""
    name: str = ""
    domain: str = ""
    domain_aliases: list[str] = field(default_factory=list)
    # RSS 专用域名（仅用于识别 RSS 种子归属，功能访问仍走主站 domain）
    rss_domains: list[str] = field(default_factory=list)
    tid_pattern: str = r"\d+"
    encoding: str = "UTF-8"
    public: bool = False
    favicon: str = ""
    language: str | None = None
    api: SiteApiConfig | None = None
    html: SiteHtmlConfig | None = None
    download: DownloadConfig | None = None
    torrent_attr: dict | None = None
    subtitle: SubtitleConfig | None = None
    detail_page_url: str = ""
    user_info: dict | None = None

    def match_url(self, url: str) -> bool:
        if not url or not self.domain:
            return False
        url_lower = url.lower()
        domain_lower = self.domain.lower()
        if domain_lower in url_lower or url_lower in domain_lower:
            return True
        url_stripped = url_lower.replace("www.", "")
        domain_stripped = domain_lower.replace("www.", "")
        if domain_stripped in url_stripped or url_stripped in domain_stripped:
            return True
        if any(alias.lower() in url_lower or url_lower in alias.lower() for alias in self.domain_aliases):
            return True
        return any(rss.lower() in url_lower or url_lower in rss.lower() for rss in self.rss_domains)

    @staticmethod
    def _parse_download(data: dict | None) -> DownloadConfig | None:
        if not isinstance(data, dict):
            return None
        return DownloadConfig(
            type=data.get("type", "api"),
            method=data.get("method", "GET"),
            path=data.get("path", ""),
            body=data.get("body"),
            response_key=data.get("response_key", "data"),
            params=data.get("params"),
            download_url=data.get("download_url"),
            selectors=data.get("selectors"),
            presigned=data.get("presigned", False),
        )

    @classmethod
    def _parse_api_profile(cls, data: dict) -> SiteApiConfig:
        return SiteApiConfig(
            base_url=data.get("base_url", ""),
            auth=data.get("auth", {}),
            endpoints=data.get("endpoints", {}),
            http2=bool(data.get("http2") or data.get("transport") == "http2"),
            torrent_attr=data.get("torrent_attr"),
            download=cls._parse_download(data.get("download")),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "SiteDefinition":
        d = cls()
        d.id = data.get("id", "")
        d.name = data.get("name", data.get("id", ""))
        d.domain = data.get("domain", "")
        d.domain_aliases = data.get("domain_aliases", [])
        d.rss_domains = data.get("rss_domains", [])
        d.tid_pattern = data.get("tid_pattern", r"\d+")
        d.encoding = data.get("encoding", "UTF-8")
        d.public = data.get("public", False)
        d.favicon = data.get("favicon", "")
        d.language = data.get("language")
        d.detail_page_url = data.get("detail_page_url", "")
        if data.get("api"):
            api = data["api"]
            profiles = {
                str(name): cls._parse_api_profile(profile)
                for name, profile in (api.get("profiles") or {}).items()
                if isinstance(profile, dict)
            }
            d.api = SiteApiConfig(
                base_url=api.get("base_url", ""),
                auth=api.get("auth", {}),
                endpoints=api.get("endpoints", {}),
                profiles=profiles,
                default_profile=str(api.get("default_profile") or ""),
                capabilities={
                    str(name): [str(item) for item in order]
                    for name, order in (api.get("capabilities") or {}).items()
                    if isinstance(order, list)
                },
                http2=bool(api.get("http2") or api.get("transport") == "http2"),
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
                test_connection=html.get("test_connection"),
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
                presigned=dl.get("presigned", False),
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
