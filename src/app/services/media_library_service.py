import os
from concurrent.futures import ThreadPoolExecutor

import log
from app.db.repositories.media_library_route_repo_adapter import MediaLibraryRouteRepositoryAdapter
from app.domain.entities.media_library_route import MediaLibraryRouteEntity
from app.domain.enums import SystemConfigKey
from app.infrastructure.cache_system import TokenCache
from app.mediaserver import MediaServer
from app.schemas.media import LibrarySpaceDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.utils import SystemUtils


class MediaLibraryService:
    """
    媒体库业务服务
    """

    def __init__(
        self,
        media_server: MediaServer,
        filetransfer: FileTransfer,
        system_config,
        thread_executor,
        media_config_service,
        route_repo=None,
    ):
        self._media_server = media_server
        self._filetransfer = filetransfer
        self._system_config = system_config
        self._thread_executor = thread_executor
        self._media_config_service = media_config_service
        self._route_repo = route_repo or MediaLibraryRouteRepositoryAdapter()

    def get_sync_state(self, server_id: int | None = None) -> str:
        """获取指定实例同步状态文本"""
        status = self._media_server.get_mediasync_status(server_id)
        if not status:
            return "未同步"
        return "电影：{}，电视剧：{}，同步时间：{}".format(
            status.get("movie_count"),
            status.get("tv_count"),
            status.get("time"),
        )

    def get_servers(self) -> list[dict]:
        return self._media_server.get_server_options()

    def start_sync(self, librarys: list, server_id: int | None = None):
        """开始指定实例的媒体库同步，并按实例持久化库选择."""
        TokenCache.delete("index")
        if not librarys:
            raise ValueError("请选择需要同步的媒体库")
        target_server_id = self._media_server.resolve_server_id(server_id)
        if target_server_id is None:
            raise ValueError("未找到可用的媒体服务器")
        self._system_config.set(
            key=f"{SystemConfigKey.SyncLibrary.value}::{target_server_id}",
            value=librarys,
        )
        # 保留全局键作为旧版本/单实例兼容
        self._system_config.set(key=SystemConfigKey.SyncLibrary, value=librarys)
        self._thread_executor.submit(self._media_server.sync_mediaserver, target_server_id, librarys)

    def refresh_library(self, server_id: int | None = None, items: list | None = None):
        """刷新指定实例，可按项目刷新或刷新整库。"""
        if items:
            return self._media_server.refresh_library_by_items(items, server_id=server_id)
        return self._media_server.refresh_root_library(server_id=server_id)

    def get_media_count(self, server_id: int | None = None) -> dict | None:
        """获取指定实例媒体库统计"""
        media_counts = self._media_server.get_medias_count(server_id)
        user_count = self._media_server.get_user_count(server_id)
        if media_counts:
            return {
                "Movie": "{:,}".format(media_counts.get("MovieCount")),
                "Series": "{:,}".format(media_counts.get("SeriesCount")),
                "Episodes": "{:,}".format(media_counts.get("EpisodeCount")) if media_counts.get("EpisodeCount") else "",
                "Music": "{:,}".format(media_counts.get("SongCount")),
                "User": user_count,
            }
        return None

    def get_play_history(self, server_id: int | None = None) -> list:
        """获取指定实例播放记录"""
        return self._media_server.get_activity_log(30, server_id=server_id)

    def get_libraries(self, server_id: int | None = None):
        """获取指定实例媒体库列表"""
        return self._media_server.get_libraries(server_id)

    def get_resume(self, num=12, server_id: int | None = None):
        """获取指定实例继续观看"""
        return self._media_server.get_resume(num=num, server_id=server_id)

    def get_latest(self, num=20, server_id: int | None = None):
        """获取指定实例最新入库"""
        return self._media_server.get_latest(num=num, server_id=server_id)

    def _get_server_section(self, server: dict) -> dict:
        server_id = server["id"]

        def _safe(call, fallback):
            try:
                return call()
            except Exception as err:  # noqa: BLE001
                log.debug(f"[MediaLibrary]{server['name']} 获取数据失败: {err}")
                return fallback

        def _with_server(items):
            return [{**item, "server_id": server_id, "server_name": server["name"]} for item in items if item]

        counts = _safe(lambda: self.get_media_count(server_id), None)
        libraries = _safe(lambda: self.get_libraries(server_id), [])
        resumes = _safe(lambda: self.get_resume(server_id=server_id), [])
        latests = _safe(lambda: self.get_latest(server_id=server_id), [])
        activity = _safe(lambda: self.get_play_history(server_id), [])
        sync_state = _safe(lambda: self.get_sync_state(server_id), "未同步")
        return {
            "server": server,
            "server_id": server_id,
            "server_name": server["name"],
            "server_success": counts is not None,
            "media_counts": counts or {},
            "sync_state": sync_state,
            "librarys": _with_server(libraries or []),
            "resumes": _with_server(resumes or []),
            "latests": _with_server(latests or []),
            "activitys": _with_server(activity or []),
        }

    def get_home_data(self, requested_id: int | None = None) -> dict:
        """聚合并发获取各实例首页数据，单个实例失败不影响其他实例。"""
        servers = self.get_servers()
        if requested_id is not None:
            servers = [item for item in servers if item["id"] == requested_id]
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(servers)))) as executor:
            sections = list(executor.map(self._get_server_section, servers))

        def _number(section: dict, key: str) -> int:
            try:
                return int(str(section["media_counts"].get(key, 0) or 0).replace(",", ""))
            except (TypeError, ValueError):
                return 0

        count_keys = ("Movie", "Series", "Music", "Episodes", "User")
        totals = {key: sum(_number(section, key) for section in sections) for key in count_keys}
        try:
            space_info = self.get_space_info()
            library_spaces = {
                "UsedPercent": space_info.used_percent,
                "FreeSpace": space_info.free_space,
                "UsedSpace": space_info.used_space,
                "TotalSpace": space_info.total_space,
            }
        except Exception as err:  # noqa: BLE001
            log.debug(f"[MediaLibrary]获取空间信息失败: {err}")
            library_spaces = {}
        return {
            "server_success": any(section["server_success"] for section in sections),
            "servers": self.get_servers(),
            "sections": sections,
            "media_counts": totals,
            "user_count": totals["User"],
            "activitys": sorted(
                [item for section in sections for item in section["activitys"]],
                key=lambda item: str(item.get("date") or ""),
                reverse=True,
            )[:30],
            "library_spaces": library_spaces,
            "librarys": [item for section in sections for item in section["librarys"]],
            "resumes": [item for section in sections for item in section["resumes"]],
            "latests": [item for section in sections for item in section["latests"]],
        }

    def get_routes(self) -> list[dict]:
        servers = {item["id"]: item["name"] for item in self.get_servers()}
        return [
            {
                "id": route.id,
                "content_profile": route.content_profile,
                "target_path": route.target_path,
                "server_id": route.server_id,
                "server_name": servers.get(route.server_id, f"实例 {route.server_id}"),
                "backend_id": route.backend_id,
                "library_id": route.library_id,
                "enabled": route.enabled,
                "note": route.note,
            }
            for route in self._route_repo.list()
        ]

    def save_route(self, data: dict, route_id: int | None = None) -> dict:
        profile = str(data.get("content_profile") or "").strip()
        target_path = str(data.get("target_path") or "").strip()
        server_id = int(data.get("server_id") or 0)
        if not profile and not target_path:
            raise ValueError("请填写目标目录或内容画像")
        if not server_id:
            raise ValueError("目标媒体服务器不能为空")
        if server_id not in {item["id"] for item in self.get_servers()}:
            raise ValueError("目标媒体服务器不存在或未启用")
        normalized_path = os.path.normpath(target_path).replace("\\", "/").rstrip("/") if target_path else ""
        for route in self._route_repo.list():
            if route.id == route_id:
                continue
            existing_path = (
                os.path.normpath(route.target_path).replace("\\", "/").rstrip("/") if route.target_path else ""
            )
            if route.content_profile == profile and existing_path == normalized_path:
                raise ValueError("相同目录和内容画像的路由已存在")
        entity = MediaLibraryRouteEntity(
            id=route_id or 0,
            content_profile=profile,
            target_path=target_path,
            server_id=server_id,
            backend_id=str(data.get("backend_id") or "local").strip() or "local",
            library_id=str(data.get("library_id") or "").strip() or None,
            enabled=bool(data.get("enabled", True)),
            note=str(data.get("note") or ""),
        )
        saved = self._route_repo.upsert(entity)
        self._media_server.refresh()
        return {
            "id": saved.id,
            "content_profile": saved.content_profile,
            "target_path": saved.target_path,
            "server_id": saved.server_id,
            "backend_id": saved.backend_id,
        }

    def delete_route(self, route_id: int) -> bool:
        deleted = self._route_repo.delete(route_id)
        self._media_server.refresh()
        return deleted

    def get_space_info(self) -> LibrarySpaceDTO:
        """获取媒体库存储空间"""
        media_cfg = self._media_config_service.get_config()
        movie_paths = media_cfg.get("movie_path") or []
        tv_paths = media_cfg.get("tv_path") or []
        anime_paths = media_cfg.get("anime_path") or []

        all_paths = movie_paths + tv_paths + anime_paths
        if not all_paths:
            return LibrarySpaceDTO()

        space_result = SystemUtils.calculate_space_usage(all_paths)
        if not isinstance(space_result, tuple):
            return LibrarySpaceDTO()
        total_space, free_space = space_result
        if not total_space:
            return LibrarySpaceDTO()

        used_space = total_space - free_space
        used_percent = round((used_space / total_space) * 100, 1)

        def fmt_space(val):
            if val > 1024:
                return f"{round(val / 1024, 2):,} TB"
            return f"{round(val, 2):,} GB"

        return LibrarySpaceDTO(
            used_percent=used_percent,
            free_space=fmt_space(free_space),
            used_space=fmt_space(used_space),
            total_space=fmt_space(total_space),
        )
