"""事件处理器注册配置.

集中显式声明所有包含 @on_event 的 handler 模块路径，
避免隐式 import 或运行时扫描带来的可维护性问题。

新增 handler 模块时，只需在此列表追加对应的模块路径。
"""

EVENT_HANDLER_MODULES: list[str] = [
    "app.services.subscribe.handlers",
    "app.services.transfer.handlers",
    "app.services.download.handlers",
    "app.services.search.handlers",
    "app.services.system.handlers",
]
