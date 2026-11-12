"""站点请求限流参数."""

from typing import Any


def get_rate_limit_kwargs(engine: Any, site: Any) -> dict:
    """获取限流参数（供 HttpClient 使用）."""
    site_limiter = getattr(engine, "site_limiter", None)
    if not site_limiter or not site or not getattr(site, "id", None):
        return {}
    rate_config = site_limiter.get_rate(str(site.id))
    if not rate_config:
        return {}
    return {
        "rate_limit_key": f"site:{site.id}",
        "rate_limit_rate": rate_config[0],
        "rate_limit_burst": rate_config[1],
    }
