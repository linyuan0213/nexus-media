"""站点图标服务.

替代旧 Sites 类的图标相关方法，从数据库/SiteEngine/回退 URL 三级查找图标。
"""

from app.db.repositories.site_repository import SiteRepository
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache


class SiteFaviconService:
    """站点图标服务."""

    def __init__(
        self,
        cache: SiteCache,
        site_engine: SiteEngine,
        repo: SiteRepository | None = None,
    ):
        self._repo = repo or SiteRepository()
        self._site_engine = site_engine
        self._cache = cache
        self._favicons: dict[str, str] = {}
        self._refresh()

    def _get_site_engine(self):
        return self._site_engine

    def _refresh(self) -> None:
        """从数据库加载图标缓存（过滤空值）."""
        self._favicons = {str(site.SITE): str(site.FAVICON) for site in self._repo.get_site_favicons() if site.FAVICON}

    def refresh(self) -> None:
        """外部触发刷新."""
        self._refresh()

    def get_favicon(self, site_name: str | None = None) -> str | dict[str, str] | None:
        """获取单个站点图标；不传 name 时返回全部图标映射."""
        if not site_name:
            return self.get_all_favicons()
        # 1. 数据库缓存
        data = self._favicons.get(site_name)
        if data:
            return data
        # 2. 从 SiteCache 回退
        sites = self._cache.get_sites_by_name(site_name)
        for site in sites:
            url = self._fallback_url(site)
            if url:
                return url
        # 3. 从 SiteEngine 回退
        for site_def in self._site_engine.all_sites():
            if site_def.name == site_name and site_def.favicon:
                return site_def.favicon
        return None

    def get_all_favicons(self) -> dict[str, str]:
        """获取全部图标映射."""
        result = {str(k): str(v) if v else "" for k, v in self._favicons.items()}
        for site in self._cache.get_sites(public=True):
            name = site.get("name")
            if name and name not in result:
                url = self._fallback_url(site)
                if url:
                    result[name] = url
        for site_def in self._site_engine.all_sites():
            if site_def.favicon and site_def.name not in result:
                result[site_def.name] = site_def.favicon
        return result

    def _fallback_url(self, site: dict) -> str | None:
        """图标回退 URL."""
        url = site.get("strict_url") or site.get("signurl") or site.get("rssurl") or ""
        site_def = self._get_site_engine().get_by_url(url)
        if site_def and site_def.favicon:
            return site_def.favicon
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        if domain:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        return None
