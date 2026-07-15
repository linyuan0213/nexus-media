"""RSS 配置存储 — 内置 JSON + 用户自定义覆盖。"""

import os

from app.core.root_path import get_project_root
from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils


class RssConfigStore:
    """加载插件目录下的 rss_configs/*.json，并支持用户自定义覆盖。"""

    _CONFIG_DIR = os.path.join(
        get_project_root(),
        "src",
        "app",
        "plugin_framework",
        "builtin_plugins",
        "autogenrss",
        "backend",
        "rss_configs",
    )
    _USER_FILE = "rss_configs.json"

    def __init__(self, plugin_ctx: PluginContext, site_engine=None):
        self._ctx = plugin_ctx
        self._site_engine = site_engine

    def load_builtin(self) -> list[dict]:
        configs: list[dict] = []
        if not os.path.isdir(self._CONFIG_DIR):
            return configs
        for fname in sorted(os.listdir(self._CONFIG_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._CONFIG_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    configs.append(JsonUtils.load(f))
            except Exception:
                self._ctx.warn(f"加载RSS配置失败: {fname}")
        return configs

    def load_user(self) -> list[dict]:
        content = self._ctx.read_data(self._USER_FILE)
        if not content:
            return []
        try:
            return JsonUtils.loads(content)
        except Exception:
            self._ctx.warn(f"读取 {self._USER_FILE} 失败，使用内置配置")
            return []

    def load(self) -> list[dict]:
        """用户配置按 site_id 覆盖内置配置。"""
        builtin = {cfg["site_id"]: cfg for cfg in self.load_builtin()}
        user = {cfg["site_id"]: cfg for cfg in self.load_user()}
        merged = dict(builtin)
        merged.update(user)
        return list(merged.values())
