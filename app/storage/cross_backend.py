"""跨后端复制引擎。"""

from typing import BinaryIO

from app.storage.backends.base import StorageBackend


def cross_copy(
    src_backend: StorageBackend,
    src_path: str,
    dst_backend: StorageBackend,
    dst_path: str,
    chunk_size: int = 8 * 1024 * 1024,
) -> None:
    """
    跨后端复制文件。

    策略（按优先级）：
    1. 服务端 COPY：dst_backend 支持从 src_backend 快速复制
    2. 流式传输：src.read_stream → dst.write_stream（分块）
    """
    try:
        if src_backend.can_fast_cross_copy(dst_backend):
            src_backend.cross_copy_to(src_path, dst_backend, dst_path)
            return
    except Exception:
        pass

    stream: BinaryIO = src_backend.read_stream(src_path)
    try:
        dst_backend.mkdir(dst_path, parents=True)
        dst_backend.write_stream(dst_path, stream)
    finally:
        stream.close()


def cross_move(
    src_backend: StorageBackend,
    src_path: str,
    dst_backend: StorageBackend,
    dst_path: str,
) -> None:
    """跨后端移动 = 跨后端复制 + 源端删除。"""
    cross_copy(src_backend, src_path, dst_backend, dst_path)
    src_backend.remove(src_path)
