"""站点凭据的读取与列表脱敏."""

from typing import Any


class SiteCredentialService:
    """站点 API 凭据视图；明文只在编辑接口按需返回."""

    @staticmethod
    def get_credentials(sites: Any, tid: int) -> dict:
        site = sites.get_sites(siteid=int(tid)) or {}
        if isinstance(site, list):
            site = site[0] if site else {}
        credentials = dict(site.get("api_credentials") or {})
        spa = credentials.get("spa")
        if isinstance(spa, dict):
            spa = dict(spa)
            storage = spa.get("local_storage") or {}
            if isinstance(storage, dict):
                spa.setdefault(
                    "bearer_token",
                    storage.get("pig_token")
                    or storage.get("auth")
                    or storage.get("token")
                    or storage.get("access_token")
                    or "",
                )
                spa.setdefault(
                    "visitor_id",
                    storage.get("visitorId") or storage.get("visitor_id") or storage.get("pig_visitorid") or "",
                )
            credentials["spa"] = spa
        return credentials

    @staticmethod
    def sanitize(site: dict) -> dict:
        """API 列表不返回明文凭据，只返回 profile/来源元信息."""
        result = dict(site)
        credentials = result.pop("api_credentials", None)
        if isinstance(credentials, dict):
            result["api_profiles"] = list(credentials.keys())
            spa = credentials.get("spa") or {}
            if isinstance(spa, dict):
                result["spa_source"] = spa.get("source") or ""
                result["spa_updated_at"] = int(spa.get("updated_at") or 0)
                result["spa_configured"] = bool(spa.get("bearer_token") or spa.get("token") or spa.get("local_storage"))
        result["has_api_credentials"] = bool(result.get("api_profiles"))
        return result
