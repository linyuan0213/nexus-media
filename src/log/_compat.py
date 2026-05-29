"""
向后兼容的别名与符号。
"""

from ._buffer_proxy import LOG_BUFFER

__all__ = ["LOG_QUEUE", "LOG_INDEX"]

LOG_QUEUE = LOG_BUFFER
LOG_INDEX = property(lambda _self: len(LOG_BUFFER))
