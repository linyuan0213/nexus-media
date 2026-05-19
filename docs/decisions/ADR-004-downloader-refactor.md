# ADR-004: 下载器模块重构设计

## Status
Proposed

## Date
2026-05-18

## Context
当前下载器模块支持 Qbittorrent、Transmission、Aria2、迅雷四种下载器，架构存在以下耦合问题：

1. **接口类型不安全**：`_IDownloadClient` 所有抽象方法返回 `Any`，调用方无法获得类型保证，IDE 也无法推断
2. **删种逻辑各写各的**：`get_remove_torrents(config: dict)` 在各实现中独立维护，但 `config` 里混入了 `qb_state`/`qb_category`（QB 专属）和 `tr_state`（TR 专属）等字段，新增下载器必须复制粘贴大量删种判断代码
3. **UI 配置硬编码**：`app/core/module_config.py` 的 `DOWNLOADER_CONF` 以字典形式写死了每种下载器的表单配置，新增下载器必须修改核心文件
4. **通用逻辑重复**：`get_transfer_task`、`get_downloading_progress` 在 QB 和 TR 中逻辑高度雷同，仅路径拼接和状态判断略有差异
5. **状态映射分散**：各下载器自行维护原始状态到 `TorrentStatus` 的映射，没有统一入口

新增 Rtorrent 下载器时，上述问题会进一步放大。

## Decision

对下载器模块进行渐进式重构，目标：**接口强类型、行为通用化、配置自包含**。

### 1. 目录结构调整

```
app/downloader/
├── __init__.py
├── interfaces.py              # 强类型接口定义（替代 _base.py 的抽象基类）
├── schema.py                  # 下载器配置表单 Schema（从 module_config.py 解耦）
├── strategy.py                # 删种策略通用数据结构
├── status.py                  # 通用状态与映射
├── registry.py                # 下载器注册表（装饰器 + 动态发现）
├── client_factory.py          # 简化后的工厂（仅负责实例创建与缓存）
└── client/
    ├── __init__.py            # 不再显式导入，由 registry 自动收集
    ├── _base.py               # 抽象基类，提供通用默认实现
    ├── qbittorrent.py         # 适配新接口
    ├── transmission.py        # 适配新接口
    └── rtorrent.py            # 新下载器
```

### 2. 强类型接口（`interfaces.py`）

使用 `typing.Protocol` 定义下载器契约，方法签名全部具体化：

```python
from typing import Protocol, runtime_checkable
from app.schemas.download import Torrent, TorrentStatus

@runtime_checkable
class IDownloadClient(Protocol):
    client_id: str
    client_type: DownloaderType
    client_name: str

    @classmethod
    def match(cls, ctype: str) -> bool: ...

    def get_type(self) -> DownloaderType: ...
    def connect(self) -> None: ...
    def get_status(self) -> bool: ...
    def get_torrents(
        self,
        ids: list[str] | str | None = None,
        status: list[TorrentStatus] | TorrentStatus | None = None,
        tag: str | list[str] | None = None,
    ) -> tuple[list[Torrent], bool]: ...
    def get_downloading_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None: ...
    def get_completed_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None: ...
    def get_files(self, tid: str | None = None) -> list[dict] | None: ...
    def set_torrents_status(self, ids: list[str] | str, tags: str | list[str] | None = None) -> bool: ...
    def set_torrents_tag(self, ids: list[str] | str | None = None, tags: str | list[str] | None = None) -> bool: ...
    def get_transfer_task(self, tag: str | None = None, match_path: bool | None = None) -> list[dict]: ...
    def get_remove_torrents(self, strategy: RemoveStrategy) -> list[dict]: ...
    def add_torrent(self, content: str | bytes, **kwargs) -> bool: ...
    def start_torrents(self, ids: list[str] | str | None = None) -> bool: ...
    def stop_torrents(self, ids: list[str] | str | None = None) -> bool: ...
    def delete_torrents(self, delete_file: bool = False, ids: list[str] | str | None = None) -> bool: ...
    def get_download_dirs(self) -> list[str]: ...
    def change_torrent(self, tid: str | None = None, **kwargs) -> bool: ...
    def get_downloading_progress(
        self, ids: list[str] | str | None = None, tag: str | None = None
    ) -> list[dict]: ...
    def set_speed_limit(self, download_limit: int | None = None, upload_limit: int | None = None) -> bool: ...
    def recheck_torrents(self, ids: list[str] | str | None = None) -> bool: ...
    def get_free_space(self, path: str) -> int | None: ...
```

> 注：保留 `Protocol` 而非纯 ABC，允许未来第三方插件通过鸭子类型实现，无需强制继承。基类 `_IDownloadClient` 同时实现该 `Protocol`，内部项目统一继承基类。

### 3. 配置 Schema 自包含（`schema.py`）

定义表单字段和下载器配置描述：

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigField:
    """单个配置表单字段"""
    id: str
    required: bool
    title: str
    type: str                           # text | password | select | switch
    tooltip: str = ""
    placeholder: str = ""
    default: Any = None
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class DownloaderConfigSchema:
    """下载器前端配置描述"""
    name: str                           # 显示名称
    img_url: str                        # 图标路径
    color: str                          # 主题色
    monitor_enable: bool = True         # 是否支持监控
    speedlimit_enable: bool = True      # 是否支持限速
    fields: list[ConfigField] = field(default_factory=list)
```

每个下载器类通过类属性暴露自己的 schema：

```python
class Qbittorrent(_IDownloadClient):
    client_id = "qbittorrent"
    client_type = DownloaderType.QB
    client_name = "Qbittorrent"

    config_schema = DownloaderConfigSchema(
        name="Qbittorrent",
        img_url="../static/img/downloader/qbittorrent.png",
        color="#3872C2",
        monitor_enable=True,
        speedlimit_enable=True,
        fields=[
            ConfigField(id="host", required=True, title="地址", type="text", placeholder="127.0.0.1"),
            ConfigField(id="port", required=True, title="端口", type="text", placeholder="8080"),
            ConfigField(id="username", required=True, title="用户名", type="text", placeholder="admin"),
            ConfigField(id="password", required=False, title="密码", type="password", placeholder="password"),
            ConfigField(
                id="torrent_management",
                required=False,
                title="种子管理模式",
                type="select",
                options={"default": "默认", "manual": "手动", "auto": "自动"},
                default="manual",
            ),
        ],
    )
```

`app/core/module_config.py` 的 `DOWNLOADER_CONF` 改为**运行时动态收集**：

```python
# module_config.py
from app.downloader.registry import get_all_clients

# 下载器配置由各下载器类自描述，此处动态聚合
DOWNLOADER_CONF = {
    cls.client_id: cls.config_schema.to_dict()
    for cls in get_all_clients()
}
```

新增下载器时**无需修改 `module_config.py`**。

### 4. 删种策略通用化（`strategy.py`）

将 `get_remove_torrents` 的 `config: dict` 替换为强类型数据结构：

```python
from dataclasses import dataclass, field
from app.schemas.download import TorrentStatus


@dataclass
class RemoveStrategy:
    """自动删种策略"""
    filter_tags: list[str] = field(default_factory=list)
    filter_status: list[TorrentStatus] = field(default_factory=list)
    ratio: float | None = None
    seeding_time: float | None = None          # 单位：小时
    size_range: tuple[int, int] | None = None  # 单位：bytes (min, max)
    upload_avs: float | None = None            # 单位：KB/s
    savepath_key: str | None = None
    tracker_key: str | None = None
    samedata: bool = False
```

基类 `_IDownloadClient` 提供 `get_remove_torrents` 的**默认实现**，各下载器无需重复：

```python
class _IDownloadClient:
    def get_remove_torrents(self, strategy: RemoveStrategy) -> list[dict]:
        torrents, error = self.get_torrents(
            status=strategy.filter_status, tag=strategy.filter_tags
        )
        if error:
            return []
        # 通用过滤逻辑...
        # 仅当下载器有特有筛选条件时才覆盖此方法
```

前端传入的配置字典由 `client_factory.py` 或调用层统一转换为 `RemoveStrategy`，下载器内部不再接触原始 dict。

### 5. 状态映射标准化（`status.py`）

定义通用状态枚举（保留现有 `TorrentStatus`），要求每个下载器实现状态映射：

```python
class _IDownloadClient:
    @abstractmethod
    def _map_status(self, raw_state: Any) -> TorrentStatus:
        """将下载器原始状态映射为通用 TorrentStatus"""

    @property
    @abstractmethod
    def _supported_statuses(self) -> list[TorrentStatus]:
        """该下载器支持的状态列表（用于删种 UI 筛选）"""
```

`TORRENTREMOVER_DICT` 也改为动态收集：

```python
# module_config.py
TORRENTREMOVER_DICT = {
    cls.client_id: {
        "name": cls.client_name,
        "img_url": cls.config_schema.img_url,
        "downloader_type": cls.client_type,
        "torrent_state": {s.name: s.value for s in cls._supported_statuses},
    }
    for cls in get_all_clients()
}
```

### 6. 通用行为下沉基类

以下方法逻辑在 QB 和 TR 中高度重复，抽到基类默认实现，下载器按需覆盖：

| 方法 | 基类默认实现 | 需覆盖点 |
|------|-------------|---------|
| `get_transfer_task` | 获取已完成种子 → 过滤标签/路径 → 返回转移任务 | `get_content_subpath(torrent)` 获取相对路径 |
| `get_downloading_progress` | 获取下载中种子 → 格式化速度/进度/状态 | `_format_speed(torrent)` 格式化显示字符串 |
| `get_remove_torrents` | 通用条件过滤（分享率、做种时间、大小等） | 特有筛选条件（如 QB 的分类） |
| `match` | `ctype in [cls.client_id, cls.client_type, cls.client_name]` | 极少需要覆盖 |
| `get_type` | `return self.client_type` | 无需覆盖 |

基类伪代码：

```python
class _IDownloadClient(metaclass=ABCMeta):
    @classmethod
    def match(cls, ctype: str) -> bool:
        return ctype in [cls.client_id, cls.client_type, cls.client_name]

    def get_type(self) -> DownloaderType:
        return self.client_type

    def get_transfer_task(self, tag=None, match_path=None) -> list[dict]:
        torrents = self.get_completed_torrents() or []
        tasks = []
        for t in torrents:
            if "已整理" in (t.labels or []):
                continue
            if tag and tag not in (t.labels or []):
                continue
            if not t.save_path:
                continue
            true_path, replaced = self.get_replace_path(t.save_path, self.download_dir)
            if match_path and not replaced:
                continue
            subpath = self._get_content_subpath(t) or t.name
            tasks.append({"path": os.path.join(true_path, subpath).replace("\\", "/"), "id": t.id})
        return tasks

    def _get_content_subpath(self, torrent: Torrent) -> str | None:
        """获取种子内容相对路径，子类可覆盖"""
        return None

    def get_downloading_progress(self, ids=None, tag=None) -> list[dict]:
        torrents = self.get_downloading_torrents(ids=ids, tag=tag) or []
        return [self._format_progress(t) for t in torrents]

    def _format_progress(self, torrent: Torrent) -> dict:
        progress = round(torrent.progress * 100, 1)
        if torrent.status in (TorrentStatus.Paused, TorrentStatus.Stopped):
            state, speed = "Stopped", "已暂停"
        else:
            state = "Downloading"
            speed = self._format_speed(torrent)
        return {"id": torrent.id, "name": torrent.name, "speed": speed, "state": state, "progress": progress}

    def _format_speed(self, torrent: Torrent) -> str:
        dl = StringUtils.str_filesize(torrent.download_speed)
        ul = StringUtils.str_filesize(torrent.upload_speed)
        if torrent.progress * 100 >= 100:
            return f"{chr(8595)}{dl}B/s {chr(8593)}{ul}B/s"
        eta = StringUtils.str_timelong(torrent.eta)
        return f"{chr(8595)}{dl}B/s {chr(8593)}{ul}B/s {eta}"
```

### 7. 注册表（`registry.py`）

用显式代码注册替代 `SubmoduleHelper.import_submodules` 的魔法导入：

```python
from typing import TypeVar

T = TypeVar("T", bound=type)
_registry: dict[str, type] = {}


def register(cls: T) -> T:
    """注册下载器类"""
    if not hasattr(cls, "client_id") or not cls.client_id:
        raise ValueError(f"下载器类 {cls.__name__} 必须定义 client_id")
    _registry[cls.client_id] = cls
    return cls


def get_client_class(client_id: str) -> type | None:
    return _registry.get(client_id)


def get_all_clients() -> list[type]:
    return list(_registry.values())
```

下载器类不自动注册，统一在 `app/downloader/client/__init__.py` 中显式注册：

```python
from app.downloader.registry import register
from .qbittorrent import Qbittorrent
from .transmission import Transmission
from .aria2 import Aria2
from .thunder import Thunder

register(Qbittorrent)
register(Transmission)
register(Aria2)
register(Thunder)
```

新增下载器时只需在 `__init__.py` 中加一行 `register(Xxx)`。

`client_factory.py` 的 `_build_class` 改为从注册表查找：

```python
def _build_class(self, ctype, conf=None):
    for cls in get_all_clients():
        if cls.match(ctype):
            return cls(conf)
    return None
```

> 不使用 `SubmoduleHelper` 兜底扫描。所有下载器必须显式在 `client/__init__.py` 中调用 `register()` 注册，注册逻辑集中、明确可控，避免魔法导入带来的隐式依赖。

### 8. 重构范围与步骤

| 步骤 | 文件 | 动作 |
|------|------|------|
| 1 | 新建 `app/downloader/interfaces.py` | 定义 `IDownloadClient` Protocol |
| 2 | 新建 `app/downloader/schema.py` | 定义 `ConfigField`、`DownloaderConfigSchema` |
| 3 | 新建 `app/downloader/strategy.py` | 定义 `RemoveStrategy` |
| 4 | 新建 `app/downloader/status.py` | 状态相关常量与辅助函数 |
| 5 | 新建 `app/downloader/registry.py` | 显式注册管理 |
| 6 | 重构 `app/downloader/client/_base.py` | 改为强类型 + 通用默认实现 |
| 7 | 适配 `app/downloader/client/qbittorrent.py` | 实现 `_map_status`、`_supported_statuses`、简化 `get_remove_torrents` |
| 8 | 适配 `app/downloader/client/transmission.py` | 同上 |
| 9 | 适配 `app/downloader/client/aria2.py` | 同上（如需要） |
| 10 | 适配 `app/downloader/client/thunder.py` | 同上（如需要） |
| 11 | 修改 `app/downloader/client_factory.py` | 使用注册表，简化 `_build_class` |
| 12 | 修改 `app/core/module_config.py` | `DOWNLOADER_CONF` 和 `TORRENTREMOVER_DICT` 改为动态收集 |
| 13 | 新建 `app/downloader/client/rtorrent.py` | 基于新架构实现 Rtorrent |

## 向后兼容

- `_IDownloadClient` 保留原有方法名，仅增加类型注解和默认实现；子类未覆盖的方法继续正常工作
- `client_factory.py` 的公共 API（`get_client`、`get_status`、`get_downloader_conf` 等）签名不变，内部实现改为调用注册表
- `DOWNLOADER_CONF` 的 JSON 结构不变，前端无需改动
- `get_remove_torrents` 接口变更（`dict` → `RemoveStrategy`）影响调用方，需同步修改调用层。调用层位于 `app/services/downloader_core.py` 和插件中，预计修改点 2-3 处

## 新增 Rtorrent 时的变化量对比

| 事项 | 重构前 | 重构后 |
|------|--------|--------|
| 添加枚举 | `app/utils/types.py` +1 行 | 同前 |
| 创建实现文件 | `app/downloader/client/rtorrent.py`（~700 行，复制粘贴大量通用逻辑） | `app/downloader/client/rtorrent.py`（~250 行，仅实现连接和状态映射） |
| 修改 UI 配置 | `app/core/module_config.py` `DOWNLOADER_CONF` 硬编码 | **无需修改**，`config_schema` 自包含 |
| 修改删种配置 | `app/core/module_config.py` `TORRENTREMOVER_DICT` 硬编码 | **无需修改**，动态收集 |
| 修改工厂 | `app/downloader/client_factory.py` 无需改 | 同前 |

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 改动面大，影响现有下载器功能 | 逐文件适配，每步通过 ruff + pyright；QB 和 TR 完整测试后再适配 Aria2/迅雷 |
| `RemoveStrategy` 接口变更影响调用方 | 调用层修改与下载器适配同步进行，确保编译/类型检查通过 |
| 注册表遗漏已有下载器 | 所有现有下载器统一在 `client/__init__.py` 中显式 `register()`，工厂加载时通过注册表获取，不依赖扫描 |
| 前端依赖 `DOWNLOADER_CONF` 结构 | 动态收集时保持输出结构与原来完全一致 |

## Consequences

- 新增下载器从修改 3-4 个文件降至 2 个文件（枚举 + 实现类）
- 删种、转移、进度展示等通用逻辑不再重复
- 接口类型安全使调用方和 IDE 都能获得准确提示
- 下载器配置自包含后，`module_config.py` 不再膨胀
- 为后续「下载器插件化」（允许第三方包注册下载器）打下基础
