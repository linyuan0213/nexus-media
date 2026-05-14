"""
通用异步任务队列
使用线程池并发消费任务，避免单个慢任务阻塞队列
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import log
from app.utils.commons import SingletonMeta


@dataclass
class Task:
    """任务单元"""

    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    retries: int = 3
    retry_delay: float = 1.0
    name: str = ""


class TaskQueue(metaclass=SingletonMeta):
    """
    通用异步任务队列（线程池并发消费）

    每个任务在独立线程中执行，一个慢任务不会阻塞其他任务
    """

    def __init__(self, max_workers: int = 5, maxsize: int = 1000):
        self._queue: queue.Queue[Task | None] = queue.Queue(maxsize=maxsize)
        self._dispatcher: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="TaskQueueWorker",
        )
        self._shutdown = False
        self._started = False
        self._max_workers = max_workers

    def start(self):
        """启动分发线程"""
        if self._started and self._dispatcher and self._dispatcher.is_alive():
            return
        self._shutdown = False
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True, name="TaskQueueDispatcher")
        self._dispatcher.start()
        self._started = True
        log.info(f"【TaskQueue】任务队列已启动（并发数: {self._max_workers}）")

    def stop(self, wait: bool = True, timeout: float = 30.0):
        """停止队列"""
        if not self._started:
            return
        self._shutdown = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if wait and self._dispatcher and self._dispatcher.is_alive():
            self._dispatcher.join(timeout=timeout)
        self._executor.shutdown(wait=wait)
        self._started = False
        log.info("【TaskQueue】任务队列已停止")

    def submit(self, func: Callable, *args, **kwargs) -> bool:
        """提交任务到队列"""
        if not self._started:
            self.start()

        name = kwargs.pop("name", func.__name__ if hasattr(func, "__name__") else "anonymous")
        retries = kwargs.pop("retries", 3)
        retry_delay = kwargs.pop("retry_delay", 1.0)

        task = Task(func=func, args=args, kwargs=kwargs, name=name, retries=retries, retry_delay=retry_delay)
        try:
            self._queue.put_nowait(task)
            return True
        except queue.Full:
            log.warning(f"【TaskQueue】队列已满，丢弃任务: {name}")
            return False

    def _dispatch_loop(self):
        """分发循环：从队列取任务，提交到线程池执行"""
        log.info("【TaskQueue】分发线程已启动")
        while not self._shutdown:
            try:
                task = self._queue.get(timeout=1)
                if task is None:
                    self._queue.task_done()
                    break
                self._executor.submit(self._run_task, task)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"【TaskQueue】分发异常: {e}")
        log.info("【TaskQueue】分发线程已退出")

    def _run_task(self, task: Task):
        """执行任务，带重试"""
        log.info(f"【TaskQueue】任务开始执行: {task.name}")
        for attempt in range(task.retries):
            try:
                task.func(*task.args, **task.kwargs)
                log.info(f"【TaskQueue】任务执行成功: {task.name}")
                return
            except Exception as e:
                log.error(f"【TaskQueue】任务 {task.name} 失败 ({attempt + 1}/{task.retries}): {e}")
                if attempt < task.retries - 1:
                    time.sleep(task.retry_delay * (attempt + 1))
        log.error(f"【TaskQueue】任务 {task.name} 最终失败，已丢弃")

    @property
    def pending(self) -> int:
        """待处理任务数"""
        return self._queue.qsize()
