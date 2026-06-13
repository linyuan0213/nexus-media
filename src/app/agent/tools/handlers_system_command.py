"""System command handler — 系统运维类工具."""

from typing import Any

from app.agent.tools.base import ToolResult
from app.schemas.scheduler import PauseSchedulerJobRequest, ResumeSchedulerJobRequest, RunSchedulerJobRequest


def system_command(deps: dict[str, Any], action: str, target: str = "", **_) -> ToolResult:
    if action.startswith("scheduler_"):
        return _handle_scheduler(deps, action, target)
    if action.startswith("brush_"):
        return _handle_brush(deps, action, target)
    if action.startswith("site_"):
        return _handle_site(deps, action, target)
    if action.startswith("rss_"):
        return _handle_rss(deps, action, target)
    if action == "transfer_run":
        deps["filetransfer_service"].transfer_manually("", "", "link")
        return ToolResult(success=True, data="文件转移任务已触发")
    if action == "sync_run":
        deps["sync_service"].transfer_sync()
        return ToolResult(success=True, data="目录同步任务已触发")
    if action == "subscribe_search_all":
        deps["subscription_monitor"].run()
        return ToolResult(success=True, data="订阅监控任务已触发")
    if action == "auto_remove_torrents":
        deps["torrentremover_service"].auto_remove_torrents()
        return ToolResult(success=True, data="自动删种任务已触发")
    if action == "truncate_transfer_blacklist":
        deps["filetransfer_service"].truncate_transfer_blacklist()
        return ToolResult(success=True, data="转移黑名单已清理")
    if action == "truncate_rss_history":
        deps["rss_helper"].truncate_rss_history()
        deps["subscribe_service"].truncate_rss_episodes()
        return ToolResult(success=True, data="RSS历史已清理")
    if action == "re_identify":
        deps["sync_service"].re_identify_items(flag="unidentification", ids=[])
        return ToolResult(success=True, data="未识别项重新识别已触发")
    if action == "restart_server":
        deps["system_lifecycle_service"].restart_server()
        return ToolResult(success=True, data="服务器重启指令已发送")
    return ToolResult(success=False, error=f"未知命令: {action}")


def _handle_scheduler(deps: dict[str, Any], action: str, target: str) -> ToolResult:
    svc = deps["scheduler_service"]
    if action == "scheduler_list":
        resp = svc.get_jobs()
        jobs = resp.data if resp.code == 0 else []
        return ToolResult(
            success=True,
            data={
                "jobs": [{"id": j.id, "name": j.name, "paused": j.paused, "next_run": j.next_run_time} for j in jobs]
            },
        )
    if action == "scheduler_run":
        resp = svc.run_job(RunSchedulerJobRequest(id=target))
        return ToolResult(success=resp.code == 0, data=resp.msg)
    if action == "scheduler_pause":
        resp = svc.pause_job(PauseSchedulerJobRequest(id=target))
        return ToolResult(success=resp.code == 0, data=resp.msg)
    if action == "scheduler_resume":
        resp = svc.resume_job(ResumeSchedulerJobRequest(id=target))
        return ToolResult(success=resp.code == 0, data=resp.msg)
    return ToolResult(success=False, error=f"未知调度命令: {action}")


def _handle_brush(deps: dict[str, Any], action: str, target: str) -> ToolResult:
    svc = deps["brush_service"]
    if action == "brush_list":
        tasks = svc.get_tasks()
        return ToolResult(
            success=True,
            data={
                "tasks": [
                    {"id": t.get("id"), "name": t.get("name"), "site": t.get("site"), "state": t.get("state")}
                    for t in tasks
                ]
            },
        )
    if action == "brush_delete":
        if not target:
            return ToolResult(success=False, error="请指定刷流任务ID")
        svc.delete_task(target)
        return ToolResult(success=True, data=f"刷流任务 {target} 已删除")
    return ToolResult(success=False, error=f"未知刷流命令: {action}")


def _handle_site(deps: dict[str, Any], action: str, target: str) -> ToolResult:
    if action == "site_list":
        svc = deps["site_service"]
        sites = svc.get_sites()
        return ToolResult(success=True, data={"sites": [{"id": s.id, "name": s.name} for s in sites]})
    if action == "site_refresh":
        if target:
            deps["site_userinfo"].refresh_site_data_now(specify_sites=[target])
            return ToolResult(success=True, data=f"站点 {target} 数据已刷新")
        deps["site_userinfo"].refresh_site_data_now()
        return ToolResult(success=True, data="所有站点数据已刷新")
    return ToolResult(success=False, error=f"未知站点命令: {action}")


def _handle_rss(deps: dict[str, Any], action: str, target: str) -> ToolResult:
    svc = deps["rss_task_service"]
    if action == "rss_list":
        tasks = svc.get_rsstask_info()
        return ToolResult(success=True, data={"tasks": [{"id": t.get("id"), "name": t.get("name")} for t in tasks]})
    if action == "rss_run":
        if not target:
            return ToolResult(success=False, error="请指定RSS任务ID")
        svc.check_task_rss(int(target))
        return ToolResult(success=True, data=f"RSS任务 {target} 已执行")
    return ToolResult(success=False, error=f"未知RSS命令: {action}")
