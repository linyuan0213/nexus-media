"""站点目录视图：定义列表、详情与内置/第三方合并."""

from typing import Any

from app.schemas.site import SiteDefinitionDTO, SiteDetailDTO
from app.services.site_credential_service import SiteCredentialService


class SiteCatalogService:
    """只负责读模型，不持有仓储状态."""

    @staticmethod
    def get_site_definitions(site_engine: Any) -> list[SiteDefinitionDTO]:
        definitions = []
        for site in site_engine.all_sites():
            site_type = ""
            if site.api:
                site_type = "api"
            elif site.html:
                site_type = "html"
            definitions.append(
                SiteDefinitionDTO(
                    id=site.id,
                    name=site.name,
                    domain=site.domain,
                    type=site_type,
                    public=site.public,
                    domain_aliases=site.domain_aliases,
                    encoding=site.encoding,
                    detail_page_url=site.detail_page_url,
                )
            )
        return sorted(definitions, key=lambda x: x.name)

    @staticmethod
    def get_site(sites: Any, site_conf: Any, tid: str | None) -> SiteDetailDTO:
        if not tid:
            return SiteDetailDTO(site=[])
        site_info = sites.get_sites(siteid=tid)
        if not site_info or isinstance(site_info, list):
            return SiteDetailDTO(site=[])
        site_free = site_2xfree = site_hr = False
        signurl = site_info.get("signurl")
        if signurl:
            attr = site_conf.get_grap_conf(signurl)
            site_free = bool(attr.get("FREE"))
            site_2xfree = bool(attr.get("2XFREE"))
            site_hr = bool(attr.get("HR"))
        return SiteDetailDTO(site=site_info, site_free=site_free, site_2xfree=site_2xfree, site_hr=site_hr)

    @staticmethod
    def get_sites(
        *,
        sites: Any,
        site_engine: Any,
        indexer_site_config_repo: Any,
        is_indexer_enabled: Any,
        rss: bool = False,
        brush: bool = False,
        statistic: bool = False,
        basic: bool = False,
        source: str | None = None,
    ) -> Any:
        # RSS/刷流/统计场景只返回 builtin 站点
        if rss or brush or statistic:
            return [
                SiteCredentialService.sanitize(site)
                for site in sites.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)
            ]

        builtin = sites.get_sites(public=True)
        engine_by_name = {s.name: s.public for s in site_engine.all_sites()}
        config_rows = indexer_site_config_repo.list_all()
        config_by_name = {row.site_name.lower(): row for row in config_rows}

        if basic:
            merged = {}
            for s in builtin:
                cfg = config_by_name.get(s["name"].lower())
                enabled = cfg.enabled if cfg else True
                if not enabled:
                    continue
                merged[s["name"]] = {
                    "id": s["id"],
                    "name": s["name"],
                    "source": "builtin",
                    "enabled": True,
                    "site_public": engine_by_name.get(s["name"], s.get("public", False)),
                }
            if source != "builtin":
                for row in config_rows:
                    if row.site_name not in merged and row.source != "builtin":
                        if not is_indexer_enabled(row.source):
                            continue
                        merged[row.site_name] = {
                            "id": str(row.id or 0),
                            "name": row.site_name,
                            "source": row.source,
                            "enabled": bool(row.enabled),
                            "third_party": True,
                        }
            return [SiteCredentialService.sanitize(site) for site in merged.values()]

        merged = {s["name"]: {**s, "source": "builtin", "third_party": False} for s in builtin}
        for name, site in merged.items():
            cfg = config_by_name.get(name.lower())
            # 站点维护列表需要展示"搜索已关闭"的站点（否则关闭后站点消失、无法再开启），
            # 因此这里不过滤 enabled：调用方（搜索/索引器）自会按启用状态过滤
            site["enabled"] = cfg.enabled if cfg else True
            site["download_setting"] = cfg.download_setting if cfg else None
            site["default_settings"] = cfg.default_settings if cfg else None
            site["site_public"] = engine_by_name.get(name, site.get("public", False))
        for row in config_rows:
            if row.source == "builtin":
                continue
            if not is_indexer_enabled(row.source):
                continue
            if row.site_name not in merged:
                merged[row.site_name] = SiteCatalogService.third_party_site_dict(row)
        return list(merged.values())

    @staticmethod
    def third_party_site_dict(row) -> dict:
        return {
            "id": row.id,
            "name": row.site_name,
            "pri": 0,
            "source": row.source,
            "third_party": True,
            "download_setting": row.download_setting,
            "enabled": bool(row.enabled),
            "default_settings": row.default_settings,
            "public": bool(row.public),
            "rssurl": "",
            "signurl": "",
            "cookie": "",
            "api_key": "",
            "bearer_token": "",
            "api_key_header": None,
            "headers": None,
            "rule": None,
            "rss_enable": False,
            "brush_enable": False,
            "statistic_enable": False,
            "uses": [],
            "ua": "",
            "parse": False,
            "unread_msg_notify": False,
            "chrome": False,
            "proxy": False,
            "subtitle": False,
            "limit_interval": None,
            "limit_count": None,
            "limit_seconds": None,
            "strict_url": "",
            "note": {},
        }
