"""
工具执行器 — 将 Agent 工具调用映射到实际业务服务

职责：
- 持有各 Service 实例引用
- 根据工具名和参数调用对应 Service 方法
- 统一错误处理和日志记录

本层允许依赖 Service / Message / Media 等模块，因为位于 Agent 之上。
"""

import json as _json

import log
from app.agent.tools.base import ToolResult
from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.media.service import MediaService
from app.message.templates import DEFAULT_MESSAGE_TEMPLATES
from app.schemas.scheduler import PauseSchedulerJobRequest, ResumeSchedulerJobRequest, RunSchedulerJobRequest
from app.services.brush_service import BrushService
from app.services.downloader_core import DownloaderCore
from app.services.indexer_service import IndexerService
from app.services.rss_automation.task_service import RssTaskService
from app.services.search_service import Searcher
from app.services.site_service import SiteService
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.subscribe_service import SubscribeService
from app.services.sync_service import SyncService
from app.services.system.lifecycle import SystemLifecycleService
from app.services.torrentremover_core import TorrentRemoverService


class ToolExecutor:
    """工具执行器 — 桥接 Agent Tools 与业务 Service"""

    def __init__(
        self,
        message,
        thread_executor,
        scheduler_core,
        event_bus,
        download_monitor,
        filetransfer_service,
        rss_helper,
        search_intent_agent,
        site_userinfo,
        scheduler_service,
        message_client_service,
        sync_service: SyncService,
        subscription_monitor: SubscriptionMonitor,
        torrentremover_service: TorrentRemoverService,
        subscribe_service: SubscribeService,
        system_lifecycle_service: SystemLifecycleService,
        brush_service: BrushService,
        site_service: SiteService,
        rss_task_service: RssTaskService,
        media_service: MediaService,
        indexer_service: IndexerService,
        downloader_core: DownloaderCore,
        searcher: Searcher,
    ):
        self._message = message
        self._thread_executor = thread_executor
        self._scheduler_core = scheduler_core
        self._event_bus = event_bus
        self._download_monitor = download_monitor
        self._filetransfer_service = filetransfer_service
        self._rss_helper = rss_helper
        self._search_intent_agent = search_intent_agent
        self._site_userinfo = site_userinfo
        self._scheduler_service = scheduler_service
        self._message_client_service = message_client_service
        self._sync_service = sync_service
        self._subscription_monitor = subscription_monitor
        self._torrentremover_service = torrentremover_service
        self._subscribe_service = subscribe_service
        self._system_lifecycle_service = system_lifecycle_service
        self._brush_service = brush_service
        self._site_service = site_service
        self._rss_task_service = rss_task_service
        self._media_service = media_service
        self._indexer_service = indexer_service
        self._downloader_core = downloader_core
        self._searcher = searcher

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """执行指定工具"""
        log.info(f"[ToolExecutor]执行工具: {tool_name}, 参数: {kwargs}")
        handler = getattr(self, f"_{tool_name}", None)
        if not handler:
            return ToolResult(success=False, error=f"未实现工具: {tool_name}")
        try:
            return handler(**kwargs)
        except Exception as e:
            log.error(f"[ToolExecutor]{tool_name} 执行失败: {e}")
            return ToolResult(success=False, error=str(e))

    # ------------------------------------------------------------------
    # system_command
    # ------------------------------------------------------------------

    def _system_command(self, action: str, target: str = "", **_) -> ToolResult:
        if action.startswith("scheduler_"):
            return self._handle_scheduler(action, target)
        if action.startswith("brush_"):
            return self._handle_brush(action, target)
        if action.startswith("site_"):
            return self._handle_site(action, target)
        if action.startswith("rss_"):
            return self._handle_rss(action, target)
        if action == "transfer_run":
            self._filetransfer_service.transfer_manually("", "", "link")
            return ToolResult(success=True, data="文件转移任务已触发")
        if action == "sync_run":
            self._sync_service.transfer_sync()
            return ToolResult(success=True, data="目录同步任务已触发")
        if action == "subscribe_search_all":
            self._subscription_monitor.run()
            return ToolResult(success=True, data="订阅监控任务已触发")
        if action == "auto_remove_torrents":
            self._torrentremover_service.auto_remove_torrents()
            return ToolResult(success=True, data="自动删种任务已触发")
        if action == "truncate_transfer_blacklist":
            self._filetransfer_service.truncate_transfer_blacklist()
            return ToolResult(success=True, data="转移黑名单已清理")
        if action == "truncate_rss_history":
            self._rss_helper.truncate_rss_history()
            self._subscribe_service.truncate_rss_episodes()
            return ToolResult(success=True, data="RSS历史已清理")
        if action == "re_identify":
            self._sync_service.re_identify_items(flag="unidentification", ids=[])
            return ToolResult(success=True, data="未识别项重新识别已触发")
        if action == "restart_server":
            self._system_lifecycle_service.restart_server()
            return ToolResult(success=True, data="服务器重启指令已发送")
        return ToolResult(success=False, error=f"未知命令: {action}")

    def _handle_scheduler(self, action: str, target: str) -> ToolResult:
        svc = self._scheduler_service
        if action == "scheduler_list":
            resp = svc.get_jobs()
            jobs = resp.data if resp.code == 0 else []
            return ToolResult(
                success=True,
                data={
                    "jobs": [
                        {"id": j.id, "name": j.name, "paused": j.paused, "next_run": j.next_run_time} for j in jobs
                    ]
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

    def _handle_brush(self, action: str, target: str) -> ToolResult:
        svc = self._brush_service
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

    def _handle_site(self, action: str, target: str) -> ToolResult:
        if action == "site_list":
            svc = self._site_service
            sites = svc.get_sites()
            return ToolResult(success=True, data={"sites": [{"id": s.id, "name": s.name} for s in sites]})
        if action == "site_refresh":
            if target:
                self._site_userinfo.refresh_site_data_now(specify_sites=[target])
                return ToolResult(success=True, data=f"站点 {target} 数据已刷新")
            self._site_userinfo.refresh_site_data_now()
            return ToolResult(success=True, data="所有站点数据已刷新")
        return ToolResult(success=False, error=f"未知站点命令: {action}")

    def _handle_rss(self, action: str, target: str) -> ToolResult:
        svc = self._rss_task_service
        if action == "rss_list":
            tasks = svc.get_rsstask_info()
            return ToolResult(success=True, data={"tasks": [{"id": t.get("id"), "name": t.get("name")} for t in tasks]})
        if action == "rss_run":
            if not target:
                return ToolResult(success=False, error="请指定RSS任务ID")
            svc.check_task_rss(int(target))
            return ToolResult(success=True, data=f"RSS任务 {target} 已执行")
        return ToolResult(success=False, error=f"未知RSS命令: {action}")

    # ------------------------------------------------------------------
    # message_template
    # ------------------------------------------------------------------

    def _message_template(
        self, action: str, msg_type: str = "", title: str = "", text: str = "", client_id: int = 0, **_
    ) -> ToolResult:
        if action == "list":
            types = list(DEFAULT_MESSAGE_TEMPLATES.keys())
            return ToolResult(success=True, data={"types": types})

        if action == "get":
            if not msg_type:
                return ToolResult(success=False, error="请指定消息类型 msg_type")
            default = DEFAULT_MESSAGE_TEMPLATES.get(msg_type)
            if not default:
                return ToolResult(success=False, error=f"未知消息类型: {msg_type}")
            custom = None
            if client_id:
                clients = self._message.get_message_client_info()
                for c in clients:
                    if c.get("id") == client_id:
                        custom = c.get("templates", {}).get(msg_type)
                        break
            return ToolResult(success=True, data={"msg_type": msg_type, "default": default, "custom": custom})

        if action == "update":
            if not msg_type or not title or not text:
                return ToolResult(success=False, error="update 需要 msg_type, title, text 参数")
            clients = self._message.get_message_client_info()
            target = next((c for c in clients if (client_id == 0 or c.get("id") == client_id)), None)
            if not target:
                return ToolResult(success=False, error="未找到目标客户端")
            templates = target.get("templates", {}) or {}
            templates[msg_type] = {"title": title, "text": text}
            self._message_client_service.upsert_client(
                name=target.get("name"),
                cid=target.get("id"),
                ctype=target.get("type"),
                config=_json.dumps(target.get("config", {})),
                switches=target.get("switches", []),
                interactive=1 if target.get("interactive") else 0,
                enabled=1 if target.get("enabled") else 0,
                templates=_json.dumps(templates),
            )
            return ToolResult(success=True, data=f"模板 {msg_type} 已更新")

        return ToolResult(success=False, error=f"未知操作: {action}")

    # ------------------------------------------------------------------
    # media_search
    # ------------------------------------------------------------------

    def _media_search(
        self, query: str, media_type: str = "", year: int = 0, season: int = 0, episode: int = 0, limit: int = 10, **_
    ) -> ToolResult:
        intent_agent = self._search_intent_agent
        intent = intent_agent.parse(query) if intent_agent.ready else None
        keywords = intent.keywords if intent else query

        media = self._media_service
        indexer = self._indexer_service
        media_info = media.get_media_info(title=keywords)
        if not media_info or not media_info.title:
            return ToolResult(success=False, error=f"无法识别媒体: {keywords}")

        filter_args = {
            "year": year or (intent.year if intent else 0),
            "season": [season or (intent.season if intent else 0)]
            if (season or (intent.season if intent else 0))
            else None,
            "episode": [episode or (intent.episode if intent else 0)]
            if (episode or (intent.episode if intent else 0))
            else None,
            "type": media_type or (intent.media_type if intent else ""),
            "seeders": True,
        }

        results = indexer.search_by_keyword(
            key_word=media_info.title,
            filter_args=filter_args,
            match_media=media_info,
        )
        if not results:
            return ToolResult(success=True, data=f"未找到 '{keywords}' 的资源")

        formatted = []
        for r in results[:limit]:
            formatted.append(
                {
                    "title": getattr(r, "title", "") or getattr(r, "org_string", ""),
                    "site": getattr(r, "site", ""),
                    "size": getattr(r, "size", 0),
                    "seeders": getattr(r, "seeders", 0),
                    "enclosure": getattr(r, "enclosure", ""),
                }
            )
        return ToolResult(
            success=True,
            data={
                "query": query,
                "keywords": keywords,
                "media_title": media_info.title,
                "results_count": len(results),
                "results": formatted,
            },
        )

    # ------------------------------------------------------------------
    # resource_filter
    # ------------------------------------------------------------------

    def _resource_filter(
        self,
        resources: list,
        min_seeders: int = 0,
        max_size_gb: float = 0,
        sites: list | None = None,
        exclude_sites: list | None = None,
        sort_by: str = "seeders",
        preferred_qualities: list | None = None,
        **_,
    ) -> ToolResult:
        filtered = resources.copy()

        if min_seeders > 0:
            filtered = [r for r in filtered if r.get("seeders", 0) >= min_seeders]

        if max_size_gb > 0:

            def _parse_size_gb(s):
                if not s:
                    return 0
                s = s.upper().replace(",", "")
                try:
                    if "TB" in s:
                        return float(s.replace("TB", "").strip()) * 1024
                    if "GB" in s:
                        return float(s.replace("GB", "").strip())
                    if "MB" in s:
                        return float(s.replace("MB", "").strip()) / 1024
                except ValueError:
                    pass
                return float("inf")

            filtered = [r for r in filtered if _parse_size_gb(r.get("size", "")) <= max_size_gb]

        if sites:
            filtered = [r for r in filtered if r.get("site", "") in sites]
        if exclude_sites:
            filtered = [r for r in filtered if r.get("site", "") not in exclude_sites]

        if preferred_qualities:

            def _score(r):
                title = r.get("title", "")
                return sum(
                    len(preferred_qualities) - i
                    for i, q in enumerate(preferred_qualities)
                    if q.lower() in title.lower()
                )

            filtered.sort(key=_score, reverse=True)

        if sort_by == "seeders":
            filtered.sort(key=lambda r: r.get("seeders", 0), reverse=True)
        elif sort_by == "site":
            filtered.sort(key=lambda r: r.get("site", ""))

        return ToolResult(
            success=True,
            data={
                "original_count": len(resources),
                "filtered_count": len(filtered),
                "results": filtered,
            },
        )

    # ------------------------------------------------------------------
    # media_download
    # ------------------------------------------------------------------

    def _media_download(
        self,
        title: str = "",
        media_type: str = "",
        year: int = 0,
        enclosure: str = "",
        site: str = "",
        size: str = "",
        season: int = 0,
        episode: int = 0,
        **_,
    ) -> ToolResult:
        # 模式1：直接下载（有 enclosure 链接）
        if enclosure:
            media_info = self._media_service.get_media_info(title=title)
            if not media_info:
                # 识别失败时，用原始资源名创建最小 MediaInfo，确保下载和通知能正常进行
                media_info = MediaInfo()
                media_info.title = title or "未知资源"
            # 保存原始资源名称，用于下载历史记录和消息通知
            media_info.org_string = title or ""
            media_info.enclosure = enclosure
            media_info.site = site
            if season:
                media_info.begin_season = season
            if episode:
                media_info.begin_episode = episode
            self._downloader_core.download(media_info=media_info)
            return ToolResult(success=True, data=f"已开始下载: {media_info.title}")

        # 模式2：搜索后下载
        if not title:
            return ToolResult(success=False, error="需要提供 title 或 enclosure")

        media_info = self._media_service.get_media_info(title=title)
        if not media_info or not media_info.title:
            return ToolResult(success=False, error=f"无法识别媒体: {title}")
        # 保存原始查询标题，用于下载历史记录
        media_info.org_string = title

        if media_type:
            type_map = {"movie": MediaType.MOVIE, "tv": MediaType.TV, "anime": MediaType.ANIME}
            media_info.type = type_map.get(media_type, media_info.type)

        searcher = self._searcher
        search_result, no_exists, search_count, download_count = searcher.search_one_media(
            media_info=media_info, in_from=SearchType.API, no_exists={}
        )

        if not search_count:
            return ToolResult(success=False, error=f"未搜索到 '{title}' 的资源")
        if download_count:
            return ToolResult(success=True, data=f"'{title}' 搜索成功，已下载 {download_count} 个资源")
        return ToolResult(success=True, data=f"'{title}' 搜索到 {search_count} 个结果，但未匹配到符合下载条件的资源")

    # ------------------------------------------------------------------
    # media_subscribe
    # ------------------------------------------------------------------

    def _media_subscribe(
        self, title: str, media_type: str, year: int = 0, season: int = 0, tmdbid: str = "", **_
    ) -> ToolResult:
        media_info = self._media_service.get_media_info(title=title)
        if not media_info or not media_info.title:
            return ToolResult(success=False, error=f"无法识别媒体: {title}")

        if media_type:
            type_map = {"movie": MediaType.MOVIE, "tv": MediaType.TV, "anime": MediaType.ANIME}
            media_info.type = type_map.get(media_type, media_info.type)

        mediaid = tmdbid or media_info.tmdb_id
        if mediaid:
            mediaid = str(mediaid)
        else:
            mediaid = None

        code, msg, media_info = self._subscribe_service.add_rss_subscribe(
            mtype=media_info.type,
            name=media_info.title,
            year=media_info.year,
            season=season or media_info.begin_season,
            mediaid=mediaid,
            channel="auto",
        )

        if code == 0:
            return ToolResult(success=True, data=f"已添加订阅: {media_info.get_title_string()}")
        return ToolResult(success=False, error=f"添加订阅失败: {msg}")
