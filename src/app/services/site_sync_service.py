"""站点同步门面：为插件提供站点查询、写入与探测能力."""

import time
from typing import Any

import log
from app.domain.entities.site import SiteEntity
from app.domain.enums import SiteUseType
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.sites.utils import is_logged_in
from app.utils.config_tools import get_ua
from app.utils.string_utils import StringUtils


class SiteSyncService:
    """插件同步端口：只暴露 dict 数据，不向插件泄漏仓储/实体/引擎."""

    def __init__(
        self,
        *,
        sites: Any,
        site_entity_repo: Any,
        site_engine: Any,
        indexer_helper: Any | None = None,
    ):
        self._sites = sites
        self._site_entity_repo = site_entity_repo
        self._site_engine = site_engine
        self._indexer_helper = indexer_helper

    # ---- 已配置站点 ----
    def list_sites(self, public: bool = False) -> list[dict]:
        result = self._sites.get_sites(public=public)
        return result if isinstance(result, list) else []

    def list_entities(self) -> list[dict]:
        return [self._entity_dict(e) for e in self._site_entity_repo.list_all()]

    @staticmethod
    def _entity_dict(entity: Any) -> dict:
        return {
            "id": int(getattr(entity, "id", 0) or 0),
            "name": str(getattr(entity, "name", "") or ""),
            "pri": int(getattr(entity, "pri", 0) or 0),
            "sign_url": getattr(entity, "sign_url", None) or "",
            "rss_url": getattr(entity, "rss_url", None) or "",
            "cookie": getattr(entity, "cookie", None) or "",
        }

    def find_sites_by_domain(self, domain_url: str) -> list[dict]:
        """按域名/二级域名匹配已配置站点."""
        matched = []
        for site in self.list_sites(public=False):
            strict_url = site.get("strict_url", "")
            if not strict_url:
                continue
            site_domain = StringUtils.get_url_domain(strict_url)
            if not site_domain:
                continue
            if domain_url in site_domain or site_domain in domain_url:
                matched.append(site)
                continue
            site_suffix = ".".join(site_domain.split(".")[-2:])
            domain_suffix = ".".join(domain_url.split(".")[-2:])
            if site_suffix == domain_suffix:
                matched.append(site)
        return matched

    def get_site(self, site_id: int) -> dict | None:
        entity = self._site_entity_repo.get_by_id(int(site_id))
        return self._entity_dict(entity) if entity else None

    def update_cookie(self, site_id: int, cookie: str) -> None:
        self._site_entity_repo.update_cookie_ua(int(site_id), cookie=cookie)

    def update_sign_url(self, site_id: int, url: str, cookie: str | None = None) -> bool:
        entity = self._site_entity_repo.get_by_id(int(site_id))
        if not entity:
            return False
        entity.sign_url = url
        if cookie:
            entity.cookie = cookie
        self._site_entity_repo.update(entity)
        return True

    def create_site(self, *, name: str, pri: int, sign_url: str, cookie: str) -> int | None:
        entity = SiteEntity(
            name=name,
            pri=pri,
            sign_url=sign_url,
            cookie=cookie,
            rss_uses=SiteUseType.STATISTIC.value,
        )
        self._site_entity_repo.insert(entity)
        inserted = self._site_entity_repo.list_by_name(name)
        ids = [int(getattr(item, "id", 0) or 0) for item in inserted]
        return max(ids) if ids else None

    def delete_site(self, site_id: int) -> None:
        self._site_entity_repo.delete(int(site_id))

    def refresh(self) -> None:
        self._sites.refresh()

    # ---- 站点定义 ----
    def resolve_definition(self, url: str) -> dict | None:
        """解析站点定义；引擎优先，索引器配置兜底."""
        definition = None
        try:
            definition = self._site_engine.get_by_url(url)
        except Exception:
            definition = None
        if definition is None and self._indexer_helper is not None:
            definition = self._indexer_helper.get_indexer_info(url)
        return self._definition_dict(definition) if definition is not None else None

    @staticmethod
    def _definition_dict(definition: Any) -> dict:
        if isinstance(definition, dict):
            aliases = definition.get("domain_aliases") or []
            return {
                "id": str(definition.get("id") or ""),
                "name": str(definition.get("name") or ""),
                "domain": str(definition.get("domain") or ""),
                "domain_aliases": [str(a) for a in aliases],
                "public": bool(definition.get("public")),
                "auth_type": str(((definition.get("api") or {}).get("auth") or {}).get("type") or ""),
            }
        api = getattr(definition, "api", None)
        auth = (getattr(api, "auth", {}) or {}) if api else {}
        return {
            "id": str(getattr(definition, "id", "") or ""),
            "name": str(getattr(definition, "name", "") or ""),
            "domain": str(getattr(definition, "domain", "") or ""),
            "domain_aliases": [str(a) for a in (getattr(definition, "domain_aliases", None) or [])],
            "public": bool(getattr(definition, "public", False)),
            "auth_type": str(auth.get("type") or ""),
        }

    def list_definitions(self, private_only: bool = False) -> list[dict]:
        try:
            definitions = self._site_engine.all_sites()
        except Exception:
            return []
        result = []
        for item in definitions:
            data = self._definition_dict(item)
            if private_only and data["public"]:
                continue
            result.append(data)
        return result

    def dedupe_by_definition(self) -> int:
        """同一站点定义只保留 id 最大的一条，返回删除数量."""
        groups: dict[str, list[int]] = {}
        for entity in self._site_entity_repo.list_all():
            url = entity.sign_url or entity.rss_url
            if not url or not entity.id:
                continue
            definition = self.resolve_definition(url)
            if definition and definition["id"]:
                groups.setdefault(definition["id"], []).append(int(entity.id))
        removed = 0
        for def_id, ids in groups.items():
            if len(ids) <= 1:
                continue
            keep = max(ids)
            drop = [sid for sid in ids if sid != keep]
            for sid in drop:
                self._site_entity_repo.delete(sid)
                removed += 1
            log.info(f"[CookieCloud]站点去重 [{def_id}] 保留 id={keep}，删除 {len(drop)} 条重复")
        if removed:
            self.refresh()
        return removed

    # ---- 探测与连接 ----
    def test_connection(self, url: str, user_config: dict) -> bool:
        ok, _, _ = self._site_engine.test_connection(url, user_config)
        return bool(ok)

    def probe_domain(self, domain: str, cookie: str = "", attempts: int = 3) -> tuple[float, float]:
        """返回 (成功率, 平均延时 ms)，供插件选择签到域名."""
        url = domain if domain.startswith("http") else f"https://{domain}"
        ok = 0
        latencies: list[float] = []
        for _ in range(max(1, attempts)):
            start = time.time()
            try:
                response = HttpClient(
                    config=HttpClientConfig(
                        default_headers={"User-Agent": get_ua()},
                        timeout=10.0,
                        connect_timeout=5.0,
                    )
                ).get(url=url, auth=CookieAuth(cookie) if cookie else None, raise_for_status=False)
                if response is not None and response.status_code == 200 and is_logged_in(response.text):
                    ok += 1
                    latencies.append((time.time() - start) * 1000)
            except Exception:
                continue
        rate = ok / max(1, attempts)
        latency = sum(latencies) / len(latencies) if latencies else float("inf")
        return rate, latency

    def upsert_credentials(self, site_id: int, profile: str, data: dict | None) -> None:
        self._site_entity_repo.upsert_site_api_credentials(int(site_id), str(profile), data)
