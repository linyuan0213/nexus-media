"""
Plugin Framework v2 Repository
处理插件框架v2的数据库操作：清单、配置、日志
"""

import json

from app.db.transaction import auto_commit
from app.db.models import PLUGINCONFIG, PLUGINHOOKS, PLUGINLOGS, PLUGINMANIFEST
from app.db.repositories.base_repository import BaseRepository
from app.domain.entities.plugin import (
    PluginConfigEntity,
    PluginManifestEntity,
)


class PluginFrameworkRepository(BaseRepository):
    """插件框架v2仓储"""

    # ==================== Plugin Manifest ====================

    def get_all_manifests(self) -> list:
        """获取所有已安装插件清单：内置在前，按类别分组，名称排序"""
        records = self._db.query(PLUGINMANIFEST).all()
        # Python 层面排序，跨数据库兼容
        records.sort(
            key=lambda r: (
                not (r.PATH and "builtin_plugins" in r.PATH),
                r.CATEGORY or "",
                r.NAME or "",
            )
        )
        return records

    def get_manifest_by_id(self, plugin_id: str) -> PLUGINMANIFEST:
        """根据ID获取插件清单"""
        return self._db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).first()

    @auto_commit(BaseRepository._db)
    def insert_manifest(self, entity: PluginManifestEntity) -> bool:
        """插入插件清单"""
        self._db.insert(
            PLUGINMANIFEST(
                ID=entity.id,
                NAME=entity.name,
                VERSION=entity.version,
                AUTHOR=entity.author,
                DESCRIPTION=entity.description,
                CATEGORY=entity.category,
                TAGS=json.dumps(entity.tags, ensure_ascii=False),
                ICON=entity.icon,
                COLOR=entity.color,
                MANIFEST_JSON=entity.manifest_json,
                ENABLED=entity.enabled,
                INSTALLED=getattr(entity, "installed", True),
                PATH=entity.path,
            )
        )
        return True

    @auto_commit(BaseRepository._db)
    def update_manifest(self, entity: PluginManifestEntity) -> bool:
        """更新插件清单"""
        update_data = {
            "NAME": entity.name,
            "VERSION": entity.version,
            "AUTHOR": entity.author,
            "DESCRIPTION": entity.description,
            "CATEGORY": entity.category,
            "TAGS": json.dumps(entity.tags, ensure_ascii=False),
            "ICON": entity.icon,
            "COLOR": entity.color,
            "MANIFEST_JSON": entity.manifest_json,
            "ENABLED": entity.enabled,
            "PATH": entity.path,
        }
        if hasattr(entity, "installed"):
            update_data["INSTALLED"] = entity.installed
        self._db.query(PLUGINMANIFEST).filter(entity.id == PLUGINMANIFEST.ID).update(update_data)
        return True

    @auto_commit(BaseRepository._db)
    def delete_manifest(self, plugin_id: str) -> bool:
        """删除插件清单"""
        self._db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).delete()
        return True

    @auto_commit(BaseRepository._db)
    def set_manifest_enabled(self, plugin_id: str, enabled: bool) -> bool:
        """设置插件启用状态"""
        self._db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).update({"ENABLED": enabled})
        return True

    @auto_commit(BaseRepository._db)
    def set_manifest_installed(self, plugin_id: str, installed: bool) -> bool:
        """设置插件安装状态"""
        self._db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).update({"INSTALLED": installed})
        return True

    # ==================== Plugin Config ====================

    def get_config(self, plugin_id: str) -> PLUGINCONFIG:
        """获取插件配置"""
        return self._db.query(PLUGINCONFIG).filter(plugin_id == PLUGINCONFIG.PLUGIN_ID).first()

    @auto_commit(BaseRepository._db)
    def save_config(self, entity: PluginConfigEntity) -> bool:
        """保存插件配置"""
        existing = self._db.query(PLUGINCONFIG).filter(entity.plugin_id == PLUGINCONFIG.PLUGIN_ID).first()
        if existing:
            existing.CONFIG = json.dumps(entity.config, ensure_ascii=False)
        else:
            self._db.insert(
                PLUGINCONFIG(
                    PLUGIN_ID=entity.plugin_id,
                    CONFIG=json.dumps(entity.config, ensure_ascii=False),
                )
            )
        return True

    @auto_commit(BaseRepository._db)
    def delete_config(self, plugin_id: str) -> bool:
        """删除插件配置"""
        self._db.query(PLUGINCONFIG).filter(plugin_id == PLUGINCONFIG.PLUGIN_ID).delete()
        return True

    # ==================== Plugin Logs ====================

    @auto_commit(BaseRepository._db)
    def insert_log(self, plugin_id: str, level: str, message: str) -> bool:
        """插入日志"""
        self._db.insert(
            PLUGINLOGS(
                PLUGIN_ID=plugin_id,
                LEVEL=level,
                MESSAGE=message,
            )
        )
        return True

    def get_logs_by_plugin(self, plugin_id: str, page: int = 1, page_size: int = 20) -> list:
        """分页获取插件日志"""
        begin_pos = 0 if page == 1 else (page - 1) * page_size
        return (
            self._db.query(PLUGINLOGS)
            .filter(plugin_id == PLUGINLOGS.PLUGIN_ID)
            .order_by(PLUGINLOGS.CREATED_AT.desc())
            .limit(page_size)
            .offset(begin_pos)
            .all()
        )

    def count_logs_by_plugin(self, plugin_id: str) -> int:
        """统计插件日志数量"""
        return self._db.query(PLUGINLOGS).filter(plugin_id == PLUGINLOGS.PLUGIN_ID).count()

    @auto_commit(BaseRepository._db)
    def clear_logs_by_plugin(self, plugin_id: str) -> bool:
        """清空插件日志"""
        self._db.query(PLUGINLOGS).filter(plugin_id == PLUGINLOGS.PLUGIN_ID).delete()
        return True

    # ==================== Plugin Hooks ====================

    def get_all_hooks(self) -> list:
        """获取所有启用的钩子订阅"""
        return self._db.query(PLUGINHOOKS).filter(PLUGINHOOKS.ENABLED).all()

    @auto_commit(BaseRepository._db)
    def insert_hook(self, plugin_id: str, event: str) -> bool:
        """插入钩子订阅"""
        self._db.insert(PLUGINHOOKS(PLUGIN_ID=plugin_id, EVENT=event, ENABLED=True))
        return True

    @auto_commit(BaseRepository._db)
    def delete_hook(self, plugin_id: str, event: str) -> bool:
        """删除指定钩子订阅"""
        self._db.query(PLUGINHOOKS).filter(plugin_id == PLUGINHOOKS.PLUGIN_ID, event == PLUGINHOOKS.EVENT).delete()
        return True

    @auto_commit(BaseRepository._db)
    def delete_hooks_by_plugin(self, plugin_id: str) -> bool:
        """删除插件的所有钩子订阅"""
        self._db.query(PLUGINHOOKS).filter(plugin_id == PLUGINHOOKS.PLUGIN_ID).delete()
        return True
