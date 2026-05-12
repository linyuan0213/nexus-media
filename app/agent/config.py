from dataclasses import dataclass
from typing import Optional

from config import Config


@dataclass
class ProviderConfig:
    """LLM 提供商配置"""

    name: str
    api_key: str
    api_url: str
    model: str
    proxy: Optional[str] = None
    timeout: int = 60


def get_provider(provider_name: str = "") -> Optional[ProviderConfig]:
    """获取 LLM 提供商配置"""
    cfg = Config().get_config("agent") or {}
    if not cfg.get("enabled"):
        return None
    providers = cfg.get("providers", {})
    if not provider_name:
        provider_name = cfg.get("default_provider", "")
    if not provider_name:
        return None
    p = providers.get(provider_name)
    if not p:
        return None
    return ProviderConfig(
        name=provider_name,
        api_key=p.get("api_key", ""),
        api_url=p.get("api_url", ""),
        model=p.get("model", ""),
        proxy=p.get("proxy"),
    )
