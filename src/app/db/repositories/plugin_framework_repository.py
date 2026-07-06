"""
Plugin Framework v2 Repository
处理插件框架v2的数据库操作：清单、配置、日志
"""

from app.db.models import PLUGINCONFIG, PLUGINHOOKS, PLUGINLOGS, PLUGINMANIFEST
from app.db.repositories.base_repository import BaseRepository
from app.domain.entities.plugin import (
    PluginConfigEntity,
    PluginManifestEntity,
)
from app.utils.json_utils import JsonUtils


class PluginFrameworkRepository(BaseRepository):
    """插件框架v2仓储"""

    # ==================== Plugin Manifest ====================

    def get_all_manifests(self) -> list:
        """获取所有已安装插件清单：内置在前，按类别分组，名称排序"""
        with self.session() as db:
            records = db.query(PLUGINMANIFEST).all()
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
        with self.session() as db:
            return db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).first()

    def insert_manifest(self, entity: PluginManifestEntity) -> bool:
        """插入插件清单"""
        with self.session() as db:
            db.add(
                PLUGINMANIFEST(
                    ID=entity.id,
                    NAME=entity.name,
                    VERSION=entity.version,
                    AUTHOR=entity.author,
                    DESCRIPTION=entity.description,
                    CATEGORY=entity.category,
                    TAGS=JsonUtils.dumps(entity.tags, ensure_ascii=False),
                    ICON=entity.icon,
                    COLOR=entity.color,
                    MANIFEST_JSON=entity.manifest_json,
                    ENABLED=entity.enabled,
                    INSTALLED=getattr(entity, "installed", True),
                    PATH=entity.path,
                )
            )
            return True

    def update_manifest(self, entity: PluginManifestEntity) -> bool:
        """更新插件清单"""
        with self.session() as db:
            update_data = {
                "NAME": entity.name,
                "VERSION": entity.version,
                "AUTHOR": entity.author,
                "DESCRIPTION": entity.description,
                "CATEGORY": entity.category,
                "TAGS": JsonUtils.dumps(entity.tags, ensure_ascii=False),
                "ICON": entity.icon,
                "COLOR": entity.color,
                "MANIFEST_JSON": entity.manifest_json,
                "ENABLED": entity.enabled,
                "PATH": entity.path,
            }
            if hasattr(entity, "installed"):
                update_data["INSTALLED"] = entity.installed
            db.query(PLUGINMANIFEST).filter(entity.id == PLUGINMANIFEST.ID).update(update_data)
            return True

    def delete_manifest(self, plugin_id: str) -> bool:
        """删除插件清单"""
        with self.session() as db:
            db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).delete()
            return True

    def set_manifest_enabled(self, plugin_id: str, enabled: bool) -> bool:
        """设置插件启用状态"""
        with self.session() as db:
            db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).update({"ENABLED": enabled})
            return True

    def set_manifest_installed(self, plugin_id: str, installed: bool) -> bool:
        """设置插件安装状态"""
        with self.session() as db:
            db.query(PLUGINMANIFEST).filter(plugin_id == PLUGINMANIFEST.ID).update({"INSTALLED": installed})
            return True

    def get_enabled_plugin_ids(self) -> list[str]:
        """获取所有已启用的插件ID"""
        with self.session() as db:
            rows = db.query(PLUGINMANIFEST.ID).filter(PLUGINMANIFEST.ENABLED).all()
            return [r[0] for r in rows]

    # ==================== Plugin Config ====================

    def get_config(self, plugin_id: str) -> PLUGINCONFIG:
        """获取插件配置"""
        with self.session() as db:
            return db.query(PLUGINCONFIG).filter(plugin_id == PLUGINCONFIG.PLUGIN_ID).first()

    def save_config(self, entity: PluginConfigEntity) -> bool:
        """保存插件配置"""
        with self.session() as db:
            existing = db.query(PLUGINCONFIG).filter(entity.plugin_id == PLUGINCONFIG.PLUGIN_ID).first()
            if existing:
                existing.CONFIG = JsonUtils.dumps(entity.config, ensure_ascii=False)
            else:
                db.add(
                    PLUGINCONFIG(
                        PLUGIN_ID=entity.plugin_id,
                        CONFIG=JsonUtils.dumps(entity.config, ensure_ascii=False),
                    )
                )
            return True

    def delete_config(self, plugin_id: str) -> bool:
        """删除插件配置"""
        with self.session() as db:
            db.query(PLUGINCONFIG).filter(plugin_id == PLUGINCONFIG.PLUGIN_ID).delete()
            return True

    # ==================== Plugin Logs ====================

    def insert_log(self, plugin_id: str, level: str, message: str) -> bool:
        """插入日志"""
        with self.session() as db:
            db.add(
                PLUGINLOGS(
                    PLUGIN_ID=plugin_id,
                    LEVEL=level,
                    MESSAGE=message,
                )
            )
            return True

    def get_logs_by_plugin(self, plugin_id: str, page: int = 1, page_size: int = 20) -> list:
        """分页获取插件日志"""
        with self.session() as db:
            begin_pos = 0 if page == 1 else (page - 1) * page_size
            return (
                db.query(PLUGINLOGS)
                .filter(plugin_id == PLUGINLOGS.PLUGIN_ID)
                .order_by(PLUGINLOGS.CREATED_AT.desc())
                .limit(page_size)
                .offset(begin_pos)
                .all()
            )

    def count_logs_by_plugin(self, plugin_id: str) -> int:
        """统计插件日志数量"""
        with self.session() as db:
            return db.query(PLUGINLOGS).filter(plugin_id == PLUGINLOGS.PLUGIN_ID).count()

    def clear_logs_by_plugin(self, plugin_id: str) -> bool:
        """清空插件日志"""
        with self.session() as db:
            db.query(PLUGINLOGS).filter(plugin_id == PLUGINLOGS.PLUGIN_ID).delete()
            return True

    # ==================== Plugin Hooks ====================

    def get_all_hooks(self) -> list:
        """获取所有启用的钩子订阅"""
        with self.session() as db:
            return db.query(PLUGINHOOKS).filter(PLUGINHOOKS.ENABLED).all()

    def insert_hook(self, plugin_id: str, event: str) -> bool:
        """插入钩子订阅"""
        with self.session() as db:
            db.add(PLUGINHOOKS(PLUGIN_ID=plugin_id, EVENT=event, ENABLED=True))
            return True

    def delete_hook(self, plugin_id: str, event: str) -> bool:
        """删除指定钩子订阅"""
        with self.session() as db:
            db.query(PLUGINHOOKS).filter(plugin_id == PLUGINHOOKS.PLUGIN_ID, event == PLUGINHOOKS.EVENT).delete()
            return True

    def delete_hooks_by_plugin(self, plugin_id: str) -> bool:
        """删除插件的所有钩子订阅"""
        with self.session() as db:
            db.query(PLUGINHOOKS).filter(plugin_id == PLUGINHOOKS.PLUGIN_ID).delete()
            return True
