"""
系统指令工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._system_command 处理

支持的命令：
- scheduler_list / scheduler_run / scheduler_pause / scheduler_resume
- brush_list / brush_delete
- site_list / site_refresh
- rss_list / rss_run
- transfer_run / sync_run
- subscribe_search_all / auto_remove_torrents
- truncate_transfer_blacklist / truncate_rss_history
- re_identify / restart_server
"""

from app.agent.tools.base import BaseTool, ToolRegistry


class SystemCommandTool(BaseTool):
    """系统指令工具"""

    name = "system_command"
    description = (
        "执行系统级命令。"
        "调度任务: scheduler_list/run/pause/resume; "
        "刷流: brush_list/delete; "
        "站点: site_list/refresh; "
        "RSS: rss_list/run; "
        "转移: transfer_run; "
        "同步: sync_run; "
        "订阅搜索: subscribe_search_all; "
        "自动删种: auto_remove_torrents; "
        "清理转移缓存: truncate_transfer_blacklist; "
        "清理RSS缓存: truncate_rss_history; "
        "重新识别: re_identify; "
        "重启: restart_server"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "scheduler_list",
                    "scheduler_run",
                    "scheduler_pause",
                    "scheduler_resume",
                    "brush_list",
                    "brush_delete",
                    "site_list",
                    "site_refresh",
                    "rss_list",
                    "rss_run",
                    "transfer_run",
                    "sync_run",
                    "subscribe_search_all",
                    "auto_remove_torrents",
                    "truncate_transfer_blacklist",
                    "truncate_rss_history",
                    "re_identify",
                    "restart_server",
                ],
                "description": "要执行的命令类型",
            },
            "target": {"type": "string", "description": "操作目标ID或名称"},
        },
        "required": ["action"],
    }

    def execute(self, **kwargs):
        raise NotImplementedError("system_command 应由 ToolExecutor 执行")


ToolRegistry.register(SystemCommandTool())
