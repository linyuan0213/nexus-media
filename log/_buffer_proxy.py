# -*- coding: utf-8 -*-
"""
LogBuffer 延迟加载代理，避免顶层导入导致循环引用。
"""

from typing import Any, Iterator, List, Optional, Tuple

__all__ = ["LogBufferProxy", "get_log_buffer", "LOG_BUFFER"]

_log_buffer = None


def get_log_buffer():
    global _log_buffer
    if _log_buffer is None:
        from app.utils.log_buffer import LogBuffer
        _log_buffer = LogBuffer(maxlen=200)
    return _log_buffer


class LogBufferProxy:
    """延迟加载 LogBuffer 的代理对象。"""

    def append(self, level: str, text: str) -> int:
        return get_log_buffer().append(level, text)

    def get_logs(
        self, source: Optional[str] = None, last_counter: int = 0
    ) -> Tuple[List[Any], int]:
        return get_log_buffer().get_logs(source=source, last_counter=last_counter)

    @property
    def counter(self) -> int:
        return get_log_buffer().counter

    def __len__(self) -> int:
        return len(get_log_buffer())

    def __iter__(self) -> Iterator[Any]:
        return iter(get_log_buffer())

    def __getitem__(self, index: Any) -> Any:
        return get_log_buffer().__getitem__(index)


LOG_BUFFER = LogBufferProxy()
