# -*- coding: utf-8 -*-
"""
搜索器工厂 — 从 engine 移出，避免 engine ↔ searchers 循环导入
"""
from typing import Optional

from app.sites.engine import SiteEngine
from app.sites.api_searcher import ApiSiteSearcher
from app.sites.html_searcher import HtmlSiteSearcher


def create_searcher(url: str, user_config: Optional[dict] = None):
    engine = SiteEngine.get_instance()
    site = engine.get_by_url(url)
    if not site:
        return None
    if site.api:
        return ApiSiteSearcher(site, user_config)
    if site.html:
        return HtmlSiteSearcher(site, user_config)
    return None
