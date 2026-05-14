import json

from app.db.repositories.system_dict_repo_adapter import SystemDictRepositoryAdapter
from app.utils.commons import SingletonMeta
from app.utils.types import SystemConfigKey


class SystemConfig(metaclass=SingletonMeta):
    """系统配置单例"""

    _type = "SystemConfig"

    def __init__(self):
        self._repo = SystemDictRepositoryAdapter()
        self.systemconfig = {}
        self.init_config()

    def init_config(self):
        """缓存系统设置"""
        import log

        rows = self._repo.list_by_type(self._type)
        for row in rows:
            if not row or not row.value:
                continue
            if self._is_obj(row.value):
                try:
                    self.systemconfig[row.key] = json.loads(row.value)
                except json.JSONDecodeError:
                    log.warn(f"配置项 {row.key} 的 JSON 格式损坏，跳过")
                    continue
            else:
                self.systemconfig[row.key] = row.value

    @staticmethod
    def _is_obj(value):
        if isinstance(value, (list, dict)):
            return True
        return str(value).startswith("{") or str(value).startswith("[")

    def set(self, key, value):
        """设置系统设置"""
        if isinstance(key, SystemConfigKey):
            key = key.value
        self.systemconfig[key] = value

        db_value = (
            json.dumps(value) if self._is_obj(value) and value is not None else str(value) if value is not None else ""
        )
        self._repo.set(self._type, key, db_value)

    def get(self, key=None):
        """获取系统设置"""
        if not key:
            return self.systemconfig
        if isinstance(key, SystemConfigKey):
            key = key.value
        return self.systemconfig.get(key)
