"""站点运行时配置：统一 profile、凭据和入口字段解析."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.sites.config import site_profile


class ProfileRouter:
    """唯一的 API profile 路由入口."""

    @staticmethod
    def candidates(site: Any, site_info: dict, capability: str) -> list[tuple[str, Any, dict]]:
        return site_profile.api_profile_candidates(site, site_info, capability)

    @staticmethod
    def resolve(site: Any, site_info: dict, capability: str) -> tuple[str, Any, dict]:
        candidates = ProfileRouter.candidates(site, site_info, capability)
        if candidates:
            return candidates[0]
        api = getattr(site, "api", None)
        return "", api, site_profile.profile_user_config(site_info, "")


@dataclass
class SiteRuntimeConfig:
    """一次站点操作的不可变运行时视图.

    调用方不再手工拼接 note/api_credentials/bearer_token 等字段。
    """

    site: Any
    site_info: dict
    capability: str
    profile_name: str
    api: Any
    user_config: dict = field(default_factory=dict)

    @classmethod
    def resolve(cls, site: Any, site_info: dict, capability: str) -> "SiteRuntimeConfig":
        name, api, user_config = ProfileRouter.resolve(site, site_info, capability)
        return cls(
            site=site,
            site_info=site_info,
            capability=capability,
            profile_name=name,
            api=api,
            user_config=user_config,
        )

    @property
    def cookie(self) -> str:
        return str(self.user_config.get("cookie") or "")

    @property
    def bearer_token(self) -> str:
        return str(self.user_config.get("bearer_token") or "")

    @property
    def api_key(self) -> str:
        return str(self.user_config.get("api_key") or "")

    @property
    def headers(self) -> dict:
        value = self.user_config.get("headers") or {}
        return value if isinstance(value, dict) else {}

    def as_search_config(self) -> dict:
        """兼容 ApiSiteSearcher 的旧构造参数，避免继续手工复制字段."""
        return {
            "site": self.site,
            "profile_name": self.profile_name,
            "api": self.api,
            "user_config": self.user_config,
        }
