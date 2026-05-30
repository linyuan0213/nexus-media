"""
配置领域实体
包含消息客户端、下载器、过滤规则、媒体服务器等配置实体
"""

import json
from dataclasses import dataclass, fields
from typing import Any, Optional


@dataclass
class MessageClientEntity:
    """消息客户端实体"""

    id: int
    name: str
    type: str
    config: str
    switchs: str
    interactive: bool
    enabled: bool
    note: str | None
    templates: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["MessageClientEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            switchs=orm_model.SWITCHS or "",
            interactive=bool(orm_model.INTERACTIVE),
            enabled=bool(orm_model.ENABLED),
            note=orm_model.NOTE,
            templates=getattr(orm_model, "TEMPLATES", None),
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "switchs": self.switchs,
            "interactive": self.interactive,
            "enabled": self.enabled,
            "note": self.note,
            "templates": self.templates,
        }


@dataclass
class DownloaderEntity:
    """下载器实体"""

    id: int
    name: str
    type: str
    config: str
    transfer: str
    only_nexus_media: bool
    match_path: bool
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["DownloaderEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            transfer=orm_model.TRANSFER or "",
            only_nexus_media=bool(orm_model.ONLY_NEXUS_MEDIA),
            match_path=bool(orm_model.MATCH_PATH),
            enabled=bool(orm_model.ENABLED),
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "transfer": self.transfer,
            "only_nexus_media": self.only_nexus_media,
            "match_path": self.match_path,
            "enabled": self.enabled,
        }


@dataclass
class FilterGroupEntity:
    """过滤规则组实体"""

    id: int
    name: str
    default: bool
    create_time: str | None
    update_time: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["FilterGroupEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.GROUP_NAME or "",
            default=str(orm_model.IS_DEFAULT).upper() == "Y",
            create_time=None,
            update_time=None,
        )

    _ORM_FIELD_MAP = {
        "is_default": "default",
    }

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "default": self.default,
            "create_time": self.create_time,
            "update_time": self.update_time,
        }


@dataclass
class FilterRuleEntity:
    """过滤规则实体"""

    id: int
    group_id: int
    name: str
    include: str
    exclude: str
    note: str | None
    priority: int
    create_time: str | None
    update_time: str | None

    @classmethod
    def from_orm(cls, orm_model) -> Optional["FilterRuleEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            group_id=orm_model.GROUP_ID or 0,
            name=orm_model.ROLE_NAME or "",
            include=orm_model.INCLUDE or "",
            exclude=orm_model.EXCLUDE or "",
            note=orm_model.NOTE,
            priority=int(orm_model.PRIORITY or 0),
            create_time=None,
            update_time=None,
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "name": self.name,
            "include": self.include,
            "exclude": self.exclude,
            "note": self.note,
            "priority": self.priority,
            "create_time": self.create_time,
            "update_time": self.update_time,
        }


@dataclass
class MediaServerEntity:
    """媒体服务器实体"""

    id: int
    name: str
    type: str
    config: str
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["MediaServerEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            type=orm_model.TYPE or "",
            config=orm_model.CONFIG or "",
            enabled=bool(orm_model.ENABLED),
        )

    _ORM_FIELD_MAP = {}

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "enabled": self.enabled,
        }


@dataclass
class TorrentRemoveTaskEntity:
    """自动删种任务实体"""

    id: int
    name: str
    downloader: str
    config: str
    enabled: bool

    @classmethod
    def from_orm(cls, orm_model) -> Optional["TorrentRemoveTaskEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            name=orm_model.NAME or "",
            downloader=orm_model.DOWNLOADER or "",
            config=orm_model.CONFIG or "",
            enabled=bool(orm_model.ENABLED),
        )

    _ORM_FIELD_MAP = {}

    @property
    def parsed_config(self) -> dict[str, Any]:
        """解析 JSON 配置字符串为字典"""
        try:
            return json.loads(self.config) if self.config else {}
        except Exception:
            return {}

    @property
    def action_display(self) -> str:
        """动作展示文本"""
        return {1: "暂停", 2: "删除种子", 3: "删除种子及文件"}.get(self.parsed_config.get("action", 0), "未知")

    @staticmethod
    def validate_params(data: dict) -> list[str]:
        """校验删种任务参数字典，返回错误信息列表（空列表表示验证通过）"""
        errors = []
        name = data.get("name")
        if not name:
            errors.append("名称参数不合法")
        action = data.get("action")
        if not str(action).isdigit() or int(action or 0) not in (1, 2, 3):
            errors.append("动作参数不合法")
        interval = data.get("interval")
        if not str(interval).isdigit():
            errors.append("运行间隔参数不合法")
        enabled = data.get("enabled")
        if not str(enabled).isdigit() or int(enabled or 0) not in (0, 1):
            errors.append("状态参数不合法")
        samedata = data.get("samedata")
        if not str(samedata).isdigit() or int(samedata or 0) not in (0, 1):
            errors.append("处理辅种参数不合法")
        only_nexus_media = data.get("only_nexus_media")
        if not str(only_nexus_media).isdigit() or int(only_nexus_media or 0) not in (0, 1):
            errors.append("仅处理NEXUS_MEDIA添加种子参数不合法")
        ratio = data.get("ratio") or 0
        if not str(ratio).replace(".", "").isdigit():
            errors.append("分享率参数不合法")
        seeding_time = data.get("seeding_time") or 0
        if not str(seeding_time).isdigit():
            errors.append("做种时间参数不合法")
        upload_avs = data.get("upload_avs") or 0
        if not str(upload_avs).isdigit():
            errors.append("平均上传速度参数不合法")
        size = data.get("size")
        size = str(size).split("-") if size else []
        if size and (len(size) != 2 or not str(size[0]).isdigit() or not str(size[-1]).isdigit()):
            errors.append("种子大小参数不合法")
        return errors

    @staticmethod
    def validate_config(config: dict) -> list[str]:
        """校验删种配置字典，返回错误信息列表"""
        errors = []
        ratio = config.get("ratio")
        if ratio is not None and not str(ratio).replace(".", "").isdigit():
            errors.append("分享率参数不合法")
        seeding_time = config.get("seeding_time")
        if seeding_time is not None and not str(seeding_time).isdigit():
            errors.append("做种时间参数不合法")
        upload_avs = config.get("upload_avs")
        if upload_avs is not None and not str(upload_avs).isdigit():
            errors.append("平均上传速度参数不合法")
        size = config.get("size")
        if size and (not isinstance(size, list) or len(size) != 2):
            errors.append("种子大小参数不合法")
        return errors

    def __getattr__(self, name: str):
        """兼容旧代码的大写属性访问"""
        lower_name = name.lower()
        field_name = self._ORM_FIELD_MAP.get(lower_name, lower_name)
        if field_name in {f.name for f in fields(self)}:
            return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "downloader": self.downloader,
            "config": self.config,
            "enabled": self.enabled,
        }
