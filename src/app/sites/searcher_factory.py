"""
搜索器工厂 — 从 engine 移出，避免 engine ↔ searchers 循环导入
"""

from app.sites.api_searcher import ApiSiteSearcher
from app.sites.html_searcher import HtmlSiteSearcher


def create_searcher(url: str, site_engine, user_config: dict | None = None):
    site = site_engine.get_by_url(url)
    if not site:
        return None
    if site.api:
        return ApiSiteSearcher(site, site_engine=site_engine, user_config=user_config)
    if site.html:
        return HtmlSiteSearcher(site, site_engine=site_engine, user_config=user_config)
    return None
