"""RateLimitMonitor - 限流监控统计."""

import threading


class RateLimitMonitor:
    """限流状态监控器."""

    def __init__(self):
        self._stats: dict[str, dict] = {}
        self._lock = threading.Lock()

    def record(self, key: str, acquired: bool, wait_time: float = 0) -> None:
        """记录一次限流事件."""
        with self._lock:
            stats = self._stats.setdefault(key, {"total": 0, "blocked": 0, "waited": 0, "total_wait": 0})
            stats["total"] += 1
            if not acquired:
                stats["blocked"] += 1
            elif wait_time > 0:
                stats["waited"] += 1
                stats["total_wait"] += wait_time

    def get_stats(self, key: str | None = None) -> dict:
        """获取统计信息."""
        with self._lock:
            if key:
                return self._stats.get(key, {}).copy()
            return {k: v.copy() for k, v in self._stats.items()}

    def reset(self, key: str | None = None) -> None:
        """重置统计."""
        with self._lock:
            if key:
                self._stats.pop(key, None)
            else:
                self._stats.clear()
