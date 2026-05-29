import re
import threading
import time
from collections import deque
from typing import Any


class LogBuffer:
    """
    线程安全的内存日志缓冲区，用于实时日志推送。
    通过单调递增计数器解决 maxlen 场景下无法识别新增日志的问题。
    """

    _SOURCE_PATTERN = re.compile(r"(?<=【).*?(?=】)")

    def __init__(self, maxlen: int = 200):
        self._queue: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0

    def append(self, level: str, text: str) -> int:
        """添加一条日志记录，返回当前计数器值。
        不再做 html.escape，Vue 前端会自动处理 XSS 防护。
        """
        if text.startswith("【"):
            match = self._SOURCE_PATTERN.search(text)
            if match:
                source = match.group(0)
                text = text.replace(f"【{source}】", "")
            else:
                source = "System"
        else:
            source = "System"

        log_entry = {
            "time": time.strftime("%H:%M:%S", time.localtime(time.time())),
            "level": level,
            "source": source,
            "text": text,
        }
        with self._lock:
            self._queue.append(log_entry)
            self._counter += 1
            return self._counter

    def get_logs(self, source: str | None = None, last_counter: int = 0) -> tuple[list[dict[str, Any]], int]:
        """
        获取自 last_counter 以来新增的所有日志。
        返回 (logs, current_counter)。
        """
        with self._lock:
            total = self._counter
            if last_counter >= total:
                return [], total
            # 当队列满时，旧数据会被丢弃，实际可获取的新条目数受队列长度限制
            count = min(total - last_counter, len(self._queue))
            logs = list(self._queue)[-count:] if count > 0 else []
        if source:
            logs = [lg for lg in logs if lg.get("source") == source]
        return logs, total

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def __iter__(self):
        with self._lock:
            return iter(list(self._queue))

    def __getitem__(self, index):
        with self._lock:
            return list(self._queue)[index]

    @property
    def counter(self) -> int:
        with self._lock:
            return self._counter
