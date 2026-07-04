"""下载协调器 — 防止多条流水线重复下载同一订阅资源.

使用分布式锁实现跨实例防重，基于 TMDB ID + 季生成唯一锁 key.
"""

from app.infrastructure.distributed_lock.base import DistributedLock
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager


class DownloadCoordinator:
    """防止多条流水线重复下载同一订阅的资源.

    基于分布式锁，同一时刻只能有一个实例/策略在处理同一个 TMDB ID + 季的下载。
    每次 try_acquire 都直接尝试 Redis 锁，避免同实例内多策略并发穿透。
    锁默认 TTL 300 秒，并由持锁方主动续期，避免策略崩溃后长时间阻塞。
    """

    DEFAULT_LOCK_TTL = 300

    def __init__(self, lock_manager=None):
        self._lock_manager = lock_manager or get_lock_manager()
        self._locks: dict[str, DistributedLock] = {}

    def _key(self, media_info) -> str:
        season = media_info.get_season_string() if hasattr(media_info, "get_season_string") else ""
        tmdb_id = getattr(media_info, "tmdb_id", "") or ""
        if tmdb_id:
            return f"subscribe:download:{tmdb_id}:{season}"
        rssid = getattr(media_info, "rssid", "") or ""
        if rssid:
            return f"subscribe:download:rssid:{rssid}"
        title = getattr(media_info, "title", "") or "unknown"
        year = getattr(media_info, "year", "") or ""
        return f"subscribe:download:manual:{title}:{year}:{season}"

    def try_acquire(self, media_info) -> bool:
        """尝试获取下载锁，成功返回 True."""
        key = self._key(media_info)
        lock = self._lock_manager.create_lock(key, ttl_seconds=self.DEFAULT_LOCK_TTL)
        if lock.acquire():
            self._locks[key] = lock
            return True
        return False

    def release(self, media_info) -> None:
        """释放下载锁."""
        key = self._key(media_info)
        lock = self._locks.pop(key, None)
        if lock:
            lock.release()

    def extend(self, media_info, additional_seconds: int | None = None) -> bool:
        """延长指定媒体锁的过期时间；默认续期一个 TTL."""
        key = self._key(media_info)
        lock = self._locks.get(key)
        if not lock:
            return False
        return lock.extend(additional_seconds or self.DEFAULT_LOCK_TTL)

    def is_locked(self, media_info) -> bool:
        """检查是否已被锁定（本实例或其他实例）."""
        key = self._key(media_info)
        if key in self._locks:
            return True
        # 尝试获取一个极短 TTL 的锁，成功说明无人持有
        lock = self._lock_manager.create_lock(key, ttl_seconds=1)
        if lock.acquire():
            lock.release()
            return False
        return True
