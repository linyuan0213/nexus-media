import json
import threading

import log
from app.db.repositories.system_dict_repo_adapter import SystemDictRepositoryAdapter
from app.domain.enums import SystemConfigKey
from app.utils.json_utils import JsonUtils


class SystemConfig:
    """系统配置单例 — 首次实例化时从数据库加载，后续复用缓存."""

    _type = "SystemConfig"
    _instance: "SystemConfig | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "SystemConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._repo = SystemDictRepositoryAdapter()
        self.systemconfig: dict = {}
        self._load_config()
        self._initialized = True

    def _load_config(self):
        rows = self._repo.list_by_type(self._type)
        for row in rows:
            if not row or not row.value:
                continue
            if self._is_obj(row.value):
                try:
                    self.systemconfig[row.key] = JsonUtils.loads(row.value)
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
            JsonUtils.dumps(value)
            if self._is_obj(value) and value is not None
            else str(value)
            if value is not None
            else ""
        )
        self._repo.set(self._type, key, db_value)

    def get(self, key=None):
        """获取系统设置"""
        if not key:
            return self.systemconfig
        if isinstance(key, SystemConfigKey):
            key = key.value
        return self.systemconfig.get(key)
