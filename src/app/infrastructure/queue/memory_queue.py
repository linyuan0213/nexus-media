"""
内存消息队列 — 基于线程池的异步任务队列
"""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import log
from app.db.session import remove_session
from app.infrastructure.queue.base import MessageQueue


class MemoryMessageQueue(MessageQueue):
    """内存消息队列（尽力而为，进程重启丢失）"""

    def __init__(self, max_workers: int = 5, maxsize: int = 1000):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="MemMQ")
        self._dispatcher: threading.Thread | None = None
        self._shutdown = False
        self._started = False
        self._max_workers = max_workers

    def start(self) -> None:
        if self._started and self._dispatcher and self._dispatcher.is_alive():
            return
        self._shutdown = False
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True, name="MemMQDispatcher")
        self._dispatcher.start()
        self._started = True
        log.info(f"[MemoryMessageQueue]内存队列已启动（并发数: {self._max_workers}）")

    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        if not self._started:
            return
        self._shutdown = True
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(None)
        if wait and self._dispatcher and self._dispatcher.is_alive():
            self._dispatcher.join(timeout=timeout)
        self._executor.shutdown(wait=wait)
        self._started = False
        log.info("[MemoryMessageQueue]内存队列已停止")

    def submit(self, func: Callable, *args, name: str = "", **kwargs) -> bool:
        if not self._started:
            self.start()
        try:
            self._queue.put_nowait((func, args, kwargs, name))
            log.info(f"[MemoryMessageQueue]任务已提交: {name}, 队列长度: {self._queue.qsize()}")
            return True
        except queue.Full:
            log.warn(f"[MemoryMessageQueue]队列已满，丢弃任务: {name}")
            return False

    def is_available(self) -> bool:
        return True

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def _dispatch_loop(self):
        log.info("[MemoryMessageQueue]分发线程已启动")
        while not self._shutdown:
            try:
                item = self._queue.get(timeout=1)
                if item is None:
                    self._queue.task_done()
                    break
                func, args, kwargs, name = item
                log.info(f"[MemoryMessageQueue]分发任务: {name}, 队列剩余: {self._queue.qsize()}")
                self._executor.submit(self._run_task, func, args, kwargs, name)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"[MemoryMessageQueue]分发异常: {e}")
        log.info("[MemoryMessageQueue]分发线程已退出")

    def _run_task(self, func, args, kwargs, name):
        try:
            func(*args, **kwargs)
            log.info(f"[MemoryMessageQueue]任务执行成功: {name}")
        except Exception as e:
            log.error(f"[MemoryMessageQueue]任务 {name} 失败: {e}")
        finally:
            remove_session()
