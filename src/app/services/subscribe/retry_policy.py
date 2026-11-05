"""订阅搜索失败退避策略：限流/429 使用独立指数退避."""

from __future__ import annotations

try:
    from app.media.metadata.errors import ProviderRateLimited
except ImportError:  # pragma: no cover - 插件能力未加载时的兼容
    ProviderRateLimited = ()  # type: ignore[assignment,misc]

RATE_LIMIT_BASE_SECONDS = 60
RATE_LIMIT_MAX_SECONDS = 3600
_RATE_LIMIT_MARKERS = ("429", "too many request", "rate limit", "请求过于频繁", "请求過於頻繁", "限流")


def is_rate_limited(exc: BaseException) -> bool:
    """识别 provider/indexer 的限流错误，不依赖单一异常类型."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        if getattr(response, "status_code", None) == 429:
            return True
        if ProviderRateLimited and isinstance(current, ProviderRateLimited):
            return True
        message = str(current).lower()
        if any(marker in message for marker in _RATE_LIMIT_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


def backoff_seconds(attempt: int) -> int:
    """第 1 次 60s，第 2 次 120s，第 3 次 240s，上限 1h."""
    attempt = max(1, int(attempt or 1))
    return min(RATE_LIMIT_BASE_SECONDS * (2 ** (attempt - 1)), RATE_LIMIT_MAX_SECONDS)
