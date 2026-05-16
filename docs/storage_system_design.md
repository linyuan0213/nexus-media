# 多存储后端文件同步系统设计文档

## 背景

当前 NAS-Tools 的目录同步功能仅支持本地文件系统操作（硬链接/软链接/复制/移动）以及基于外部命令的 Rclone/MinIO 同步。随着用户需要将媒体文件同步到远程存储（WebDAV、SMB、OpenList 等）的需求增长，需要设计一套统一的存储抽象层，使文件转移逻辑与底层存储实现解耦。

## 目标

1. **统一存储抽象**：定义 `StorageBackend` 接口，屏蔽本地与远程存储差异
2. **向后兼容**：现有 `RmtMode` 和 `TransferActionEngine` 继续工作
3. **即插即用**：新增存储类型无需修改业务代码
4. **支持的场景**：
   - WebDAV（AList、坚果云、NextCloud 等）
   - SMB/CIFS（群晖、Windows 共享）
   - OpenList（媒体服务器文件列表）
   - 本地文件系统（已有功能）
   - Rclone/MinIO（已有功能，逐步迁移到新架构）

---

## 架构设计

### 1. 核心接口层 `app/storage/backends/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, BinaryIO, Iterator


class StorageType(Enum):
    LOCAL = "local"
    WEBDAV = "webdav"
    SMB = "smb"
    OPENLIST = "openlist"
    RCLONE = "rclone"
    S3 = "s3"


@dataclass(frozen=True)
class FileInfo:
    """文件元信息"""
    path: str
    size: int
    mtime: float
    is_dir: bool
    mime_type: str = ""


@dataclass
class StorageConfig:
    """存储后端配置基类"""
    name: str
    type: StorageType
    enabled: bool = True


class StorageBackend(ABC):
    """
    存储后端抽象基类。

    所有存储实现必须提供：
    - 路径存在性检查
    - 文件/目录读写
    - 文件转移（复制/移动，支持同后端和跨后端）
    - 流式读写（大文件场景）
    """

    def __init__(self, config: StorageConfig) -> None:
        self.config = config

    # ---------- 元信息 ----------

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查路径是否存在"""

    @abstractmethod
    def stat(self, path: str) -> FileInfo | None:
        """获取文件元信息"""

    @abstractmethod
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        """列出目录内容"""

    # ---------- 读写 ----------

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """读取完整文件（小文件场景）"""

    @abstractmethod
    def read_stream(self, path: str) -> BinaryIO:
        """获取文件读取流（大文件场景）"""

    @abstractmethod
    def write_file(self, path: str, data: bytes) -> None:
        """写入完整文件"""

    @abstractmethod
    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        """从流写入文件"""

    # ---------- 目录 ----------

    @abstractmethod
    def mkdir(self, path: str, parents: bool = True) -> None:
        """创建目录"""

    @abstractmethod
    def remove(self, path: str, recursive: bool = False) -> None:
        """删除文件或目录"""

    # ---------- 同后端转移 ----------

    @abstractmethod
    def copy(self, src: str, dst: str) -> None:
        """同存储后端内复制"""

    @abstractmethod
    def move(self, src: str, dst: str) -> None:
        """同存储后端内移动"""

    # ---------- 跨后端支持 ----------

    def supports_streaming_upload(self) -> bool:
        """是否支持流式上传（用于跨后端复制大文件）"""
        return True

    def supports_streaming_download(self) -> bool:
        """是否支持流式下载"""
        return True
```

### 2. 存储工厂 `app/storage/factory.py`

```python
from typing import ClassVar

from app.storage.backends.base import StorageBackend, StorageConfig, StorageType


class StorageBackendFactory:
    """存储后端工厂——注册表模式"""

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
    def list_supported_types(cls) -> list[StorageType]:
        return list(cls._registry.keys())
```

### 3. 配置模型 `app/storage/config_models.py`

```python
from dataclasses import dataclass, field

from app.storage.backends.base import StorageConfig, StorageType


@dataclass
class LocalStorageConfig(StorageConfig):
    type: StorageType = StorageType.LOCAL
    # 本地存储无额外配置


@dataclass
class WebDAVStorageConfig(StorageConfig):
    type: StorageType = StorageType.WEBDAV
    url: str = ""
    username: str = ""
    password: str = ""
    # 是否使用 https
    ssl_verify: bool = True
    # 超时（秒）
    timeout: int = 30
    # 分块上传大小（字节）
    chunk_size: int = 8 * 1024 * 1024


@dataclass
class SMBStorageConfig(StorageConfig):
    type: StorageType = StorageType.SMB
    server: str = ""          # IP 或域名
    share: str = ""           # 共享名
    port: int = 445
    username: str = ""
    password: str = ""
    domain: str = ""
    # 本地挂载路径（如使用 mount.cifs）
    mount_point: str = ""


@dataclass
class OpenListStorageConfig(StorageConfig):
    type: StorageType = StorageType.OPENLIST
    base_url: str = ""
    api_token: str = ""
    timeout: int = 30
    # OpenList 通常是只读或半只读，需标记支持的写操作
    write_enabled: bool = False
```

### 4. 本地实现 `app/storage/backends/local.py`

复用现有 `SystemUtils`/`PathUtils`，完全兼容当前行为：

```python
import os
import shutil
from typing import BinaryIO, Iterator

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig
from app.utils import PathUtils


class LocalStorageBackend(StorageBackend):
    """本地文件系统存储后端"""

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

    def read_file(self, path: str) -> bytes:
        with open(self._resolve(path), "rb") as f:
            return f.read()

    def read_stream(self, path: str) -> BinaryIO:
        return open(self._resolve(path), "rb")

    def write_file(self, path: str, data: bytes) -> None:
        rp = self._resolve(path)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "wb") as f:
            f.write(data)

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
        from app.utils import SystemUtils
        ret, _ = SystemUtils.copy(self._resolve(src), self._resolve(dst))
        if ret != 0:
            raise OSError(f"复制失败: {src} -> {dst}")

    def move(self, src: str, dst: str) -> None:
        from app.utils import SystemUtils
        ret, _ = SystemUtils.move(self._resolve(src), self._resolve(dst))
        if ret != 0:
            raise OSError(f"移动失败: {src} -> {dst}")
```

### 5. WebDAV 实现 `app/storage/backends/webdav.py`

基于 `webdav4` 或 `requests` + `lxml` 实现：

```python
from io import BytesIO
from typing import BinaryIO, Iterator

import requests
from lxml import etree

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class WebDAVStorageBackend(StorageBackend):
    """WebDAV 存储后端"""

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()
        self._session.auth = (config.username, config.password)
        self._session.verify = config.ssl_verify
        self._session.timeout = config.timeout
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

    def read_stream(self, path: str) -> BinaryIO:
        r = self._session.get(self._url(path), stream=True)
        r.raise_for_status()
        return r.raw

    def write_stream(self, path: str, stream: BinaryIO, size: int = 0) -> None:
        # 大文件分块上传（PUT 覆盖）
        self._session.put(self._url(path), data=stream).raise_for_status()

    def mkdir(self, path: str, parents: bool = True) -> None:
        self._session.request("MKCOL", self._url(path))
        # parents=True 时递归创建父目录

    def copy(self, src: str, dst: str) -> None:
        self._session.request(
            "COPY", self._url(src), headers={"Destination": self._url(dst)}
        )

    def move(self, src: str, dst: str) -> None:
        self._session.request(
            "MOVE", self._url(src), headers={"Destination": self._url(dst)}
        )
```

### 6. SMB 实现 `app/storage/backends/smb.py`

基于 `smbprotocol`（纯 Python，无外部依赖）或挂载模式：

```python
from typing import BinaryIO, Iterator

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig


class SMBStorageBackend(StorageBackend):
    """
    SMB/CIFS 存储后端。

    实现方式二选一（按配置切换）：
    A. 直接协议模式 —— 使用 smbprotocol，无需 mount
    B. 挂载模式     —— 本地 mount.cifs 后，委托 LocalStorageBackend
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        if config.mount_point:
            # 挂载模式：复用本地后端
            self._delegate = LocalStorageBackend(
                StorageConfig(name=config.name, type=StorageType.LOCAL)
            )
            self._root = config.mount_point
        else:
            self._delegate = None
            self._root = f"//{config.server}/{config.share}"
            # 初始化 smbprotocol 连接池...

    def exists(self, path: str) -> bool:
        if self._delegate:
            return self._delegate.exists(os.path.join(self._root, path))
        # 直接 SMB 协议实现...
```

### 7. 跨后端复制引擎 `app/storage/cross_backend.py`

```python
import shutil
from typing import BinaryIO

from app.storage.backends.base import StorageBackend


def cross_backend_copy(
    src_backend: StorageBackend,
    src_path: str,
    dst_backend: StorageBackend,
    dst_path: str,
    chunk_size: int = 8 * 1024 * 1024,
) -> None:
    """
    跨存储后端复制文件。

    策略优先级：
    1. 如果两端都支持同协议直连（如两端都是 WebDAV），优先使用服务端 COPY
    2. 否则使用流式管道：src.read_stream -> dst.write_stream
    """
    # 优先检查是否可以使用服务端 COPY
    if src_backend.config.type == dst_backend.config.type:
        try:
            src_backend.copy(src_path, dst_path)
            return
        except Exception:
            pass

    # 流式复制（避免大文件内存溢出）
    stream: BinaryIO = src_backend.read_stream(src_path)
    try:
        dst_backend.write_stream(dst_path, stream)
    finally:
        stream.close()
```

---

## 与现有系统集成

### 集成点 1：`RmtMode` 扩展

在 `app/utils/types.py` 中新增存储类型枚举值：

```python
class RmtMode(Enum):
    LINK = "硬链接"
    SOFTLINK = "软链接"
    COPY = "复制"
    MOVE = "移动"
    RCLONECOPY = "Rclone复制"
    RCLONE = "Rclone移动"
    MINIOCOPY = "Minio复制"
    MINIO = "Minio移动"
    # 新增
    WEBDAV = "WebDAV"
    WEBDAV_COPY = "WebDAV复制"
    SMB = "SMB"
    SMB_COPY = "SMB复制"
    OPENLIST = "OpenList"
```

### 集成点 2：`TransferActionEngine` 重构

将现有的 `transfer_command` 方法重构为通过 `StorageBackend` 执行：

```python
class TransferActionEngine:
    def __init__(self, ...):
        self._storage_factory = StorageBackendFactory()
        self._local = LocalStorageBackend(StorageConfig(name="local", type=StorageType.LOCAL))

    def transfer(
        self,
        src_path: str,
        dst_path: str,
        rmt_mode: RmtMode,
        dst_backend: StorageBackend | None = None,
    ) -> int:
        """
        统一转移入口。

        - dst_backend 为 None → 本地转移（复用现有逻辑）
        - dst_backend 不为 None → 跨后端转移
        """
        if dst_backend is None:
            return self._local_transfer(src_path, dst_path, rmt_mode)

        # 远程存储转移
        try:
            if rmt_mode in (RmtMode.COPY, RmtMode.WEBDAV_COPY, RmtMode.SMB_COPY):
                cross_backend_copy(self._local, src_path, dst_backend, dst_path)
            elif rmt_mode in (RmtMode.MOVE, RmtMode.WEBDAV, RmtMode.SMB):
                cross_backend_copy(self._local, src_path, dst_backend, dst_path)
                self._local.remove(src_path)
            else:
                raise ValueError(f"不支持的远程转移模式: {rmt_mode}")
            return 0
        except Exception as e:
            log.error(f"【Storage】跨后端转移失败: {e}")
            return 1
```

### 集成点 3：`SyncCore` 扩展

同步配置表 `CONFIG_SYNC_PATHS` 新增字段 `DEST_BACKEND`（存储后端 ID）：

```python
class SyncCore:
    def _reload_config(self) -> None:
        for sync_conf in self._sync_repo.get_config_sync_paths():
            # ... 原有字段解析 ...
            backend_id = sync_conf.DEST_BACKEND  # 新增
            target_path = sync_conf.DEST

            # 加载目标存储后端
            backend = None
            if backend_id:
                backend = StorageBackendFactory.create(
                    self._load_backend_config(backend_id)
                )

            self._sync_path_confs[str(sid)] = {
                # ...
                "backend": backend,
            }
```

### 集成点 4：数据库模型扩展

```python
# app/db/models/sync.py 新增
class SYNC_STORAGE_BACKEND(Base):
    __tablename__ = "SYNC_STORAGE_BACKEND"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    TYPE: Mapped[str] = mapped_column(String(50))       # webdav/smb/openlist/...
    CONFIG: Mapped[str] = mapped_column(Text)            # JSON 序列化配置
    ENABLED: Mapped[int] = mapped_column(Integer, default=1)
```

---

## 文件目录结构

```
app/storage/
├── __init__.py
├── factory.py                 # StorageBackendFactory
├── cross_backend.py           # 跨后端复制引擎
├── config_models.py           # 配置数据类
├── backends/
│   ├── __init__.py
│   ├── base.py                # StorageBackend / FileInfo / StorageConfig
│   ├── local.py               # LocalStorageBackend
│   ├── webdav.py              # WebDAVStorageBackend
│   ├── smb.py                 # SMBStorageBackend
│   └── openlist.py            # OpenListStorageBackend（只读或代理模式）
```

---

## 使用示例

### 配置 WebDAV 后端并同步

```python
from app.storage.factory import StorageBackendFactory
from app.storage.config_models import WebDAVStorageConfig

# 1. 创建配置
config = WebDAVStorageConfig(
    name="alist-webdav",
    type=StorageType.WEBDAV,
    url="https://alist.example.com/dav/media",
    username="admin",
    password="***",
    ssl_verify=True,
)

# 2. 创建后端
backend = StorageBackendFactory.create(config)

# 3. 同步文件
from app.storage.cross_backend import cross_backend_copy
from app.storage.backends.local import LocalStorageBackend

local = LocalStorageBackend(StorageConfig(name="local", type=StorageType.LOCAL))
cross_backend_copy(
    local, "/downloads/movies/xxx.mkv",
    backend, "/movies/xxx.mkv",
)
```

### 在目录同步中使用

用户界面新增"目标存储"下拉框：
- 选择"本地" → 现有行为（`DEST` 为本地路径）
- 选择"WebDAV: alist-webdav" → `DEST_BACKEND` 指向对应后端，`DEST` 为 WebDAV 上的目标路径

---

## 风险与兼容性

| 风险 | 缓解措施 |
|------|----------|
| 大文件跨网络复制内存溢出 | 强制使用 `read_stream` + `write_stream` 分块传输（默认 8MB） |
| 网络抖动导致同步中断 | 增加重试机制（指数退避，最多 3 次） |
| SMB/WebDAV 服务端不支持部分操作 | 后端实现时降级处理（如不支持服务端 COPY，fallback 到流式传输） |
| 现有 RmtMode 行为变更 | 本地模式完全保留现有 `SystemUtils` 调用，新增模式独立实现 |
| 数据库迁移 | 新增 `SYNC_STORAGE_BACKEND` 表，`CONFIG_SYNC_PATHS` 新增可空字段 `DEST_BACKEND` |

---

## 实施阶段

1. **Phase 1**：定义 `StorageBackend` 接口 + `LocalStorageBackend` + 工厂（1-2 天）
2. **Phase 2**：接入 `TransferActionEngine`，将本地操作路由到 `LocalStorageBackend`（1 天）
3. **Phase 3**：实现 `WebDAVStorageBackend` + UI 配置页面（2-3 天）
4. **Phase 4**：实现 `SMBStorageBackend`（挂载模式优先，1-2 天）
5. **Phase 5**：实现 `OpenListStorageBackend`（只读扫描，1-2 天）
6. **Phase 6**：逐步将 Rclone/MinIO 迁移为新后端（可选）
