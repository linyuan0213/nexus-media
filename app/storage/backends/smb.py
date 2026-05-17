"""SMB 存储后端。"""

import shutil
from collections.abc import Iterator
from typing import BinaryIO

from smbclient import (
    copyfile,
    makedirs,
    mkdir,
    open_file,
    register_session,
    remove,
    rmdir,
    scandir,
)
from smbclient import stat as smb_stat
from smbclient.path import exists as smb_exists
from smbclient.path import isdir
from smbclient.shutil import rmtree

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class SMBStorageBackend(StorageBackend):
    """SMB 存储后端。"""

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._server = getattr(config, "server", "")
        self._share = getattr(config, "share", "")
        if not self._server or not self._share:
            raise ValueError("SMB server 和 share 不能为空")
        self._username = getattr(config, "username", "")
        self._password = getattr(config, "password", "")
        self._port = int(getattr(config, "port", 445) or 445)
        self._base = f"\\\\{self._server}\\{self._share}"
        if self._username:
            register_session(
                self._server,
                username=self._username,
                password=self._password,
                port=self._port,
            )

    def _path(self, path: str) -> str:
        p = path.lstrip("/").replace("/", "\\")
        if p:
            return f"{self._base}\\{p}"
        return self._base

    def exists(self, path: str) -> bool:
        return smb_exists(self._path(path))

    def stat(self, path: str) -> FileInfo | None:
        try:
            st = smb_stat(self._path(path))
            return FileInfo(
                path=path,
                size=st.st_size,
                mtime=st.st_mtime,
                is_dir=isdir(self._path(path)),
            )
        except Exception:
            return None

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        rp = self._path(path)
        for entry in scandir(rp):
            st = entry.stat()
            yield FileInfo(
                path=path.rstrip("/") + "/" + entry.name,
                size=st.st_size if not entry.is_dir() else 0,
                mtime=st.st_mtime,
                is_dir=entry.is_dir(),
            )

    def read_stream(self, path: str) -> BinaryIO:
        return open_file(self._path(path), mode="rb")

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        rp = self._path(path)
        makedirs(self._dir(rp), exist_ok=True)
        with open_file(rp, mode="wb") as f:
            shutil.copyfileobj(stream, f)

    def _dir(self, path: str) -> str:
        return path.rsplit("\\", 1)[0] if "\\" in path else path

    def mkdir(self, path: str, parents: bool = True) -> None:
        rp = self._path(path)
        if parents:
            makedirs(rp, exist_ok=True)
        else:
            mkdir(rp)

    def remove(self, path: str, recursive: bool = False) -> None:
        rp = self._path(path)
        if isdir(rp):
            if recursive:
                rmtree(rp)
            else:
                rmdir(rp)
        else:
            remove(rp)

    def copy(self, src: str, dst: str) -> None:
        copyfile(self._path(src), self._path(dst))

    def move(self, src: str, dst: str) -> None:
        shutil.move(self._path(src), self._path(dst))

    def health_check(self) -> tuple[bool, str]:
        try:
            for _ in self.list_dir("/"):
                break
            return True, "连接成功"
        except Exception as e:
            return False, str(e)
