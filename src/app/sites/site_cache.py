"""站点内存缓存层.

从 ISiteRepository 读取 SiteEntity 列表，构建内存索引，提供与旧 Sites 类
兼容的查询接口。

刷新机制：SiteService 写操作后调用 refresh() 重建缓存。
"""

from app.domain.interfaces.site_repo import ISiteRepository
from app.utils import StringUtils
from app.utils.config_tools import get_ua
from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
from app.sites.engine import SiteEngine


class SiteCache:
    """站点配置内存缓存.

    构建与旧 Sites.get_sites() 返回格式一致的 dict 索引，
    供所有调用方零成本迁移。

    由 lifespan 创建并注册到 registry，lifespan 中统一刷新。
    """

    def __init__(self, repo: ISiteRepository | None = None, site_engine: SiteEngine | None = None):
        self._repo = repo or SiteRepositoryAdapter()
        self._site_engine = site_engine or SiteEngine()
        self._site_by_ids: dict[int, dict] = {}
        self._site_by_urls: dict[str, dict] = {}
        self._rss_sites: list[dict] = []
        self._brush_sites: list[dict] = []
        self._statistic_sites: list[dict] = []
        self._signin_sites: list[dict] = []
        self._refresh()

    def _refresh(self) -> None:
        """重建所有内存索引."""
        self._site_by_ids = {}
        self._site_by_urls = {}
        self._rss_sites = []
        self._brush_sites = []
        self._statistic_sites = []
        self._signin_sites = []

        entities = self._repo.list_all()
        for entity in entities:
            site_info = self._build_site_info(entity)
            sid = site_info["id"]
            self._site_by_ids[sid] = site_info

            strict_url = site_info.get("strict_url")
            if strict_url:
                domain = StringUtils.get_url_domain(strict_url)
                if domain:
                    self._site_by_urls[domain] = site_info

            if site_info.get("rss_enable"):
                self._rss_sites.append(site_info)
            if site_info.get("brush_enable"):
                self._brush_sites.append(site_info)
            if site_info.get("statistic_enable"):
                self._statistic_sites.append(site_info)
            if not site_info.get("public"):
                self._signin_sites.append(site_info)

    def refresh(self) -> None:
        """外部触发缓存重建（SiteService 写操作后调用）."""
        self._refresh()

    def _build_site_info(self, entity) -> dict:
        """将 SiteEntity 转换为与旧 Sites 兼容的 dict 格式."""
        note = entity.note or {}
        site_rssurl = entity.rss_url
        site_signurl = entity.sign_url
        site_cookie = entity.cookie
        site_uses = entity.rss_uses or ""
        site_headers = note.get("headers")

        # 功能开关计算
        uses = []
        if site_uses:
            rss_enable = bool("D" in site_uses and site_rssurl)
            has_auth = bool(site_cookie or site_headers or entity.api_key or entity.bearer_token)
            brush_enable = bool("S" in site_uses and site_rssurl and has_auth)
            statistic_enable = bool("T" in site_uses and (site_rssurl or site_signurl) and has_auth)
            uses.append("D") if rss_enable else None
            uses.append("S") if brush_enable else None
            uses.append("T") if statistic_enable else None
        else:
            rss_enable = False
            brush_enable = False
            statistic_enable = False

        # strict_url 和 api_key_header
        strict_url = ""
        api_key_header = None
        site_def = self._site_engine.get_by_url(str(site_signurl or site_rssurl or ""))
        if site_def and site_def.api and site_def.api.auth:
            api_key_header = site_def.api.auth.get("header_name")
            strict_url = site_def.api.base_url
        else:
            strict_url = StringUtils.get_base_url(site_signurl or site_rssurl)

        # 公开站点判断
        is_public = False
        if not site_signurl and not site_cookie:
            is_public = True
        if note.get("public") == "Y":
            is_public = True
        if note.get("public") == "N":
            is_public = False

        return {
            "id": entity.id,
            "name": entity.name,
            "pri": entity.pri or 0,
            "rssurl": site_rssurl,
            "signurl": site_signurl,
            "cookie": site_cookie,
            "api_key": entity.api_key,
            "bearer_token": entity.bearer_token,
            "api_key_header": api_key_header,
            "headers": entity.headers or site_headers,
            "rule": note.get("rule"),
            "download_setting": note.get("download_setting"),
            "rss_enable": rss_enable,
            "brush_enable": brush_enable,
            "statistic_enable": statistic_enable,
            "uses": uses,
            "ua": note.get("ua") or get_ua(),
            "parse": note.get("parse") == "Y",
            "unread_msg_notify": note.get("message") == "Y",
            "chrome": note.get("chrome") == "Y",
            "proxy": note.get("proxy") == "Y",
            "subtitle": note.get("subtitle") == "Y",
            "limit_interval": note.get("limit_interval"),
            "limit_count": note.get("limit_count"),
            "limit_seconds": note.get("limit_seconds"),
            "strict_url": strict_url,
            "tag": entity.name if note.get("tag") == "Y" else "",
            "public": is_public,
        }

    def get_sites(
        self,
        siteid: int | str | None = None,
        siteurl: str | None = None,
        siteids: list | None = None,
        rss: bool = False,
        brush: bool = False,
        statistic: bool = False,
        public: bool = False,
    ) -> dict | list[dict]:
        """获取站点配置，与旧 Sites.get_sites() 完全兼容."""
        if siteid:
            return self._site_by_ids.get(int(siteid)) or {}
        if siteurl:
            site_def = self._site_engine.get_by_url(siteurl)
            if site_def and site_def.api:
                siteurl = site_def.api.base_url
            domain = StringUtils.get_url_domain(siteurl)
            return self._site_by_urls.get(domain) or {}

        ret = []
        seen = set()
        for site in self._site_by_ids.values():
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
            url = site.get("strict_url")
            if url and url in seen:
                continue
            if url:
                seen.add(url)
            ret.append(site)
        return ret

    def get_sites_by_suffix(self, suffix: str) -> dict:
        """根据 URL 后缀获取站点配置."""
        for key in self._site_by_urls:
            key_end = ".".join(key.split(".")[-2:])
            if suffix == key_end:
                return self._site_by_urls[key]
        return {}

    def get_sites_by_name(self, name: str) -> list[dict]:
        """根据站点名称获取站点配置."""
        return [site for site in self._site_by_ids.values() if site.get("name") == name]

    def get_max_site_pri(self) -> int:
        """获取最大站点优先级."""
        if not self._site_by_ids:
            return 0
        return max(int(site.get("pri", 0)) for site in self._site_by_ids.values())

    def get_site_dict(
        self, rss: bool = False, brush: bool = False, statistic: bool = False, signin: bool = False
    ) -> list[dict]:
        """获取站点字典."""
        return [
            {"id": site.get("id"), "name": site.get("name")}
            for site in self.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)
            if not (signin and site.get("public"))
        ]

    def get_site_names(self, rss: bool = False, brush: bool = False, statistic: bool = False) -> list[str]:
        """获取站点名称列表."""
        return [site.get("name", "") for site in self.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)]

    def get_site_download_setting(self, site_name: str | None = None) -> str | None:
        """获取站点下载设置."""
        if site_name:
            for site in self._site_by_ids.values():
                if site.get("name") == site_name:
                    return site.get("download_setting")
        return None

    def check_ratelimit(self, site_id: int | str) -> bool:
        """检查站点是否触发流控."""
        from app.services.site_rate_limiter import SiteRateLimiterService

        limiter = SiteRateLimiterService()
        state = limiter.check(str(site_id), timeout=0)
        if state:
            import log

            log.warn(f"[SiteCache]站点 {self._site_by_ids.get(int(site_id), {}).get('name')} 触发流控")
        return state
