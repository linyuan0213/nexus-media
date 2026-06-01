"""下载协调器 — 防止多条流水线重复下载同一订阅资源.

使用分布式锁实现跨实例防重，基于 TMDB ID + 季生成唯一锁 key.
"""

from app.infrastructure.distributed_lock.base import DistributedLock
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager


class DownloadCoordinator:
    """防止多条流水线重复下载同一订阅的资源.

    基于分布式锁，同一时刻只能有一个实例在处理同一个 TMDB ID + 季的下载。
    """

    def __init__(self, lock_manager=None):
        self._lock_manager = lock_manager or get_lock_manager()
        self._locks: dict[str, DistributedLock] = {}

    def try_acquire(self, media_info) -> bool:
        """尝试获取下载锁，成功返回 True."""
        season = media_info.get_season_string() if hasattr(media_info, "get_season_string") else ""
        key = f"subscribe:download:{media_info.tmdb_id}:{season}"
        if key in self._locks:
            return True
        lock = self._lock_manager.create_lock(key, ttl_seconds=1800)
        if lock.acquire():
            self._locks[key] = lock
            return True
        return False

    def release(self, media_info) -> None:
        """释放下载锁."""
        season = media_info.get_season_string() if hasattr(media_info, "get_season_string") else ""
        key = f"subscribe:download:{media_info.tmdb_id}:{season}"
        lock = self._locks.pop(key, None)
        if lock:
            lock.release()

    def is_locked(self, media_info) -> bool:
        """检查是否已被锁定（本实例或其他实例）."""
        season = media_info.get_season_string() if hasattr(media_info, "get_season_string") else ""
        key = f"subscribe:download:{media_info.tmdb_id}:{season}"
        if key in self._locks:
            return True
        # 尝试获取一个极短 TTL 的锁，成功说明无人持有
        lock = self._lock_manager.create_lock(key, ttl_seconds=1)
        if lock.acquire():
            lock.release()
            return False
        return True
