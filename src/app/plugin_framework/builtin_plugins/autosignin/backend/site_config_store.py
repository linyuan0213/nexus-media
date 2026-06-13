"""站点声明式配置存储 — 默认配置 + 用户自定义覆盖。"""

from app.plugin_framework.context import PluginContext
from app.utils.json_utils import JsonUtils

from .handlers._declarative import DeclarativeSiteConfig

_DEFAULT_SITES: list[DeclarativeSiteConfig] = [
    DeclarativeSiteConfig(
        site_url="rousi.pro",
        method="post",
        auth_type="bearer",
        auth_source={"type": "header", "name": "x-sign-token", "strip_prefix": "Bearer "},
        headers={"content-type": "application/json"},
        response_type="json",
        json_success_path="code",
        json_success_value=0,
        already_markers=["已签到"],
    ),
    DeclarativeSiteConfig(
        site_url="hdarea.club",
        method="post",
        data={"action": "sign_in"},
        success_markers=["此次签到您获得"],
        already_markers=["请不要重复签到哦"],
    ),
    DeclarativeSiteConfig(
        site_url="yemapt.org",
        method="get",
        auth_type="cookie_raw",
    ),
    DeclarativeSiteConfig(
        site_url="zhuque.io",
        method="get",
        auth_type="cookie_raw",
    ),
    DeclarativeSiteConfig(
        site_url="btschool.club",
        method="get",
        auth_type="cookie_raw",
    ),
]


class SiteConfigStore:
    _FILENAME = "site_configs.json"

    def __init__(self, plugin_ctx: PluginContext):
        self._ctx = plugin_ctx

    def load(self) -> list[DeclarativeSiteConfig]:
        content = self._ctx.read_data(self._FILENAME)
        if not content:
            return list(_DEFAULT_SITES)
        try:
            raw = JsonUtils.loads(content)
            return [DeclarativeSiteConfig(**item) for item in raw]
        except Exception:
            self._ctx.warn(f"读取 {self._FILENAME} 失败，使用默认配置")
            return list(_DEFAULT_SITES)

    def save_defaults(self):
        if self._ctx.read_data(self._FILENAME):
            return
        data = [cfg.__dict__ for cfg in _DEFAULT_SITES]
        self._ctx.write_data(self._FILENAME, JsonUtils.dumps(data, ensure_ascii=False, indent=2))
