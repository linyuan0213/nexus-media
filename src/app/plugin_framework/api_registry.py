"""插件自定义 API 注册表.

插件通过 PluginContext.register_api(path, handler) 注册自定义接口，
由 /api/plugin-framework/plugins/{plugin_id}/api/{path} 通用调度路由统一分发。

handler 约定：handler(params: dict) -> dict
- 返回 {"success": bool, "message": str, "data": ...} 时映射为 success/fail 响应
- 返回其他值时包装为 success(data=result)
"""

import threading
from collections.abc import Callable

PluginApiHandler = Callable[[dict], object]

_handlers: dict[tuple[str, str], PluginApiHandler] = {}
_lock = threading.Lock()


def register_api(plugin_id: str, path: str, handler: PluginApiHandler) -> None:
    """注册插件 API 处理器"""
    normalized = path.strip("/")
    if not plugin_id or not normalized:
        return
    with _lock:
        _handlers[(plugin_id, normalized)] = handler


def unregister_plugin_apis(plugin_id: str) -> None:
    """移除插件的全部 API 注册（卸载/禁用时调用）"""
    with _lock:
        for key in [k for k in _handlers if k[0] == plugin_id]:
            _handlers.pop(key, None)


def get_api_handler(plugin_id: str, path: str) -> PluginApiHandler | None:
    """获取插件 API 处理器"""
    with _lock:
        return _handlers.get((plugin_id, path.strip("/")))
