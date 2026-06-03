import json
import re
from typing import Any

from app.infrastructure.cache_system.manager import get_cache_manager


class CookiecloudAdapter:
    def __init__(self):
        self._cache = get_cache_manager().get_or_create("plugin_cookiecloud", cache_type="redis")

    def get_cookie(self, domain_url: str) -> str:
        cookie = self._cache.get(f"cookie:{domain_url}")
        if cookie:
            if isinstance(cookie, bytes):
                return cookie.decode("utf-8")
            return str(cookie)
        return ""

    def get_local_storage(self, domain_url: str) -> Any:
        storage = self._cache.get(f"local_storage:{domain_url}")
        if storage:
            if isinstance(storage, bytes):
                storage = storage.decode("utf-8")
            data = json.loads(storage)
            # 修复反斜杠转义问题，保留单个反斜杠，修复双反斜杠
            return self._fix_backslash_escapes(data)
        return {}

    def _fix_backslash_escapes(self, data):
        """
        递归处理数据中的反斜杠转义问题，修复双反斜杠为单反斜杠
        """
        if isinstance(data, dict):
            return {key: self._fix_backslash_escapes(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._fix_backslash_escapes(item) for item in data]
        elif isinstance(data, str):
            fixed_string = re.sub(r"\\\\", r"\\", data)
            return fixed_string
        else:
            return data
