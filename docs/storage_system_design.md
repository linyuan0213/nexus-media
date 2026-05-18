# 多存储后端文件同步系统重构设计

## 1. 设计原则

- **彻底替换**：`TransferActionEngine`、`SyncCore`、`RmtMode` 枚举、`SystemUtils` 文件操作方法全部废弃，不保留兼容层。
- **单一抽象**：所有存储通过 `StorageBackend` 接口操作，上层完全无感知。
- **配置驱动**：存储后端通过数据库配置动态创建。
- **流式优先**：跨后端传输强制流式读写。
- **操作即字符串**：转移模式为 `"copy"` / `"move"` / `"link"` / `"softlink"`，由后端自身判断支持性。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│ 应用层                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐    │
│  │ SyncEngine  │  │TransferEngine│  │ MediaFileScanner │    │
│  └─────────────┘  └─────────────┘  └──────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│ 调度层                                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         CrossBackendEngine（跨后端复制/移动）         │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│ 存储层                                                       │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Local  │ │ WebDAV │ │  SMB   │ │   S3   │ │ Rclone │  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
├─────────────────────────────────────────────────────────────┤
│ 数据层                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Entity     │  │  Repository  │  │   Adapter    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 存储层

### 3.1 抽象接口 `app/storage/backends/base.py`

```python
"""存储后端抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import BinaryIO, Iterator


class StorageType(Enum):
    LOCAL = auto()
    WEBDAV = auto()
    SMB = auto()
    S3 = auto()
    RCLONE = auto()
    OPENLIST = auto()


@dataclass(frozen=True)
class FileInfo:
    path: str
    size: int
    mtime: float
    is_dir: bool
    mime_type: str = ""


@dataclass
class StorageConfig:
    id: str
    name: str
    type: StorageType
    enabled: bool = True


class StorageBackend(ABC):
    """所有文件操作的唯一入口。"""

    def __init__(self, config: StorageConfig) -> None:
        self.config = config

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def stat(self, path: str) -> FileInfo | None: ...

    @abstractmethod
    def list_dir(self, path: str) -> Iterator[FileInfo]: ...

    @abstractmethod
    def mkdir(self, path: str, parents: bool = True) -> None: ...

    @abstractmethod
    def remove(self, path: str, recursive: bool = False) -> None: ...

    @abstractmethod
    def read_stream(self, path: str) -> BinaryIO: ...

    @abstractmethod
    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None: ...

    @abstractmethod
    def copy(self, src: str, dst: str) -> None: ...

    @abstractmethod
    def move(self, src: str, dst: str) -> None: ...

    def hardlink(self, src: str, dst: str) -> None:
        raise NotImplementedError(f"{self.config.type.name} 不支持硬链接")

    def softlink(self, src: str, dst: str) -> None:
        raise NotImplementedError(f"{self.config.type.name} 不支持软链接")
```

### 3.2 工厂 `app/storage/factory.py`

```python
from typing import ClassVar

from app.storage.backends.base import StorageBackend, StorageConfig, StorageType


class StorageBackendFactory:
    _registry: ClassVar[dict[StorageType, type[StorageBackend]]] = {}

    @classmethod
    def register(cls, stype: StorageType, backend_cls: type[StorageBackend]) -> None:
        cls._registry[stype] = backend_cls

    @classmethod
    def create(cls, config: StorageConfig) -> StorageBackend:
        backend_cls = cls._registry.get(config.type)
        if not backend_cls:
            raise ValueError(f"不支持的存储类型: {config.type}")
        return backend_cls(config)

    @classmethod
    def list_types(cls) -> list[StorageType]:
        return list(cls._registry.keys())
```

### 3.3 跨后端引擎 `app/storage/cross_backend.py`

```python
from typing import BinaryIO

from app.storage.backends.base import StorageBackend


class CrossBackendEngine:
    DEFAULT_CHUNK_SIZE: int = 8 * 1024 * 1024

    @classmethod
    def copy(
        cls,
        src_backend: StorageBackend,
        src_path: str,
        dst_backend: StorageBackend,
        dst_path: str,
    ) -> None:
        if src_backend.config.type == dst_backend.config.type:
            try:
                src_backend.copy(src_path, dst_path)
                return
            except Exception:
                pass

        stream: BinaryIO = src_backend.read_stream(src_path)
        try:
            dst_backend.mkdir(dst_path, parents=True)
            dst_backend.write_stream(dst_path, stream)
        finally:
            stream.close()

    @classmethod
    def move(
        cls,
        src_backend: StorageBackend,
        src_path: str,
        dst_backend: StorageBackend,
        dst_path: str,
    ) -> None:
        cls.copy(src_backend, src_path, dst_backend, dst_path)
        src_backend.remove(src_path)
```

### 3.4 配置模型 `app/storage/config_models.py`

```python
from dataclasses import dataclass

from app.storage.backends.base import StorageConfig, StorageType


@dataclass
class LocalStorageConfig(StorageConfig):
    type: StorageType = StorageType.LOCAL


@dataclass
class WebDAVStorageConfig(StorageConfig):
    type: StorageType = StorageType.WEBDAV
    url: str = ""
    username: str = ""
    password: str = ""
    ssl_verify: bool = True
    connect_timeout: int = 10
    read_timeout: int = 30
    chunk_size: int = 8 * 1024 * 1024


@dataclass
class SMBStorageConfig(StorageConfig):
    type: StorageType = StorageType.SMB
    server: str = ""
    share: str = ""
    port: int = 445
    username: str = ""
    password: str = ""
    domain: str = ""
    mount_point: str = ""


@dataclass
class S3StorageConfig(StorageConfig):
    type: StorageType = StorageType.S3
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    region: str = "us-east-1"
    secure: bool = True


@dataclass
class RcloneStorageConfig(StorageConfig):
    type: StorageType = StorageType.RCLONE
    remote_name: str = ""
    rc_url: str = ""
    rc_user: str = ""
    rc_pass: str = ""


@dataclass
class OpenListStorageConfig(StorageConfig):
    type: StorageType = StorageType.OPENLIST
    base_url: str = ""
    api_token: str = ""
    write_enabled: bool = False
```

### 3.5 后端实现

#### Local `app/storage/backends/local.py`

```python
import os
import shutil
from typing import BinaryIO, Iterator

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class LocalStorageBackend(StorageBackend):
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
        return FileInfo(path=path, size=st.st_size, mtime=st.st_mtime, is_dir=os.path.isdir(rp))

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        for entry in os.scandir(self._resolve(path)):
            yield FileInfo(
                path=entry.path,
                size=entry.stat().st_size if entry.is_file() else 0,
                mtime=entry.stat().st_mtime,
                is_dir=entry.is_dir(),
            )

    def read_stream(self, path: str) -> BinaryIO:
        return open(self._resolve(path), "rb")

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        rp = self._resolve(path)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "wb") as f:
            shutil.copyfileobj(stream, f)

    def mkdir(self, path: str, parents: bool = True) -> None:
        rp = self._resolve(path)
        if parents:
            os.makedirs(rp, exist_ok=True)
        else:
            os.mkdir(rp)

    def remove(self, path: str, recursive: bool = False) -> None:
        rp = self._resolve(path)
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
```

#### WebDAV `app/storage/backends/webdav.py`

```python
import os
from typing import BinaryIO, Iterator

import requests

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class WebDAVStorageBackend(StorageBackend):
    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()
        self._session.auth = (config.username, config.password)
        self._session.verify = config.ssl_verify
        self._session.timeout = (config.connect_timeout, config.read_timeout)
        self._base = config.url.rstrip("/")
        self._chunk_size = config.chunk_size

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    def exists(self, path: str) -> bool:
        r = self._session.request("PROPFIND", self._url(path), headers={"Depth": "0"})
        return r.status_code == 207

    def stat(self, path: str) -> FileInfo | None:
        r = self._session.request("PROPFIND", self._url(path), headers={"Depth": "0"})
        if r.status_code != 207:
            return None
        # 解析 PROPFIND 响应 ...
        return FileInfo(path=path, size=0, mtime=0, is_dir=False)

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        # PROPFIND Depth=1 解析 ...
        yield from []

    def read_stream(self, path: str) -> BinaryIO:
        r = self._session.get(self._url(path), stream=True)
        r.raise_for_status()
        return r.raw

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        self._session.put(self._url(path), data=stream).raise_for_status()

    def mkdir(self, path: str, parents: bool = True) -> None:
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            self._session.request("MKCOL", self._url(sub))

    def remove(self, path: str, recursive: bool = False) -> None:
        self._session.request("DELETE", self._url(path))

    def copy(self, src: str, dst: str) -> None:
        self._session.request(
            "COPY", self._url(src), headers={"Destination": self._url(dst), "Overwrite": "T"}
        )

    def move(self, src: str, dst: str) -> None:
        self._session.request(
            "MOVE", self._url(src), headers={"Destination": self._url(dst), "Overwrite": "T"}
        )
```

#### SMB `app/storage/backends/smb.py`

```python
import os
from typing import BinaryIO, Iterator

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend


class SMBStorageBackend(StorageBackend):
    """
    SMB 后端。挂载模式委托 LocalStorageBackend，协议模式使用 smbprotocol。
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._mount_point = getattr(config, "mount_point", "")
        if self._mount_point:
            self._delegate = LocalStorageBackend(
                StorageConfig(id=config.id, name=config.name, type=StorageType.LOCAL)
            )
        else:
            self._delegate = None
            from smbprotocol.connection import Connection
            self._conn = Connection(config.server, config.username, config.password, config.domain)

    def _path(self, path: str) -> str:
        if self._delegate:
            return os.path.join(self._mount_point, path.lstrip("/"))
        return path

    def exists(self, path: str) -> bool:
        if self._delegate:
            return self._delegate.exists(self._path(path))
        # smbprotocol 实现...
        return False

    def read_stream(self, path: str) -> BinaryIO:
        if self._delegate:
            return self._delegate.read_stream(self._path(path))
        raise NotImplementedError

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        if self._delegate:
            return self._delegate.write_stream(self._path(path), stream, size)
        raise NotImplementedError

    def copy(self, src: str, dst: str) -> None:
        if self._delegate:
            return self._delegate.copy(self._path(src), self._path(dst))
        raise NotImplementedError

    def move(self, src: str, dst: str) -> None:
        if self._delegate:
            return self._delegate.move(self._path(src), self._path(dst))
        raise NotImplementedError
```

#### S3 `app/storage/backends/s3.py`

```python
from typing import BinaryIO, Iterator

import boto3

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class S3StorageBackend(StorageBackend):
    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._bucket = getattr(config, "bucket", "data")
        self._client = boto3.client(
            "s3",
            endpoint_url=getattr(config, "endpoint", None) or None,
            aws_access_key_id=getattr(config, "access_key", "") or None,
            aws_secret_access_key=getattr(config, "secret_key", "") or None,
            region_name=getattr(config, "region", "us-east-1") or None,
            use_ssl=getattr(config, "secure", True),
        )

    def _key(self, path: str) -> str:
        return path.lstrip("/")

    def exists(self, path: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(path))
            return True
        except Exception:
            return False

    def stat(self, path: str) -> FileInfo | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=self._key(path))
            return FileInfo(
                path=path,
                size=resp.get("ContentLength", 0),
                mtime=resp.get("LastModified", 0).timestamp() if resp.get("LastModified") else 0,
                is_dir=False,
            )
        except Exception:
            return None

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        prefix = self._key(path)
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
            for obj in page.get("Contents", []):
                if obj["Key"] == prefix:
                    continue
                yield FileInfo(
                    path="/" + obj["Key"],
                    size=obj.get("Size", 0),
                    mtime=obj.get("LastModified", 0).timestamp() if obj.get("LastModified") else 0,
                    is_dir=False,
                )
            for cp in page.get("CommonPrefixes", []):
                if cp["Prefix"] == prefix:
                    continue
                yield FileInfo(
                    path="/" + cp["Prefix"].rstrip("/"),
                    size=0,
                    mtime=0,
                    is_dir=True,
                )

    def read_stream(self, path: str) -> BinaryIO:
        resp = self._client.get_object(Bucket=self._bucket, Key=self._key(path))
        return resp["Body"]

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        self._client.upload_fileobj(stream, self._bucket, self._key(path))

    def mkdir(self, path: str, parents: bool = True) -> None:
        pass

    def remove(self, path: str, recursive: bool = False) -> None:
        key = self._key(path)
        if recursive:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=key):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
        else:
            self._client.delete_object(Bucket=self._bucket, Key=key)

    def copy(self, src: str, dst: str) -> None:
        self._client.copy_object(
            Bucket=self._bucket,
            Key=self._key(dst),
            CopySource={"Bucket": self._bucket, "Key": self._key(src)},
        )

    def move(self, src: str, dst: str) -> None:
        self.copy(src, dst)
        self.remove(src)
```

#### Rclone `app/storage/backends/rclone.py`

```python
import os
from typing import BinaryIO, Iterator

import requests

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class RcloneStorageBackend(StorageBackend):
    """
    Rclone 后端。使用 rclone rc HTTP API，要求 rclone 已以 daemon 模式运行。
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._rc_url = (getattr(config, "rc_url", "") or "http://localhost:5572").rstrip("/")
        self._remote = getattr(config, "remote_name", "NEXUS_MEDIA")
        self._session = requests.Session()
        username = getattr(config, "rc_user", "")
        password = getattr(config, "rc_pass", "")
        if username:
            self._session.auth = (username, password)

    def _call(self, endpoint: str, payload: dict) -> dict:
        resp = self._session.post(f"{self._rc_url}/{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def exists(self, path: str) -> bool:
        try:
            result = self._call("operations/stat", {"fs": self._remote, "remote": path.lstrip("/")})
            return result.get("item") is not None
        except Exception:
            return False

    def stat(self, path: str) -> FileInfo | None:
        try:
            result = self._call("operations/stat", {"fs": self._remote, "remote": path.lstrip("/")})
            item = result.get("item")
            if not item:
                return None
            return FileInfo(
                path=path,
                size=item.get("Size", 0),
                mtime=item.get("ModTime", 0),
                is_dir=item.get("IsDir", False),
            )
        except Exception:
            return None

    def list_dir(self, path: str) -> Iterator[FileInfo]:
        result = self._call(
            "operations/list",
            {"fs": self._remote, "remote": path.lstrip("/"), "opt": {"recurse": False}},
        )
        for item in result.get("list", []):
            yield FileInfo(
                path=os.path.join(path, item.get("Name", "")),
                size=item.get("Size", 0),
                mtime=item.get("ModTime", 0),
                is_dir=item.get("IsDir", False),
            )

    def read_stream(self, path: str) -> BinaryIO:
        raise NotImplementedError("Rclone 后端暂不支持流式读取")

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        raise NotImplementedError("Rclone 后端暂不支持流式写入")

    def mkdir(self, path: str, parents: bool = True) -> None:
        self._call("operations/mkdir", {"fs": self._remote, "remote": path.lstrip("/")})

    def remove(self, path: str, recursive: bool = False) -> None:
        if recursive:
            self._call("operations/purge", {"fs": self._remote, "remote": path.lstrip("/")})
        else:
            self._call("operations/deletefile", {"fs": self._remote, "remote": path.lstrip("/")})

    def copy(self, src: str, dst: str) -> None:
        self._call(
            "operations/copyfile",
            {
                "srcFs": self._remote,
                "srcRemote": src.lstrip("/"),
                "dstFs": self._remote,
                "dstRemote": dst.lstrip("/"),
            },
        )

    def move(self, src: str, dst: str) -> None:
        self._call(
            "operations/movefile",
            {
                "srcFs": self._remote,
                "srcRemote": src.lstrip("/"),
                "dstFs": self._remote,
                "dstRemote": dst.lstrip("/"),
            },
        )
```

---

## 4. 数据层

### 4.1 实体 `app/domain/entities/storage_backend.py`

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class StorageBackendEntity:
    id: str
    name: str
    type: str
    config: dict[str, Any]
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> "StorageBackendEntity | None":
        if orm_model is None:
            return None
        import json
        return cls(
            id=orm_model.ID or "",
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=json.loads(orm_model.CONFIG or "{}"),
            enabled=bool(orm_model.ENABLED),
        )
```

### 4.2 数据库模型 `app/db/models/storage_backend.py`

遵循项目风格：全大写类名、`Mapped[X] = mapped_column(...)`、`Sequence` 主键。

```python
"""
存储后端模型
包含: 存储后端配置
"""

from sqlalchemy import Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class STORAGEBACKEND(Base):
    __tablename__ = "STORAGE_BACKEND"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(50))
    CONFIG: Mapped[str] = mapped_column(Text)
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
```

### 4.3 修改现有模型 `app/db/models/sync.py`

```python
"""
同步配置模型
"""

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CONFIGSYNC(Base):
    __tablename__ = "CONFIG_SYNC_PATHS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SOURCE: Mapped[str] = mapped_column(String(512))
    DEST: Mapped[str] = mapped_column(String(512))
    UNKNOWN: Mapped[str] = mapped_column(String(512))
    MODE: Mapped[str] = mapped_column(String(50))           # 保留兼容
    OPERATION: Mapped[str] = mapped_column(String(50))      # 新字段
    SRC_BACKEND: Mapped[str] = mapped_column(String(64), default="local")
    DST_BACKEND: Mapped[str] = mapped_column(String(64), default="local")
    COMPATIBILITY: Mapped[int] = mapped_column(Integer, default=0)
    RENAME: Mapped[int] = mapped_column(Integer, default=1)
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
    NOTE: Mapped[str | None] = mapped_column(String(512), nullable=True)
```

### 4.4 仓储接口 `app/domain/interfaces/storage_backend_repo.py`

```python
from typing import Protocol

from app.domain.entities.storage_backend import StorageBackendEntity


class IStorageBackendRepository(Protocol):
    def get_all(self) -> list[StorageBackendEntity]: ...

    def get_by_id(self, sid: str) -> StorageBackendEntity | None: ...

    def insert(self, name: str, type: str, config: str) -> int: ...

    def update(self, sid: int, **kwargs) -> None: ...

    def delete(self, sid: int) -> None: ...
```

### 4.5 仓储实现 `app/db/repositories/storage_backend_repository.py`

```python
"""
存储后端仓储
"""

from app.db import DbPersist
from app.db.models import STORAGEBACKEND
from app.db.repositories.base_repository import BaseRepository


class StorageBackendRepository(BaseRepository):
    def get_all(self):
        return self._db.query(STORAGEBACKEND).all()

    def get_by_id(self, sid):
        return self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).first()

    @DbPersist(BaseRepository._db)
    def insert(self, name, type, config):
        self._db.insert(STORAGEBACKEND(NAME=name, TYPE=type, CONFIG=config))

    @DbPersist(BaseRepository._db)
    def update(self, sid, **kwargs):
        self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).update(kwargs)

    @DbPersist(BaseRepository._db)
    def delete(self, sid):
        self._db.query(STORAGEBACKEND).filter(STORAGEBACKEND.ID == sid).delete()
```

### 4.6 适配器 `app/db/repositories/storage_backend_repo_adapter.py`

```python
"""
存储后端仓储适配器
"""

from app.db.repositories.storage_backend_repository import StorageBackendRepository
from app.domain.entities.storage_backend import StorageBackendEntity
from app.domain.interfaces.storage_backend_repo import IStorageBackendRepository


class StorageBackendRepositoryAdapter(IStorageBackendRepository):
    def __init__(self, repo=None):
        self._repo = repo or StorageBackendRepository()

    def get_all(self) -> list[StorageBackendEntity]:
        rows = self._repo.get_all()
        return [e for e in [StorageBackendEntity.from_orm(r) for r in rows] if e is not None]

    def get_by_id(self, sid: str) -> StorageBackendEntity | None:
        row = self._repo.get_by_id(sid)
        return StorageBackendEntity.from_orm(row)

    def insert(self, name: str, type: str, config: str) -> int:
        return self._repo.insert(name, type, config)

    def update(self, sid: int, **kwargs) -> None:
        self._repo.update(sid, **kwargs)

    def delete(self, sid: int) -> None:
        self._repo.delete(sid)
```

---

## 5. 应用层

### 5.1 TransferEngine（替换 TransferActionEngine）

```python
"""文件转移引擎——唯一文件操作入口。"""

import os
import re
from threading import Lock

import log
from app.core.constants import RMT_AUDIO_TRACK_EXT, RMT_SUBEXT
from app.db.repositories.transfer_repo_adapter import TransferBlacklistRepositoryAdapter
from app.media import meta_info
from app.storage import LocalStorageBackend, StorageConfig, StorageBackendFactory, cross_copy, cross_move
from app.storage.backends.base import StorageBackend, StorageType
from app.utils import PathUtils

_lock = Lock()


class TransferEngine:
    """
    文件转移引擎。
    所有文件操作通过 StorageBackend 完成，不再区分本地/远程。
    operation 为字符串："copy" / "move" / "link" / "softlink"
    """

    def __init__(self):
        self._local = LocalStorageBackend(
            StorageConfig(id="local", name="local", type=StorageType.LOCAL)
        )
        self._blacklist = TransferBlacklistRepositoryAdapter()

    def _execute(self, src: str, dst: str, operation: str, dst_backend: StorageBackend | None = None) -> None:
        backend = dst_backend or self._local
        with _lock:
            if backend is not self._local:
                if operation == "copy":
                    cross_copy(self._local, src, backend, dst)
                elif operation == "move":
                    cross_move(self._local, src, backend, dst)
                else:
                    raise ValueError(f"远程后端不支持 {operation}")
                return
            if operation == "copy":
                self._local.copy(src, dst)
            elif operation == "move":
                self._local.move(src, dst)
            elif operation == "link":
                self._local.hardlink(src, dst)
            elif operation == "softlink":
                self._local.softlink(src, dst)
            else:
                raise ValueError(f"不支持的操作: {operation}")

    def transfer_subtitles(self, org_name: str, new_name: str, operation: str) -> None:
        _zhcn_sub_re = (
            r"([.\[(](((zh[-_])?(cn|ch[si]|sg|sc))|zho?"
            r"|chinese|(cn|ch[si]|sg|zho?|eng)[-_&](cn|ch[si]|sg|zho?|eng)"
            r"|简[体中]?|JPSC)[.\])])"
            r"|([\u4e00-\u9fa5]{0,3}[中双][\u4e00-\u9fa5]{0,2}[字文语][\u4e00-\u9fa5]{0,3})"
            r"|简体|简中"
            r"|(?<![a-z0-9])gb(?![a-z0-9])"
        )
        _zhtw_sub_re = (
            r"([.\[(](((zh[-_])?(hk|tw|cht|tc))"
            r"|繁[体中]?|JPTC)[.\])])"
            r"|繁体中[文字]|中[文字]繁体|繁体"
            r"|(?<![a-z0-9])big5(?![a-z0-9])"
        )
        _eng_sub_re = r"[.\[(]eng[.\])]"

        dir_name = os.path.dirname(org_name)
        file_name = os.path.basename(org_name)
        file_list = PathUtils.get_dir_level1_files(dir_name, RMT_SUBEXT)
        if not file_list:
            return

        metainfo = meta_info(title=file_name)
        for file_item in file_list:
            sub_file_name = re.sub(
                _zhtw_sub_re, ".", re.sub(_zhcn_sub_re, ".", os.path.basename(file_item), flags=re.I), flags=re.I
            )
            sub_file_name = re.sub(_eng_sub_re, ".", sub_file_name, flags=re.I)
            sub_metainfo = meta_info(title=os.path.basename(file_item))
            if not self._subtitle_match(file_name, sub_file_name, metainfo, sub_metainfo):
                continue

            new_file_type = self._detect_subtitle_type(file_item, _zhcn_sub_re, _zhtw_sub_re, _eng_sub_re)
            file_ext = os.path.splitext(file_item)[-1]
            for tag in [new_file_type] + [f"{new_file_type}.{t}" for t in range(1, 6)]:
                new_file = os.path.splitext(new_name)[0] + tag + file_ext
                if os.path.exists(new_file) and os.path.getsize(new_file) == os.path.getsize(file_item):
                    log.info(f"【Rmt】字幕 {new_file} 已存在")
                    break
                try:
                    log.debug(f"【Rmt】正在处理字幕：{os.path.basename(file_item)}")
                    self._execute(file_item, new_file, operation)
                    log.info(f"【Rmt】字幕 {os.path.basename(file_item)} {operation}完成")
                    break
                except Exception as e:
                    log.error(f"【Rmt】字幕 {file_name} {operation}失败：{e}")
                    raise

    def transfer_audio_tracks(self, org_name: str, new_name: str, operation: str, over_flag: bool) -> None:
        dir_name = os.path.dirname(org_name)
        file_pre = os.path.splitext(os.path.basename(org_name))[0]
        for track_file in PathUtils.get_dir_level1_files(dir_name, RMT_AUDIO_TRACK_EXT):
            if os.path.splitext(os.path.basename(track_file))[0] != file_pre:
                continue
            new_track = os.path.splitext(new_name)[0] + os.path.splitext(track_file)[1].lower()
            if os.path.exists(new_track):
                if not over_flag:
                    log.warn(f"【Rmt】音轨文件已存在：{new_track}")
                    continue
                os.remove(new_track)
            log.info(f"【Rmt】正在转移音轨文件：{track_file} 到 {new_track}")
            self._execute(track_file, new_track, operation)
            log.info(f"【Rmt】音轨文件 {os.path.basename(track_file)} {operation}完成")

    def transfer_dir(self, src_dir: str, target_dir: str, operation: str, record_blacklist: bool = True) -> None:
        for file in PathUtils.get_dir_files(src_dir):
            new_file = file.replace(src_dir, target_dir)
            if os.path.exists(new_file):
                log.warn(f"【Rmt】{new_file} 文件已存在")
                continue
            os.makedirs(os.path.dirname(new_file), exist_ok=True)
            self._execute(file, new_file, operation)
            if record_blacklist:
                self._blacklist.insert(file)

    def transfer_bluray_dir(self, src_dir: str, target_dir: str, operation: str) -> None:
        self.transfer_dir(src_dir, target_dir, operation, record_blacklist=False)
        self._blacklist.insert(src_dir)

    def transfer(
        self,
        src: str,
        dst: str,
        operation: str,
        over_flag: bool = False,
        old_file: str | None = None,
        dst_backend: StorageBackend | None = None,
    ) -> None:
        if not over_flag and os.path.exists(dst):
            log.warn(f"【Rmt】文件已存在：{dst}")
            return
        if over_flag and old_file and os.path.isfile(old_file):
            os.remove(old_file)

        log.info(f"【Rmt】正在转移文件：{os.path.basename(src)} 到 {dst}")
        self._execute(src, dst, operation, dst_backend)
        log.info(f"【Rmt】文件 {os.path.basename(src)} {operation}完成")
        self._blacklist.insert(src)

        self.transfer_subtitles(src, dst, operation)
        self.transfer_audio_tracks(src, dst, operation, over_flag)

    @staticmethod
    def delete_media_file(filedir: str, filename: str) -> tuple[bool, str]:
        try:
            file = os.path.join(filedir, filename)
            if not os.path.exists(file):
                return False, "文件不存在"
            os.remove(file)
            if not os.listdir(filedir):
                os.rmdir(filedir)
            return True, "删除成功"
        except Exception as e:
            log.error(f"【Rmt】删除文件失败: {e}")
            return False, str(e)

    @staticmethod
    def _subtitle_match(file_name: str, sub_name: str, meta, sub_meta) -> bool:
        if os.path.splitext(file_name)[0] == os.path.splitext(sub_name)[0]:
            return True
        if sub_meta.cn_name and sub_meta.cn_name == meta.cn_name:
            return True
        if sub_meta.en_name and sub_meta.en_name == meta.en_name:
            return True
        if meta.get_season_string() and meta.get_season_string() != sub_meta.get_season_string():
            return False
        if meta.get_episode_string() and meta.get_episode_string() != sub_meta.get_episode_string():
            return False
        return True

    @staticmethod
    def _detect_subtitle_type(file_item: str, zhcn_re, zhtw_re, eng_re) -> str:
        if re.search(zhcn_re, file_item, re.I):
            return ".chi.zh-cn"
        if re.search(zhtw_re, file_item, re.I):
            return ".zh-tw"
        if re.search(eng_re, file_item, re.I):
            return ".eng"
        return ".und"
```

### 5.2 SyncEngine（替换 SyncCore）

```python
"""目录同步引擎。"""

import os
import threading
import traceback
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

import log
from app.core.constants import RMT_MEDIAEXT
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import TransferHistoryRepositoryAdapter
from app.services.transfer_engine import TransferEngine
from app.storage import StorageBackendFactory
from app.storage.backends.base import StorageType
from app.storage.config_models import StorageConfig
from app.utils import PathUtils

_synced_lock = threading.Lock()
_pending_lock = threading.Lock()
_observer_lock = threading.Lock()


class FileMonitorHandler(FileSystemEventHandler):
    def __init__(self, monpath: str, engine: "SyncEngine"):
        super().__init__()
        self._watch_path = monpath
        self._engine = engine

    def on_created(self, event):
        self._engine.on_file_event(event.src_path)

    def on_moved(self, event):
        self._engine.on_file_event(event.dest_path)


class SyncPathConfig:
    def __init__(self, row: Any):
        self.id = str(row.ID)
        self.source = row.SOURCE or ""
        self.dest = row.DEST or ""
        self.unknown = row.UNKNOWN or ""
        self.operation = row.OPERATION or "copy"
        self.src_backend_id = row.SRC_BACKEND or "local"
        self.dst_backend_id = row.DST_BACKEND or "local"
        self.rename = bool(row.RENAME)
        self.compatibility = bool(row.COMPATIBILITY)
        self.enabled = bool(row.ENABLED)


class SyncEngine:
    def __init__(self):
        self._transfer = TransferEngine()
        self._sync_repo = SyncPathRepositoryAdapter()
        self._history_repo = TransferHistoryRepositoryAdapter()
        self._backend_repo = StorageBackendRepositoryAdapter()
        self._factory = StorageBackendFactory()
        self._configs: dict[str, SyncPathConfig] = {}
        self._monitor_ids: list[str] = []
        self._observers: list[Observer] = []
        self._synced_files: list[str] = []
        self._pending: dict[str, dict] = {}
        self._reload()

    def init(self) -> None:
        self._reload()
        self._start()

    def _resolve_backend(self, backend_id: str):
        if backend_id == "local":
            from app.storage.backends.local import LocalStorageBackend
            return LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        entity = self._backend_repo.get_by_id(backend_id)
        if not entity:
            raise ValueError(f"未找到存储后端: {backend_id}")
        config = self._build_storage_config(entity)
        return self._factory.create(config)

    def _build_storage_config(self, entity):
        from app.storage.config_models import (
            LocalStorageConfig, WebDAVStorageConfig, SMBStorageConfig,
            S3StorageConfig, RcloneStorageConfig, OpenListStorageConfig,
        )
        from app.storage.backends.base import StorageType
        mapping = {
            "local": (StorageType.LOCAL, LocalStorageConfig),
            "webdav": (StorageType.WEBDAV, WebDAVStorageConfig),
            "smb": (StorageType.SMB, SMBStorageConfig),
            "s3": (StorageType.S3, S3StorageConfig),
            "rclone": (StorageType.RCLONE, RcloneStorageConfig),
            "openlist": (StorageType.OPENLIST, OpenListStorageConfig),
        }
        stype, cls = mapping.get(entity.type, (StorageType.LOCAL, LocalStorageConfig))
        config = cls(id=entity.id, name=entity.name, type=stype, enabled=entity.enabled)
        for k, v in entity.config.items():
            if hasattr(config, k):
                setattr(config, k, v)
        return config

    def _reload(self) -> None:
        self._configs = {}
        self._monitor_ids = []
        for row in self._sync_repo.get_config_sync_paths():
            if not row:
                continue
            cfg = SyncPathConfig(row)
            log.info(
                f"【Sync】监控目录：{cfg.source} -> {cfg.dest} "
                f"(操作={cfg.operation}, 目标后端={cfg.dst_backend_id})"
            )
            if not cfg.enabled:
                log.info(f"【Sync】{cfg.source} 已关闭")
                continue
            self._configs[cfg.id] = cfg
            if os.path.exists(cfg.source):
                self._monitor_ids.append(cfg.id)
            else:
                log.error(f"【Sync】{cfg.source} 目录不存在")

    @property
    def monitor_ids(self) -> list[str]:
        return self._monitor_ids

    def get_config(self, sid: str | None = None):
        if sid:
            return self._configs.get(sid)
        return self._configs

    def _start(self) -> None:
        self.stop()
        for sid in self._monitor_ids:
            cfg = self.get_config(sid)
            if not cfg:
                continue
            obs = PollingObserver(timeout=10) if cfg.compatibility else Observer(timeout=10)
            with _observer_lock:
                self._observers.append(obs)
            obs.schedule(FileMonitorHandler(cfg.source, self), path=cfg.source, recursive=True)
            obs.daemon = True
            obs.start()
            log.info(f"【Sync】{cfg.source} 监控已启动")

    def stop(self) -> None:
        with _observer_lock:
            for obs in self._observers:
                try:
                    obs.stop()
                    obs.join()
                except Exception as e:
                    log.error(f"【Sync】停止监控异常: {e}")
            self._observers = []

    def on_file_event(self, event_path: str) -> None:
        if not os.path.exists(event_path):
            return
        with _synced_lock:
            if event_path in self._synced_files:
                return
            self._synced_files.append(event_path)

        try:
            cfg = self._find_config(event_path)
            if not cfg:
                return
            if PathUtils.is_invalid_path(event_path):
                return

            if not cfg.rename:
                self._do_link(event_path, cfg)
            else:
                self._do_transfer(event_path, cfg)
        except Exception as e:
            log.error(f"【Sync】处理失败：{e}\n{traceback.format_exc()}")

    def _find_config(self, event_path: str):
        for sid in self._monitor_ids:
            cfg = self.get_config(sid)
            if not cfg:
                continue
            if PathUtils.is_path_in_path(cfg.source, event_path):
                if PathUtils.is_path_in_path(cfg.dest, event_path):
                    log.error(f"【Sync】嵌套目录：{event_path}")
                    return None
                return cfg
        return None

    def _do_link(self, event_path: str, cfg: SyncPathConfig) -> None:
        if self._history_repo.is_sync_in_history(event_path, cfg.dest):
            return
        rel = os.path.relpath(event_path, cfg.source)
        dst = os.path.join(cfg.dest, rel)
        try:
            self._transfer._execute(event_path, dst, cfg.operation)
            self._history_repo.insert_sync_history(event_path, cfg.source, cfg.dest)
            log.info(f"【Sync】{event_path} 同步完成")
        except Exception as e:
            log.error(f"【Sync】{event_path} 同步失败：{e}")

    def _do_transfer(self, event_path: str, cfg: SyncPathConfig) -> None:
        name = os.path.basename(event_path)
        if name.lower() != "index.bdmv":
            ext = os.path.splitext(name)[-1].lower()
            if ext not in RMT_MEDIAEXT:
                return
        dst_backend = self._resolve_backend(cfg.dst_backend_id)
        self._transfer.transfer(
            src=event_path,
            dst=os.path.join(cfg.dest, name),
            operation=cfg.operation,
            dst_backend=dst_backend if cfg.dst_backend_id != "local" else None,
        )

    def run_sync(self, sid: str | list[str] | None = None) -> None:
        sids = sid if isinstance(sid, list) else [sid] if sid else self._monitor_ids
        for sid in sids:
            cfg = self.get_config(sid)
            if not cfg:
                continue
            if not cfg.rename:
                for f in PathUtils.get_dir_files(cfg.source):
                    self._do_link(f, cfg)
            else:
                for p in PathUtils.get_dir_level1_medias(cfg.source, RMT_MEDIAEXT):
                    if PathUtils.is_invalid_path(p):
                        continue
                    self._do_transfer(p, cfg)

    def delete_path(self, sid: int) -> Any:
        ret = self._sync_repo.delete_config_sync_path(sid=sid)
        self.init()
        return ret

    def insert_path(self, **kwargs) -> Any:
        ret = self._sync_repo.insert_config_sync_path(**kwargs)
        self.init()
        return ret

    def update_path(self, **kwargs) -> Any:
        ret = self._sync_repo.check_config_sync_paths(**kwargs)
        self.init()
        return ret
```

---

## 6. Alembic 迁移

### 6.1 创建迁移

```bash
uv run alembic revision -m "add_storage_backend_and_sync_fields"
```

### 6.2 迁移脚本

```python
"""add_storage_backend_and_sync_fields

Revision ID: xxx
Revises: yyy
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "xxx"
down_revision = "yyy"


def upgrade():
    # 创建 STORAGE_BACKEND 表
    op.create_table(
        "STORAGE_BACKEND",
        sa.Column("ID", sa.Integer(), sa.Sequence("ID"), nullable=False),
        sa.Column("NAME", sa.String(255), nullable=False),
        sa.Column("TYPE", sa.String(50), nullable=False),
        sa.Column("CONFIG", sa.Text(), nullable=False),
        sa.Column("ENABLED", sa.Integer(), server_default="1"),
        sa.PrimaryKeyConstraint("ID"),
    )

    # 修改 CONFIG_SYNC_PATHS 表
    op.add_column("CONFIG_SYNC_PATHS", sa.Column("OPERATION", sa.String(50), nullable=True))
    op.add_column("CONFIG_SYNC_PATHS", sa.Column("SRC_BACKEND", sa.String(64), server_default="local"))
    op.add_column("CONFIG_SYNC_PATHS", sa.Column("DST_BACKEND", sa.String(64), server_default="local"))

    # 数据迁移：MODE 映射到 OPERATION
    op.execute("""
        UPDATE CONFIG_SYNC_PATHS SET OPERATION = CASE
            WHEN MODE IN ('copy', 'rclonecopy', 'miniocopy') THEN 'copy'
            WHEN MODE IN ('move', 'rclone', 'minio') THEN 'move'
            WHEN MODE = 'link' THEN 'link'
            WHEN MODE = 'softlink' THEN 'softlink'
            ELSE 'copy'
        END
    """)


def downgrade():
    op.drop_column("CONFIG_SYNC_PATHS", "OPERATION")
    op.drop_column("CONFIG_SYNC_PATHS", "SRC_BACKEND")
    op.drop_column("CONFIG_SYNC_PATHS", "DST_BACKEND")
    op.drop_table("STORAGE_BACKEND")
```

---

## 7. 文件目录结构

```
app/
├── storage/
│   ├── __init__.py
│   ├── factory.py
│   ├── cross_backend.py
│   ├── config_models.py
│   └── backends/
│       ├── __init__.py
│       ├── base.py
│       ├── local.py
│       ├── webdav.py
│       ├── smb.py
│       ├── s3.py
│       ├── rclone.py
│       └── openlist.py
├── services/
│   ├── transfer_engine.py      # 替换 transfer_action_engine.py
│   └── sync_engine.py          # 替换 sync_core.py
├── domain/
│   ├── entities/
│   │   └── storage_backend.py
│   └── interfaces/
│       └── storage_backend_repo.py
├── db/
│   ├── models/
│   │   └── storage_backend.py
│   └── repositories/
│       ├── storage_backend_repository.py
│       └── storage_backend_repo_adapter.py
```

---

## 8. 废弃清单

重构完成后删除：
1. `app/services/transfer_action_engine.py`
2. `app/services/sync_core.py`
3. `app/utils/types.py` 中的 `RmtMode` 枚举
4. `app/core/module_config.py` 中的 `RMT_MODES` / `RMT_MODES_LITE` / `REMOTE_RMT_MODES`
5. `SystemUtils` 中的 `copy/move/link/softlink/rclone_move/rclone_copy/minio_move/minio_copy`
