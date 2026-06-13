import json
import threading
import time
from collections.abc import Iterator

import log


class LogStreamingService:
    """
    实时日志 SSE 服务。
    封装全局状态与迭代逻辑，避免污染路由文件。
    """

    def __init__(self, buffer=None, sleep_interval: float = 0.3):
        self._sleep_interval = sleep_interval
        self._lock = threading.Lock()
        self._source_map: dict[str, int] = {}
        self._buffer = buffer
        if buffer is None:
            # 触发 LogBuffer 的懒加载，确保 SSE 首次连接时缓冲区已就绪
            self._get_buffer()

    def _get_buffer(self):
        if self._buffer is None:
            self._buffer = log.LOG_BUFFER
        return self._buffer

    def stream(self, source: str = "") -> Iterator[str]:
        """
        SSE 数据流生成器。
        首次连接时推送当前内存缓冲区中的全部历史日志，
        之后只推送增量，保持与旧版行为一致。
        """
        key = source or "__all__"
        first_yield = True

        while True:
            with self._lock:
                buffer = self._get_buffer()
                if first_yield:
                    # 首次连接：推送缓冲区内的全部现有日志
                    total = getattr(buffer, "counter", len(buffer))
                    buf_len = len(buffer)
                    last_counter = max(0, total - buf_len)
                    first_yield = False
                else:
                    last_counter = self._source_map.get(key, 0)
                    total = getattr(buffer, "counter", len(buffer))
                    # 如果客户端切换了 source，重置索引
                    if last_counter > total:
                        last_counter = total
                logs, next_counter = buffer.get_logs(source=source or None, last_counter=last_counter)
                self._source_map[key] = next_counter

            if logs:
                yield f"data: {json.dumps(logs)}\n\n"
            time.sleep(self._sleep_interval)
