from dataclasses import dataclass

from app.core.settings import settings


@dataclass
class ProviderConfig:
    """LLM 提供商配置"""

    name: str
    api_key: str
    api_url: str
    model: str
    proxy: str | None = None
    timeout: int = 60


def get_provider(provider_name: str = "") -> ProviderConfig | None:
    """获取 LLM 提供商配置"""
    cfg = settings.get("agent") or {}
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
