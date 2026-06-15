"""Config services - 索引器、媒体服务器、系统配置与配置更新."""

import json
from typing import cast

from sqlalchemy import text

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.core.system_config import SystemConfig
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.config_repo_adapter import MediaServerRepositoryAdapter
from app.domain.enums import SystemConfigKey
from app.indexer.indexer import Indexer
from app.infrastructure.cache_system import TokenCache
from app.mediaserver import MediaServer
from app.schemas.system import (
    ConfigUpdateResultDTO,
    IndexerConfigResultDTO,
    MediaServerConfigResultDTO,
)
from app.services.indexer_service import IndexerService
from app.services.web.utils import set_config_value
from app.utils import ExceptionUtils
from app.utils.json_utils import JsonUtils
from app.utils.submodule_loader import SubmoduleLoader


class IndexerConfigService:
    """
    索引器配置业务服务
    负责保存索引器配置、兼容旧配置迁移、测试连接
    """

    def __init__(self, indexer_service: IndexerService, indexer: Indexer, system_config: SystemConfig | None = None):
        self._system_config = system_config or SystemConfig()
        self._indexer_service = indexer_service
        self._indexer = indexer

    def save_config(self, data: dict) -> IndexerConfigResultDTO:
        """保存索引器配置"""
        name = data.get("type") or ""
        test = data.get("test") in [True, "true", "on", "1", 1]
        # 兼容旧配置：首次保存时从配置文件迁移
        existing = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
        if name != "builtin" and (not existing or name not in existing):
            old_cfg = settings.get(name)
            if old_cfg:
                existing[name] = dict(old_cfg)
        # 提取并保存索引器详细配置
        config = {}
        for key, value in data.items():
            if key.startswith(name + "."):
                config[key.split(".", 1)[1]] = value
        if config:
            existing[name] = config
        if existing:
            self._system_config.set(SystemConfigKey.IndexerConfig, existing)
        # 保存当前使用的索引器
        self._system_config.set(SystemConfigKey.SearchIndexer, name)
        # 保存builtin站点的选中状态
        if name == "builtin":
            sites = data.get("indexer_sites")
            if sites is not None:
                self._system_config.set(SystemConfigKey.UserIndexerSites, sites)
        # 刷新 Indexer 单例配置
        self._indexer._refresh()
        # 测试连接
        if test and name != "builtin":
            try:
                schemas = SubmoduleLoader.import_submodules(
                    "app.indexer.client", filter_func=lambda _, obj: hasattr(obj, "client_id")
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return IndexerConfigResultDTO(
                            success=True, code=0 if status else 1, msg="测试成功" if status else "测试失败"
                        )
                return IndexerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return IndexerConfigResultDTO(success=False, code=-1, msg=str(e))
        return IndexerConfigResultDTO(success=True)


class MediaServerConfigService:
    """
    媒体服务器配置业务服务
    负责保存媒体服务器配置、测试连接
    """

    def __init__(self, media_server: MediaServer, config_repo=None):

        self._config_repo = config_repo or MediaServerRepositoryAdapter()
        self._media_server = media_server

    def get_media_servers_info(self) -> dict:
        """获取媒体服务器配置信息（包含服务器列表、默认服务器名称）"""
        servers = self._config_repo.get_media_servers()
        default_server = self._config_repo.get_default_media_server()
        server_dict = {}
        for item in servers:
            try:
                cfg = JsonUtils.loads(str(item.CONFIG)) if str(item.CONFIG or "") else {}
            except json.JSONDecodeError:
                cfg = {}
            server_dict[item.NAME] = {
                "id": item.ID,
                "name": item.NAME,
                "enabled": item.ENABLED,
                "is_default": item.IS_DEFAULT,
                "config": cfg,
            }
        return {
            "servers": server_dict,
            "default_server": default_server.NAME if default_server else None,
        }

    def save_config(self, data: dict) -> MediaServerConfigResultDTO:
        """保存媒体服务器配置"""
        name = data.get("type") or ""
        test = data.get("test") in [True, "true", "on", "1", 1]
        config = {}
        for key, value in data.items():
            if key.startswith(name + "."):
                config[key.split(".", 1)[1]] = value
        if not config:
            return MediaServerConfigResultDTO(success=False, code=-1, msg="配置为空")
        enabled = 1 if config.get("enabled") else 0
        is_default = 1 if config.get("is_default") else 0
        item = self._config_repo.get_media_server_by_name(name)
        sid = cast(int, item.ID) if item else None
        self._config_repo.update_media_server(
            sid=int(sid) if sid else None,
            name=name,
            enabled=enabled,
            config=JsonUtils.dumps(config),
            is_default=is_default,
        )
        # 如果有设置默认，需要清理其他默认并同步 ENABLED
        if is_default:
            self._config_repo.set_default_media_server(name)
        # 刷新 MediaServer 单例配置
        self._media_server._refresh()
        TokenCache.delete("index")
        # 测试连接
        if test:
            try:
                schemas = SubmoduleLoader.import_submodules(
                    "app.mediaserver.client", filter_func=lambda _, obj: hasattr(obj, "client_id")
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return MediaServerConfigResultDTO(
                            success=True, code=0 if status else 1, msg="测试成功" if status else "测试失败"
                        )
                return MediaServerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return MediaServerConfigResultDTO(success=False, code=-1, msg=str(e))
        return MediaServerConfigResultDTO(success=True)


class SystemConfigService:
    """
    系统配置业务服务
    """

    def __init__(self, system_config: SystemConfig | None = None):
        self._system_config = system_config or SystemConfig()

    def get(self, key=None):
        """获取系统配置项"""
        return self._system_config.get(key)

    def set(self, key: str, value) -> None:
        """设置系统配置项"""
        self._system_config.set(key=key, value=value)

    def set_config(self, key: str, value) -> bool:
        """设置系统配置项（兼容旧接口）"""
        if not key or not value:
            return False
        self._system_config.set(key=key, value=value)
        return True

    def reset_db_version(self) -> None:
        """重置数据库 alembic_version 表（用于版本回滚后重建）"""
        with BaseRepository().session() as db:
            db.execute(text("DROP TABLE IF EXISTS alembic_version"))


class ConfigUpdateService:
    """
    配置更新业务服务（文件配置 + 数据库配置合并更新）
    """

    @staticmethod
    def update_config(data: dict) -> ConfigUpdateResultDTO:
        cfg = settings.get()
        config_test = False
        for key, value in dict(data).items():
            if key == "test" and value:
                config_test = True
                continue
            cfg = set_config_value(cfg, key, value)
        if not config_test:
            cfg.pop("test", None)
            settings.save(cfg)
            settings.reload()
        return ConfigUpdateResultDTO(success=True, test_mode=config_test)
