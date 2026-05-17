"""OpenList / AList 存储后端。"""

import datetime
import posixpath
from collections.abc import Iterator
from typing import BinaryIO

import requests

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class OpenListStorageBackend(StorageBackend):
    """OpenList 存储后端。

    参考 API: https://fox.oplist.org/
    认证: 支持直接填 token 或 username/password 登录获取 JWT。
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._base = getattr(config, "base_url", "").rstrip("/")
        self._token = getattr(config, "api_token", "")
        self._username = getattr(config, "username", "")
        self._password = getattr(config, "password", "")
        self._write_enabled = getattr(config, "write_enabled", False)
        self._session = requests.Session()
        if not self._token and self._username and self._password:
            self._login()
        if self._token:
            self._session.headers["Authorization"] = self._token

    def _login(self) -> None:
        """通过 username/password 获取 JWT token。"""
        url = f"{self._base}/api/auth/login"
        resp = self._session.post(
            url,
            json={"username": self._username, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(data.get("message", "login failed"))
        self._token = data["data"]["token"]
        self._session.headers["Authorization"] = self._token

    def _api(self, endpoint: str, method: str = "POST", **kwargs):
        url = f"{self._base}/api/fs/{endpoint.lstrip('/')}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(data.get("message", "unknown error"))
        return data.get("data", {})

    @staticmethod
    def _parse_mtime(value) -> float:
        """解析 OpenList 返回的 modified/created 时间为 Unix 时间戳。"""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0

    def exists(self, path: str) -> bool:
        try:
            return self.stat(path) is not None
        except Exception:
            return False

    def stat(self, path: str) -> FileInfo | None:
        try:
            data = self._api("get", json={"path": path, "password": ""})
            return FileInfo(
                path=path,
                size=int(data.get("size", 0) or 0),
                mtime=self._parse_mtime(data.get("modified")),
                is_dir=bool(data.get("is_dir", False)),
            )
        except Exception:
            return None

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        page = 1
        per_page = 100
        while True:
            data = self._api(
                "list",
                json={"path": path, "password": "", "page": page, "per_page": per_page},
            )
            items = data.get("content", [])
            for item in items:
                yield FileInfo(
                    path=posixpath.join(path.rstrip("/"), item.get("name", "")),
                    size=int(item.get("size", 0) or 0),
                    mtime=self._parse_mtime(item.get("modified")),
                    is_dir=bool(item.get("is_dir", False)),
                )
            if len(items) < per_page:
                break
            page += 1

    def read_stream(self, path: str) -> BinaryIO:
        data = self._api("get", json={"path": path, "password": ""})
        raw_url = data.get("raw_url") or data.get("url")
        if not raw_url:
            raise RuntimeError("无法获取文件下载地址")
        resp = self._session.get(raw_url, stream=True, timeout=60)
        resp.raise_for_status()
        return resp.raw  # type: ignore[return-value]

    def _get_stream_size(self, stream: BinaryIO) -> int:
        """尝试获取流的大小。"""
        try:
            pos = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(pos)
            return size
        except Exception:
            return 0

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        if not self._write_enabled:
            raise NotImplementedError("OpenList 后端未启用写入")
        url = f"{self._base}/api/fs/put"
        headers = {"File-Path": path}
        actual_size = size or self._get_stream_size(stream)
        if actual_size > 0:
            headers["Content-Length"] = str(actual_size)
        resp = self._session.put(url, headers=headers, data=stream, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(data.get("message", "upload failed"))

    def mkdir(self, path: str, parents: bool = True) -> None:
        if not self._write_enabled:
            raise NotImplementedError("OpenList 后端未启用写入")
        self._api("mkdir", json={"path": path})

    def remove(self, path: str, recursive: bool = False) -> None:
        if not self._write_enabled:
            raise NotImplementedError("OpenList 后端未启用写入")
        parent = posixpath.dirname(path.rstrip("/"))
        name = posixpath.basename(path.rstrip("/"))
        self._api("remove", json={"dir": parent, "names": [name]})

    def copy(self, src: str, dst: str) -> None:
        if not self._write_enabled:
            raise NotImplementedError("OpenList 后端未启用写入")
        src_dir = posixpath.dirname(src.rstrip("/"))
        dst_dir = posixpath.dirname(dst.rstrip("/"))
        self._api(
            "copy",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [posixpath.basename(src.rstrip("/"))],
            },
        )

    def move(self, src: str, dst: str) -> None:
        if not self._write_enabled:
            raise NotImplementedError("OpenList 后端未启用写入")
        src_dir = posixpath.dirname(src.rstrip("/"))
        dst_dir = posixpath.dirname(dst.rstrip("/"))
        self._api(
            "move",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [posixpath.basename(src.rstrip("/"))],
            },
        )

    def health_check(self) -> tuple[bool, str]:
        try:
            self._api("list", json={"path": "/", "password": ""})
            return True, "连接成功"
        except Exception as e:
            return False, str(e)
