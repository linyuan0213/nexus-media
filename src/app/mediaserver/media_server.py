import hashlib
import threading
import time
from typing import Any

import log
from app.core.settings import settings

# isort: off
from app.media import MediaService  # 先完成 app.media 初始化，避免 SystemConfig 循环导入

# isort: on
from app.db.repositories.config_repo_adapter import MediaServerRepositoryAdapter
from app.db.repositories.media_library_route_repo_adapter import MediaLibraryRouteRepositoryAdapter
from app.db.repositories.media_sync_repo_adapter import MediaSyncRepositoryAdapter
from app.domain.enums import ProgressKey, SystemConfigKey
from app.domain.media_types import ProviderMediaType
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.infrastructure.message_queue.base import MessageQueue
from app.infrastructure.progress import ProgressTracker
from app.infrastructure.system_config import SystemConfig
from app.mediaserver.registry import get_all_clients
from app.message import Message
from app.utils import ExceptionUtils
from app.utils.json_utils import JsonUtils
from app.utils.path_utils import PathUtils

lock = threading.Lock()

# "已入库"实时检查缓存：(mtype, title, year, season) -> (expire_ts, exists)
_LIVE_LIBRARY_TTL = 300
_LIVE_LIBRARY_CACHE: dict[tuple, tuple[float, bool]] = {}
server_lock = threading.Lock()


class MediaServer:
    """媒体服务器管理器.

    由 lifespan 通过 AppContext 创建并管理生命周期。
    """

    _server_type: str | None = None
    _server = None
    mediadb: MediaSyncRepositoryAdapter | None = None
    progress: ProgressTracker | None = None
    message: Message | None = None
    media: MediaService | None = None
    systemconfig: SystemConfig | None = None
    config_repo: MediaServerRepositoryAdapter | None = None
    _message_queue: MessageQueue

    def __init__(
        self,
        media_service: MediaService,
        message: Message,
        message_queue: MessageQueue,
        media_sync_repo: MediaSyncRepositoryAdapter | None = None,
        progress_helper: ProgressTracker | None = None,
        system_config: SystemConfig | None = None,
        media_server_repo: MediaServerRepositoryAdapter | None = None,
        route_repo: MediaLibraryRouteRepositoryAdapter | None = None,
    ):
        self.mediadb = media_sync_repo or MediaSyncRepositoryAdapter()
        self.message = message
        self.progress = progress_helper or ProgressTracker()
        self.media = media_service
        self.systemconfig = system_config or SystemConfig()
        self.config_repo = media_server_repo or MediaServerRepositoryAdapter()
        self.route_repo = route_repo or MediaLibraryRouteRepositoryAdapter()
        self._message_queue = message_queue
        self._server_type = None
        self._server: Any = None
        self._servers: dict[int, Any] = {}

    def _refresh(self):
        """重置服务器实例，下次访问时重新构建。"""
        self.refresh()

    def refresh(self) -> None:
        """配置热重载：清除服务器类型与实例缓存，下次访问按新配置重建。"""
        with server_lock:
            self._server_type = None
            self._server = None
            self._servers.clear()

    def __build_class(self, ctype, conf):
        for cls in get_all_clients():
            try:
                if cls.match(ctype):
                    return cls(conf)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    @property
    def server(self):
        return self._get_client()

    def __get_server(self, ctype: str | None, conf=None):
        return self.__build_class(ctype=ctype, conf=conf)

    def _get_client(self, server_id: int | None = None):
        """按实例 ID 获取客户端；客户端初始化在锁外执行。"""
        conf = {}
        target_id = server_id or 0
        with server_lock:
            if self._server is not None:
                if server_id is None:
                    return self._server
                default = self.config_repo.get_default_media_server() if self.config_repo else None
                if default and int(default.ID) == int(server_id):
                    return self._server
            if self.config_repo is None:
                return None
            if server_id is None:
                row = self.config_repo.get_default_media_server()
            else:
                rows = self.config_repo.get_media_servers(int(server_id))
                row = rows[0] if rows else None
            if row is not None and not row.ENABLED:
                return None
            if row is None:
                if self._server is not None:
                    return self._server
                server_type = self._server_type or settings.get("media").get("media_server") or "emby"
            else:
                target_id = int(row.ID)
                if target_id in self._servers:
                    return self._servers[target_id]
                server_type = row.TYPE or row.NAME
                try:
                    conf = JsonUtils.loads(row.CONFIG) if row.CONFIG else {}
                except Exception:
                    conf = {}

        # 客户端初始化可能包含网络请求，不能在全局锁内执行
        client = self.__get_server(server_type, conf if row is not None else None)
        with server_lock:
            if row is None:
                if self._server is None:
                    self._server = client
                self._server_type = server_type
                return self._server
            client = self._servers.setdefault(target_id, client)
            default = self.config_repo.get_default_media_server()
            if default and int(default.ID) == server_id:
                self._server_type = server_type
            return client

    def get_server_options(self) -> list[dict]:
        """返回启用实例摘要，不包含连接密钥。"""
        if self.config_repo is None:
            return []
        default = self.config_repo.get_default_media_server()
        default_id = int(default.ID) if default else None
        return [
            {
                "id": int(row.ID),
                "name": row.NAME,
                "type": row.TYPE or row.NAME,
                "is_default": int(row.ID) == default_id,
            }
            for row in self.config_repo.get_media_servers()
            if row.ENABLED
        ]

    def list_routes(self, content_profile: str | None = None, target_path: str | None = None) -> list[Any]:
        """列出已启用的媒体库路由，供插件统一走公共门面。"""
        route_repo = getattr(self, "route_repo", None)
        if route_repo is None:
            return []
        routes = [
            route
            for route in route_repo.list()
            if route.enabled
            and route.target_path
            and (not content_profile or not route.content_profile or route.content_profile == content_profile)
            and (not target_path or PathUtils.is_path_in_path(route.target_path, target_path))
        ]
        return routes

    def resolve_route(self, content_profile: str | None = None, target_path: str | None = None, routes=None):
        """解析目录/画像路由，保留 server_id 和 library_id 完整目标。"""
        route_repo = getattr(self, "route_repo", None)
        if target_path and route_repo:
            candidates = self.list_routes(content_profile, target_path) if routes is None else []
            if routes is not None:
                for route in routes:
                    if not route.enabled or not route.target_path:
                        continue
                    if content_profile and route.content_profile and route.content_profile != content_profile:
                        continue
                    if PathUtils.is_path_in_path(route.target_path, target_path):
                        candidates.append(route)
            if candidates:
                return max(candidates, key=lambda route: len(route.target_path.replace("\\", "/")))
        if content_profile and route_repo:
            return route_repo.get_profile(content_profile)
        return None

    def resolve_server_id(
        self,
        server_id: int | None = None,
        content_profile: str | None = None,
        target_path: str | None = None,
    ) -> int | None:
        if server_id is not None:
            return int(server_id)
        route = self.resolve_route(content_profile, target_path)
        if route:
            return int(route.server_id)
        default = self.config_repo.get_default_media_server() if self.config_repo else None
        return int(default.ID) if default else None

    def get_type(self, server_id: int | None = None):
        """获取指定实例类型，未指定时使用默认实例。"""
        client = self._get_client(server_id)
        return client.get_type() if client else None

    def get_activity_log(self, limit, server_id: int | None = None):
        """获取指定实例的活动日志。"""
        client = self._get_client(server_id)
        return client.get_activity_log(limit) if client else []

    def get_user_count(self, server_id: int | None = None):
        """获取指定实例的用户数。"""
        client = self._get_client(server_id)
        return client.get_user_count() if client else 0

    def get_medias_count(self, server_id: int | None = None):
        """获取指定实例的媒体统计。"""
        client = self._get_client(server_id)
        return client.get_medias_count() if client else None

    def refresh_root_library(self, server_id: int | None = None, library_id: str | None = None):
        """刷新指定实例，支持按媒体库 ID 定向刷新。"""
        client = self._get_client(server_id)
        if not client:
            return None
        if library_id and hasattr(client, "refresh_library"):
            return client.refresh_library(library_id)
        return client.refresh_root_library()

    def get_episode_image_by_id(self, item_id, season_id, episode_id):
        """
        根据itemid、season_id、episode_id从Emby查询图片地址
        :param item_id: 在Emby中的ID
        :param season_id: 季
        :param episode_id: 集
        :return: 图片对应在TMDB中的URL
        """
        if not self.server:
            return None
        if not item_id or not season_id or not episode_id:
            return None
        return self.server.get_episode_image_by_id(item_id, season_id, episode_id)

    def get_remote_image_by_id(self, item_id, image_type):
        """
        根据ItemId从媒体服务器查询图片地址
        :param item_id: 在Emby中的ID
        :param image_type: 图片的类弄地，poster或者backdrop等
        :return: 图片对应在TMDB中的URL
        """
        if not self.server:
            return None
        if not item_id:
            return None
        return self.server.get_remote_image_by_id(item_id, image_type)

    def get_local_image_by_id(self, item_id):
        """
        根据ItemId从媒体服务器查询图片地址
        :param item_id: 在Emby中的ID
        """
        if not self.server:
            return None
        if not item_id:
            return None
        return self.server.get_local_image_by_id(item_id)

    def get_no_exists_episodes(self, meta_info, season_number, episode_count):
        """
        根据标题、年份、季、总集数，查询媒体服务器中缺少哪几集
        :param meta_info: 已识别的需要查询的媒体信息
        :param season_number: 季号，数字
        :param episode_count: 该季的总集数
        :return: 该季不存在的集号列表
        """
        if not self.server:
            return None
        return self.server.get_no_exists_episodes(meta_info, season_number, episode_count)

    def get_movies(self, title, year=None):
        """
        根据标题和年份，检查电影是否在媒体服务器中存在，存在则返回列表
        :param title: 标题
        :param year: 年份，可以为空，为空时不按年份过滤
        :return: 含title、year属性的字典列表
        """
        if not self.server:
            return None
        return self.server.get_movies(title, year)

    def supports_person_tags(
        self,
        server_id: int | None = None,
        content_profile: str | None = None,
        target_path: str | None = None,
    ) -> bool:
        """目标实例是否支持人物标签读写。"""
        resolved = self.resolve_server_id(server_id, content_profile, target_path)
        client = self._get_client(resolved)
        return bool(client and hasattr(client, "list_persons") and hasattr(client, "add_person_tags"))

    def list_persons(
        self,
        server_id: int | None = None,
        content_profile: str | None = None,
        target_path: str | None = None,
    ) -> list[dict]:
        """按路由解析实例并列出人物条目。"""
        resolved = self.resolve_server_id(server_id, content_profile, target_path)
        client = self._get_client(resolved)
        if not client or not hasattr(client, "list_persons"):
            return []
        return client.list_persons()

    def add_person_tags(
        self,
        person_id: str,
        tags: list[str],
        server_id: int | None = None,
        content_profile: str | None = None,
        target_path: str | None = None,
    ) -> bool:
        """按路由解析实例并给人物追加标签。"""
        resolved = self.resolve_server_id(server_id, content_profile, target_path)
        client = self._get_client(resolved)
        if not client or not hasattr(client, "add_person_tags"):
            return False
        return client.add_person_tags(person_id, tags)

    def _group_items_by_route(
        self,
        items,
        content_profile: str | None = None,
    ) -> dict[tuple[int | None, str | None], list[dict]]:
        grouped: dict[tuple[int | None, str | None], list[dict]] = {}
        routes = self.route_repo.list() if getattr(self, "route_repo", None) else None
        for item in items:
            profile = content_profile or item.get("content_profile")
            target_path = item.get("target_path") or item.get("file_path")
            route = self.resolve_route(profile, target_path, routes=routes)
            target_id = int(route.server_id) if route else self.resolve_server_id()
            library_id = route.library_id if route else None
            grouped.setdefault((target_id, library_id), []).append(item)
        return grouped

    def refresh_library_by_items(
        self,
        items,
        server_id: int | None = None,
        content_profile: str | None = None,
    ):
        """按目录和内容画像分组，分别刷新目标实例。"""
        if not items:
            return
        if server_id is not None:
            return self._refresh_items_for_instance(items, server_id)
        for (target_id, library_id), group_items in self._group_items_by_route(items, content_profile).items():
            if library_id:
                for item in group_items:
                    item.setdefault("library_id", library_id)
            self._refresh_items_for_instance(group_items, target_id)

    def refresh_library_with_scan(
        self,
        items,
        server_id: int | None = None,
        content_profile: str | None = None,
    ):
        """刷新条目后触发路由命中的媒体库扫描，确保新目录也被索引。"""
        if not items:
            return
        if server_id is not None:
            self._scan_instance(items, server_id, None)
            return
        for (target_id, library_id), group_items in self._group_items_by_route(items, content_profile).items():
            if library_id:
                for item in group_items:
                    item.setdefault("library_id", library_id)
            self._scan_instance(group_items, target_id, library_id)

    def _scan_instance(self, items, server_id: int | None, library_id: str | None) -> None:
        """同一实例/媒体库的扫描串行执行，避免并发扫描把 Emby 写成重复剧集。"""
        key = f"mediaserver:scan:{server_id or 0}:{library_id or ''}"
        lock = get_lock_manager().create_lock(key, ttl_seconds=900)
        if not lock.acquire():
            log.info("[MediaServer]媒体库扫描正在执行，跳过重复触发")
            return
        try:
            self._refresh_items_for_instance(items, server_id)
            self.refresh_root_library(server_id=server_id, library_id=library_id)
        finally:
            lock.release()

    def _refresh_items_for_instance(self, items, server_id: int | None):
        client = self._get_client(server_id)
        if not client:
            return
        items_str = str(sorted([str(i) for i in items]))
        lock_key = (
            f"mediaserver:refresh:{server_id}:{hashlib.md5(items_str.encode(), usedforsecurity=False).hexdigest()}"
        )
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            log.info("[MediaServer]媒体库刷新正在执行，跳过")
            return
        try:
            return client.refresh_library_by_items(items)
        finally:
            lock.release()

    def get_libraries(self, server_id: int | None = None):
        """获取指定实例的媒体库列表。"""
        client = self._get_client(server_id)
        return client.get_libraries() if client else []

    def get_items(self, parent, server_id: int | None = None):
        """获取指定实例媒体库中的所有媒体。"""
        client = self._get_client(server_id)
        return client.get_items(parent) if client else []

    def get_play_url(self, item_id, server_id: int | None = None):
        """获取指定实例的播放地址。"""
        client = self._get_client(server_id)
        return client.get_play_url(item_id) if client else None

    def get_tv_episodes(self, item_id=None, server_id: int | None = None, **kwargs):
        """获取指定实例电视剧的所有集数信息。"""
        client = self._get_client(server_id)
        return client.get_tv_episodes(item_id=item_id, **kwargs) if client else []

    def sync_all_mediaservers(self) -> None:
        """定时任务入口：遍历所有启用实例，各自的库选择独立生效."""
        for option in self.get_server_options():
            try:
                self.sync_mediaserver(int(option["id"]))
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[MediaServer]实例 {option.get('name') or option.get('id')} 同步失败: {exc}")

    def sync_mediaserver(self, server_id: int | None = None, library_ids: list[str] | None = None):
        """同步指定实例的媒体库数据到本地数据库。"""
        server_id = self.resolve_server_id(server_id)
        client = self._get_client(server_id)
        if not client or not self.mediadb or not self.progress or not self.systemconfig:
            return
        rows = self.config_repo.get_media_servers(server_id) if self.config_repo and server_id else []
        server_type = (rows[0].TYPE or rows[0].NAME) if rows else self._server_type

        # 进度任务为全局 MediaSync，同步串行执行，避免不同实例互相覆盖进度
        dist_lock = get_lock_manager().create_lock("mediaserver:sync", ttl_seconds=3600)
        acquired = dist_lock.acquire()
        if not acquired:
            log.info("[MediaServer]媒体库同步正在其他实例执行，跳过")
            return

        try:
            with lock:
                log.info("[MediaServer]开始同步媒体库数据...")
                self.progress.start(ProgressKey.MediaSync)
                self.progress.update(ptype=ProgressKey.MediaSync, text="请稍候...")
                # 获取需同步的媒体库：优先实例级选择，旧版本回退全局选择
                if library_ids is not None:
                    librarys = library_ids
                else:
                    librarys = (
                        self.systemconfig.get(f"{SystemConfigKey.SyncLibrary.value}::{server_id}")
                        or self.systemconfig.get(SystemConfigKey.SyncLibrary)
                        or []
                    )
                if not librarys:
                    # 未选择任何媒体库时直接返回：避免清空登记薄后写入为空，导致"已入库"判定全部失效
                    log.warn("[MediaServer]未选择需要同步的媒体库，跳过本次同步（不清空登记薄）")
                    self.progress.end(ProgressKey.MediaSync)
                    return

            # 汇总统计
            medias_count = self.get_medias_count(server_id)
            if not medias_count:
                self.progress.end(ProgressKey.MediaSync)
                return
            libraries = self.get_libraries(server_id)
            # 确认实例可读取后再清理旧登记，避免连接失败导致数据丢失
            self.mediadb.empty(server_type=server_type, server_id=server_id)
            total_media_count = medias_count.get("MovieCount") + medias_count.get("SeriesCount")
            total_count = 0
            movie_count = 0
            tv_count = 0
            for library in libraries:
                if str(library.get("id")) not in librarys:
                    continue
                # 获取媒体库所有项目
                self.progress.update(
                    ptype=ProgressKey.MediaSync, text="正在获取 {} 数据...".format(library.get("name"))
                )
                for item in self.get_items(library.get("id"), server_id):
                    if not item:
                        continue
                    # 更新进度
                    seasoninfo = []
                    total_count += 1
                    item_type = ProviderMediaType.from_value(item.get("type") or "")
                    if item_type == ProviderMediaType.MOVIE:
                        movie_count += 1
                    elif item_type == ProviderMediaType.SERIES:
                        tv_count += 1
                        # 查询剧集信息
                        seasoninfo = self.get_tv_episodes(item.get("id"), server_id=server_id)
                    self.progress.update(
                        ptype=ProgressKey.MediaSync,
                        text="正在同步 {}，已完成：{} / {} ...".format(
                            library.get("name"), total_count, total_media_count
                        ),
                        value=round(100 * total_count / total_media_count, 1),
                    )
                    # 插入数据
                    self.mediadb.insert(
                        server_type=server_type, iteminfo=item, seasoninfo=seasoninfo, server_id=server_id
                    )

            # 更新总体同步情况
            self.mediadb.statistics(
                server_type=server_type,
                total_count=total_count,
                movie_count=movie_count,
                tv_count=tv_count,
                server_id=server_id,
            )
            # 结束进度条
            self.progress.update(
                ptype=ProgressKey.MediaSync, value=100, text=f"媒体库数据同步完成，同步数量：{total_count}"
            )
            self.progress.end(ProgressKey.MediaSync)
            log.info(f"[MediaServer]媒体库数据同步完成，同步数量：{total_count}")
        finally:
            dist_lock.release()

    def check_library_present(
        self,
        mtype,
        title=None,
        year=None,
        tmdbid=None,
        season=None,
        content_profile: str | None = None,
        server_id: int | None = None,
    ) -> bool:
        """按目标实例实时检查媒体库是否存在。"""
        server_id = self.resolve_server_id(server_id, content_profile)
        client = self._get_client(server_id)
        if not client or not title:
            return False
        key = (server_id, str(mtype).lower(), str(title), str(year or ""), str(season or ""))
        now = time.time()
        cached = _LIVE_LIBRARY_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
        result = False
        try:
            numeric_tmdb = str(tmdbid) if tmdbid and str(tmdbid).isdigit() else None
            if str(mtype).lower() == "movie":
                result = bool(client.get_movies(title, year))
                if not result:
                    # 只调用客户端类显式实现的方法，避免 MagicMock/代理对象把动态属性误判为能力。
                    keyword_search = getattr(type(client), "search_movie_keyword", None)
                    if callable(keyword_search):
                        result = bool(keyword_search(client, str(title)))
            else:
                episodes = client.get_tv_episodes(title=title, year=year, tmdbid=numeric_tmdb, season=season or 1)
                result = bool(episodes)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[MediaServer]实时检查媒体库存在性失败 {title}: {e!s}")
            result = False
        _LIVE_LIBRARY_CACHE[key] = (now + _LIVE_LIBRARY_TTL, result)
        return result

    def check_library_present_any(
        self,
        mtype,
        title=None,
        year=None,
        tmdbid=None,
        season=None,
        content_profile: str | None = None,
        alternate_titles: list[str] | None = None,
    ) -> bool:
        """跨全部启用实例检查媒体是否已入库（多实例媒体库）."""
        titles = [str(title or "").strip(), *[str(t or "").strip() for t in (alternate_titles or [])]]
        titles = [item for item in dict.fromkeys(titles) if item]
        if not titles:
            return False
        for server in self.get_server_options():
            for candidate in titles:
                if self.check_library_present(
                    mtype,
                    title=candidate,
                    year=year,
                    tmdbid=tmdbid,
                    season=season,
                    content_profile=content_profile,
                    server_id=int(server["id"]),
                ):
                    return True
        return False

    def check_item_exists(
        self,
        mtype,
        title=None,
        year=None,
        tmdbid=None,
        season=None,
        episode=None,
        content_profile: str | None = None,
        server_id: int | None = None,
    ):
        """按目标实例检查同步登记中的媒体项目。"""
        if not self.mediadb:
            return None
        server_id = self.resolve_server_id(server_id, content_profile)
        rows = self.config_repo.get_media_servers(server_id) if self.config_repo and server_id else []
        server_type = (rows[0].TYPE or rows[0].NAME) if rows else self._server_type
        media = self.mediadb.query(
            server_type=server_type,
            title=title,
            year=year,
            tmdbid=tmdbid,
            server_id=server_id,
        )
        if not media:
            return None

        # 剧集没有季时默认为第1季
        if mtype != ProviderMediaType.MOVIE and not season:
            season = 1
        if season:
            # 匹配剧集是否存在
            seasoninfos = JsonUtils.loads(media.JSON or "[]")
            for seasoninfo in seasoninfos:
                if seasoninfo.get("season_num") == int(season) and (
                    not episode or seasoninfo.get("episode_num") == int(episode)
                ):
                    return media.ITEM_ID
            return None
        else:
            return media.ITEM_ID

    def get_mediasync_status(self, server_id: int | None = None):
        """获取指定实例的同步状态。"""
        if not self.mediadb:
            return {}
        server_id = self.resolve_server_id(server_id)
        rows = self.config_repo.get_media_servers(server_id) if self.config_repo and server_id else []
        server_type = (rows[0].TYPE or rows[0].NAME) if rows else self._server_type
        status = self.mediadb.get_statistics(server_type=server_type, server_id=server_id)
        if not status:
            return {}
        else:
            return {"movie_count": status.MOVIE_COUNT, "tv_count": status.TV_COUNT, "time": status.UPDATE_TIME}

    def get_iteminfo(self, itemid, server_id: int | None = None):
        """查询指定实例的项目详情。"""
        client = self._get_client(server_id)
        return client.get_iteminfo(itemid) if client and itemid else None

    def get_playing_sessions(self, server_id: int | None = None):
        """获取指定实例正在播放的会话。"""
        client = self._get_client(server_id)
        return client.get_playing_sessions() if client else None

    def _process_webhook(self, event_info: dict, channel: str):
        """异步处理 webhook（图片获取 + 消息发送）"""
        if not self.message:
            return
        try:
            if event_info.get("item_type") == "tv":
                image_url = self.get_episode_image_by_id(
                    item_id=event_info.get("item_id"),
                    season_id=event_info.get("season_id"),
                    episode_id=event_info.get("episode_id"),
                )
            elif event_info.get("item_type") in ["movie", "show"]:
                image_url = self.get_remote_image_by_id(item_id=event_info.get("item_id"), image_type="Backdrop")
            elif event_info.get("item_type") == "AUD":
                image_url = self.get_local_image_by_id(item_id=event_info.get("item_id"))
            else:
                image_url = None
            self.message.send_mediaserver_message(event_info=event_info, channel=channel, image_url=image_url)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("[MediaServer]webhook 异步处理异常")

    def webhook_message_handler(self, message: str, channel: str):
        """
        处理Webhook消息（快速响应，异步处理，多实例部署时通过分布式锁去重）
        """
        if not self.server:
            return
        if channel != self.server.get_type():
            return
        event_info = None
        try:
            event_info = self.server.get_webhook_message(message)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("[MediaServer]webhook 消息解析异常")
            return
        if not event_info:
            return

        # 分布式锁去重：同一事件在多实例环境下只处理一次
        event = event_info.get("event") or "unknown"
        item_id = event_info.get("item_id") or ""
        user_id = event_info.get("user_id") or ""
        timestamp = str(event_info.get("timestamp") or "")
        raw_key = f"{event}:{item_id}:{user_id}:{timestamp}"
        lock_key = f"webhook:{channel}:{hashlib.md5(raw_key.encode(), usedforsecurity=False).hexdigest()}"

        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=60)
        acquired = lock.acquire()
        if not acquired:
            log.debug(f"[MediaServer]webhook 事件已处理，跳过: {raw_key}")
            return

        try:
            self._message_queue.submit(self._process_webhook, event_info, channel, name="mediaserver_webhook")
        finally:
            lock.release()

    def get_resume(self, num=12, server_id: int | None = None):
        """获取指定实例的继续观看。"""
        client = self._get_client(server_id)
        return client.get_resume(num=num) if client else []

    def get_latest(self, num=20, server_id: int | None = None):
        """获取指定实例的最新入库。"""
        client = self._get_client(server_id)
        return client.get_latest(num=num) if client else []

    def download_image(self, url: str, server_id: int | None = None) -> bytes | None:
        if server_id is not None:
            client = self._get_client(server_id)
            return client.download_image(url) if client else None
        for cls in get_all_clients():
            server = self.__build_class(cls.client_id, None)
            if server:
                content = server.download_image(url)
                if content:
                    return content
        return None
