"""Site rate limiter service — 站点限流服务.

替换旧的 app/sites/site_limiter.py，使用 RateLimitEngine 统一限流框架.
"""

import json
import threading

from app.infrastructure.rate_limiter import RateLimitEngine


class SiteRateLimiterService:
    """站点限流服务 — 按站点 ID 管理限流."""

    def __init__(self, engine: RateLimitEngine | None = None):
        self._engine = engine or RateLimitEngine()
        self._site_rates: dict[str, tuple[str, int]] = {}
        self._lock = threading.Lock()

    def register_site(self, site_id: str, site_note: str | dict | None) -> None:
        """注册站点限流配置.

        支持新旧两种配置格式：
        - 旧: {"limit_interval": 60, "limit_count": 10, "limit_seconds": 10}
        - 新: {"rate_limit": "10/m", "rate_burst": 10}
        """
        note = site_note if isinstance(site_note, dict) else {}
        if isinstance(site_note, str):
            try:
                note = json.loads(site_note)
            except json.JSONDecodeError:
                note = {}

        # 优先使用新配置格式
        rate_str = note.get("rate_limit")
        burst = note.get("rate_burst")

        if not rate_str:
            # 兼容旧配置格式
            limit_interval = note.get("limit_interval")
            limit_count = note.get("limit_count")
            limit_seconds = note.get("limit_seconds")

            if limit_interval and limit_count:
                # 转换为 rate 格式
                rate_str = f"{limit_count}/{limit_interval}s"
                if burst is None:
                    burst = int(limit_count)
            elif limit_seconds:
                # 只有访问间隔限制，转换为 rate
                rate_str = f"1/{limit_seconds}s"
                if burst is None:
                    burst = 1

        if not rate_str:
            # 默认不限流
            with self._lock:
                self._site_rates.pop(site_id, None)
            return

        if burst is None:
            # 默认 burst 等于 rate 的 count
            try:
                count = float(rate_str.split("/")[0])
                burst = int(count)
            except (ValueError, IndexError):
                burst = 10

        with self._lock:
            self._site_rates[site_id] = (rate_str, burst)

    def check(self, site_id: str, timeout: float | None = 0) -> bool:
        """检查站点是否触发流控.

        :param site_id: 站点 ID
        :param timeout: 等待秒数，0=立即返回，None=不等待直接返回 False
        :return: True=触发了流控（未获得许可），False=未触发
        """
        with self._lock:
            config = self._site_rates.get(site_id)
        if not config:
            return False

        rate_str, burst = config
        key = f"site:{site_id}"
        acquired = self._engine.acquire(key, rate=rate_str, burst=burst, timeout=timeout)
        return not acquired

    @property
    def engine(self) -> RateLimitEngine:
        """暴露底层限流引擎，供 HttpClient 注入使用."""
        return self._engine

    def get_rate(self, site_id: str) -> tuple[str, int] | None:
        """获取站点限流配置.

        :return: (rate_str, burst) 或 None（未配置限流）
        """
        with self._lock:
            return self._site_rates.get(site_id)

    def get_status(self, site_id: str | None = None) -> dict:
        """获取站点限流状态."""
        if site_id:
            key = f"site:{site_id}"
            return self._engine.get_status(key)
        return self._engine.get_status()
