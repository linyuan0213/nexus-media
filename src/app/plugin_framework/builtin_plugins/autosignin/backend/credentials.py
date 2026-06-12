"""签到凭据解析器 — 支持 headers / LocalStorage / 数据库字段等多来源提取。"""

import json
from abc import ABC, abstractmethod
from typing import Optional

from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter


class CredentialSource(ABC):
    @abstractmethod
    def extract(self, site_info: dict) -> Optional[str]: ...


class HeaderSource(CredentialSource):
    def __init__(self, name: str, strip_prefix: str = ""):
        self.name = name.lower()
        self.strip_prefix = strip_prefix

    def extract(self, site_info: dict) -> Optional[str]:
        headers = site_info.get("headers")
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                return None
        if not isinstance(headers, dict):
            return None
        for key, value in headers.items():
            if key.lower() == self.name:
                if self.strip_prefix and isinstance(value, str) and value.startswith(self.strip_prefix):
                    return value[len(self.strip_prefix) :]
                return value
        return None


class LocalStorageSource(CredentialSource):
    def __init__(self, domain: str, key: str):
        self.domain = domain
        self.key = key

    def extract(self, site_info: dict) -> Optional[str]:
        local_storage = CookiecloudAdapter().get_local_storage(self.domain)
        if local_storage:
            return local_storage.get(self.key)
        return None


class CredentialResolver:
    """凭据解析器。"""

    def __init__(self, site_info: dict):
        self.site_info = site_info

    def resolve(self, auth_source: dict | None) -> tuple[Optional[str], bool]:
        """返回 (token_value, need_sync)。"""
        if auth_source is None:
            return None, False
        source = self._build_source(auth_source)
        if isinstance(source, LocalStorageSource):
            return None, True
        return source.extract(self.site_info), False

    def resolve_after_sync(self, auth_source: dict | None) -> Optional[str]:
        if auth_source is None:
            return None
        return self._build_source(auth_source).extract(self.site_info)

    @staticmethod
    def sync_local_storage(hook_system):
        hook_system.emit("site.local_storage_sync", {})
        import time

        time.sleep(10)

    def _build_source(self, cfg: dict) -> CredentialSource:
        stype = cfg["type"]
        if stype == "header":
            return HeaderSource(cfg["name"], cfg.get("strip_prefix", ""))
        if stype == "local_storage":
            return LocalStorageSource(cfg["domain"], cfg["key"])
        raise ValueError(f"Unknown credential source type: {stype}")
