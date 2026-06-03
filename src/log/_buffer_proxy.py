"""LogBuffer 代理，线程安全延迟访问."""

from collections.abc import Iterator
from typing import Any

from log._buffer import LogBuffer

__all__ = ["LogBufferProxy", "get_log_buffer", "LOG_BUFFER"]

_log_buffer: LogBuffer | None = None


def get_log_buffer() -> LogBuffer:
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = LogBuffer(maxlen=200)
    return _log_buffer


class LogBufferProxy:
    """日志缓冲区的线程安全代理."""

    def append(self, level: str, text: str) -> int:
        return get_log_buffer().append(level, text)

    def get_logs(self, source: str | None = None, last_counter: int = 0) -> tuple[list[Any], int]:
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
