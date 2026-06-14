"""本地文件系统存储后端。"""

import os
import shutil
from collections.abc import Iterator
from typing import BinaryIO

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class LocalStorageBackend(StorageBackend):
    """
    本地文件系统后端。

    直接替换 SystemUtils 的 copy/move/link/softlink，
    不再通过 subprocess 或外部命令。
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)

    def _resolve(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(path))

    def exists(self, path: str) -> bool:
        return os.path.exists(self._resolve(path))

    def stat(self, path: str) -> FileInfo | None:
        rp = self._resolve(path)
        if not os.path.exists(rp):
            return None
        st = os.stat(rp)
        return FileInfo(
            path=path,
            size=st.st_size,
            mtime=st.st_mtime,
            is_dir=os.path.isdir(rp),
        )

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        rp = self._resolve(path)
        for entry in os.scandir(rp):
            yield FileInfo(
                path=entry.path,
                size=entry.stat().st_size if entry.is_file() else 0,
                mtime=entry.stat().st_mtime,
                is_dir=entry.is_dir(),
            )

    def read_stream(self, path: str) -> BinaryIO:
        return open(self._resolve(path), "rb")

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0, chunk_size: int = 0) -> None:
        rp = self._resolve(path)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        # 使用 chunk_size 或默认 1MB 缓冲区，避免大文件拷贝时频繁小 IO
        length = chunk_size if chunk_size > 0 else 1024 * 1024
        with open(rp, "wb") as f:
            shutil.copyfileobj(stream, f, length=length)

    def mkdir(self, path: str, parents: bool = True) -> None:
        rp = self._resolve(path)
        if parents:
            os.makedirs(rp, exist_ok=True)
        else:
            os.mkdir(rp)

    def remove(self, path: str, recursive: bool = False) -> None:
        rp = self._resolve(path)
        if not rp or rp == "/":
            raise ValueError("不能删除根目录")
        if os.path.isdir(rp):
            if recursive:
                shutil.rmtree(rp)
            else:
                os.rmdir(rp)
        else:
            os.remove(rp)

    def copy(self, src: str, dst: str) -> None:
        src_rp = self._resolve(src)
        dst_rp = self._resolve(dst)
        os.makedirs(os.path.dirname(dst_rp), exist_ok=True)
        shutil.copy2(src_rp, dst_rp)

    def move(self, src: str, dst: str) -> None:
        src_rp = self._resolve(src)
        dst_rp = self._resolve(dst)
        os.makedirs(os.path.dirname(dst_rp), exist_ok=True)
        shutil.move(src_rp, dst_rp)

    def hardlink(self, src: str, dst: str) -> None:
        src_rp = self._resolve(src)
        dst_rp = self._resolve(dst)
        os.makedirs(os.path.dirname(dst_rp), exist_ok=True)
        os.link(src_rp, dst_rp)

    def softlink(self, src: str, dst: str) -> None:
        src_rp = self._resolve(src)
        dst_rp = self._resolve(dst)
        os.makedirs(os.path.dirname(dst_rp), exist_ok=True)
        os.symlink(src_rp, dst_rp)

    def health_check(self) -> tuple[bool, str]:
        return True, "本地文件系统"
