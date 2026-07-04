"""策略级分布式锁上下文管理器 — 自动续期。"""

import threading
from contextlib import contextmanager

import log
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager


@contextmanager
def strategy_lock(lock_key: str, ttl_seconds: int = 300, extend_interval: int = 60):
    """策略锁上下文管理器，持锁期间后台线程自动续期。

    :param lock_key: 锁 key
    :param ttl_seconds: 锁 TTL 秒数
    :param extend_interval: 续期间隔秒数
    :yield True 获取成功，False 已被其他实例持有
    """
    lock = get_lock_manager().create_lock(lock_key, ttl_seconds=ttl_seconds)
    acquired = lock.acquire()
    if not acquired:
        yield False
        return

    stop_event = threading.Event()

    def _extend_loop():
        while not stop_event.wait(extend_interval):
            try:
                lock.extend(ttl_seconds)
            except Exception as e:
                log.debug(f"[StrategyLock] 续期失败 {lock_key}: {e}")

    thread = threading.Thread(target=_extend_loop, daemon=True)
    thread.start()
    try:
        yield True
    finally:
        stop_event.set()
        thread.join(timeout=1)
        lock.release()
