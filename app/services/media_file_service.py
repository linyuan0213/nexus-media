import os

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.di import container
from app.plugin_framework.event_compat import EventHandler
from app.storage import StorageBackendFactory
from app.storage.backends.base import StorageType
from app.storage.config_models import LocalStorageConfig
from app.utils import SystemUtils
from app.utils.path_utils import get_category_path
from app.utils.types import EventType, OsType


class MediaFileService:
    """
    媒体文件操作业务服务
    """

    def __init__(self):
        pass

    def get_dir_list(self, in_dir: str, backend_id: str = "") -> tuple[bool, list, str]:
        """获取目录列表，支持本地和远程存储后端"""
        result = []
        try:
            if backend_id and backend_id != "local":
                repo = container.storage_backend_repo()
                entity = repo.get_by_id(int(backend_id))
                if not entity:
                    return False, [], f"未找到存储后端: {backend_id}"
                info = StorageBackendFactory.get_config_info(entity.type)
                if info:
                    stype, cls = info
                else:
                    stype, cls = StorageType.LOCAL, LocalStorageConfig
                config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
                for k, v in entity.config.items():
                    if hasattr(config, k):
                        setattr(config, k, v)
                backend = StorageBackendFactory.create(config)
                for fi in backend.list_dir(in_dir or "/"):
                    item = {
                        "name": os.path.basename(fi.path),
                        "path": fi.path,
                        "is_dir": fi.is_dir,
                    }
                    if fi.mtime:
                        item["mtime"] = fi.mtime
                    if fi.size is not None and not fi.is_dir:
                        item["size"] = fi.size
                        item["ext"] = os.path.splitext(fi.path)[1][1:]
                    result.append(item)
                return True, result, ""

            if not in_dir or in_dir == "/":
                if SystemUtils.get_system() == OsType.WINDOWS:
                    partitions = SystemUtils.get_windows_drives()
                    if partitions:
                        for p in partitions:
                            result.append({"name": p, "path": p, "is_dir": True})
                    else:
                        for f in os.listdir("C:/"):
                            ff = os.path.join("C:/", f)
                            result.append({"name": f, "path": ff.replace("\\", "/"), "is_dir": os.path.isdir(ff)})
                else:
                    for f in os.listdir("/"):
                        ff = os.path.join("/", f)
                        result.append({"name": f, "path": ff.replace("\\", "/"), "is_dir": os.path.isdir(ff)})
            else:
                d = os.path.normpath(in_dir)
                if not os.path.isdir(d):
                    d = os.path.dirname(d)
                for f in os.listdir(d):
                    ff = os.path.join(d, f)
                    is_dir = os.path.isdir(ff)
                    item = {"name": f, "path": ff.replace("\\", "/"), "is_dir": is_dir}
                    try:
                        st = os.stat(ff)
                        item["mtime"] = st.st_mtime
                        item["ctime"] = st.st_ctime
                    except OSError:
                        item["mtime"] = None
                        item["ctime"] = None
                    if not is_dir:
                        item["ext"] = os.path.splitext(f)[1][1:]
                        try:
                            item["size"] = os.path.getsize(ff)
                        except OSError:
                            item["size"] = None
                    result.append(item)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            return False, [], str(e)
        return True, result, ""

    def get_library_paths(self, media: dict, sync_svc, downloader_svc=None) -> dict:
        """获取媒体库目录 + 同步源目录 + 同步目标目录"""

        def _make_path(path: str, label: str, ptype: str, backend_id: str = "local"):
            if not path:
                return None
            norm = path.replace("\\", "/").rstrip("/")
            name = os.path.basename(norm) or label
            return {"name": name, "path": norm, "type": ptype, "backend_id": backend_id or "local"}

        def _dedupe(paths: list, seen: set) -> list:
            result = []
            for item in paths:
                if not item:
                    continue
                norm = item["path"]
                if norm in seen:
                    continue
                seen.add(norm)
                result.append(item)
            return result

        library_paths = []
        seen_lib = set()
        movie_paths = media.get("movie_path") or []
        if not isinstance(movie_paths, list):
            movie_paths = [movie_paths] if movie_paths else []
        tv_paths = media.get("tv_path") or []
        if not isinstance(tv_paths, list):
            tv_paths = [tv_paths] if tv_paths else []
        anime_paths = media.get("anime_path") or []
        if not isinstance(anime_paths, list):
            anime_paths = [anime_paths] if anime_paths else []

        movie_backend = media.get("movie_backend") or []
        tv_backend = media.get("tv_backend") or []
        anime_backend = media.get("anime_backend") or []

        for i, p in enumerate(movie_paths):
            item = _make_path(p, "电影", "movie", movie_backend[i] if i < len(movie_backend) else "local")
            if item:
                library_paths.append(item)
        for i, p in enumerate(tv_paths):
            item = _make_path(p, "电视剧", "tv", tv_backend[i] if i < len(tv_backend) else "local")
            if item:
                library_paths.append(item)
        for i, p in enumerate(anime_paths):
            item = _make_path(p, "动漫", "anime", anime_backend[i] if i < len(anime_backend) else "local")
            if item:
                library_paths.append(item)
        library_paths = _dedupe(library_paths, seen_lib)

        sync_source_paths = []
        sync_dest_paths = []
        seen_src = set()
        seen_dst = set()
        try:
            sync_confs = sync_svc.get_sync_paths()
            if isinstance(sync_confs, dict):
                for sp in sync_confs.values():
                    if hasattr(sp, "source"):
                        src = sp.source
                        dest = getattr(sp, "dest", "")
                        src_backend = getattr(sp, "src_backend_id", "local")
                        dst_backend = getattr(sp, "dst_backend_id", "local")
                    elif isinstance(sp, dict):
                        src = sp.get("from") or sp.get("source")
                        dest = sp.get("dest") or sp.get("target") or ""
                        src_backend = sp.get("src_backend_id", "local")
                        dst_backend = sp.get("dst_backend_id", "local")
                    else:
                        src = None
                        dest = ""
                        src_backend = "local"
                        dst_backend = "local"
                    src_item = _make_path(src or "", "同步源目录", "sync", src_backend)
                    if src_item:
                        sync_source_paths.append(src_item)
                    if dest and dest != src:
                        dst_item = _make_path(dest, "同步目标目录", "sync_dest", dst_backend)
                        if dst_item:
                            sync_dest_paths.append(dst_item)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            pass
        sync_source_paths = _dedupe(sync_source_paths, seen_src)
        sync_dest_paths = _dedupe(sync_dest_paths, seen_dst)

        default_path = media.get("media_default_path")
        if not default_path:
            if library_paths:
                default_path = library_paths[0]["path"]
            elif sync_dest_paths:
                default_path = sync_dest_paths[0]["path"]
            elif sync_source_paths:
                default_path = sync_source_paths[0]["path"]
            else:
                default_path = os.path.expanduser("~").replace("\\", "/")

        return {
            "library_paths": library_paths,
            "sync_source_paths": sync_source_paths,
            "sync_dest_paths": sync_dest_paths,
            "default_path": default_path,
        }

    def download_subtitle(self, path: str, name: str) -> tuple[bool, str]:
        """下载字幕"""
        media = container.media_service().get_media_info(title=name)
        if not media or not media.tmdb_info:
            return False, f"{name} 无法从TMDB查询到媒体信息"
        if not media.imdb_id:
            media.set_tmdb_info(container.media_service().get_tmdb_info(mtype=media.type, tmdbid=media.tmdb_id))
        EventHandler.send_event(
            EventType.SubtitleDownload,
            {
                "media_info": media.to_dict(),
                "file": os.path.splitext(path)[0],
                "file_ext": os.path.splitext(name)[-1],
                "bluray": False,
            },
        )
        return True, "字幕下载任务已提交，正在后台运行。"

    def scrap_media_path(self, path: str, backend_id: str = "local") -> str:
        """刮削媒体路径，支持本地和远程后端"""
        if not path:
            return "请指定刮削路径"
        dst_backend = None
        if backend_id and backend_id != "local":
            repo = container.storage_backend_repo()
            entity = repo.get_by_id(int(backend_id))
            if entity:
                info = StorageBackendFactory.get_config_info(entity.type)
                if info:
                    stype, cls = info
                else:
                    stype, cls = StorageType.LOCAL, LocalStorageConfig
                config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
                for k, v in entity.config.items():
                    if hasattr(config, k):
                        setattr(config, k, v)
                dst_backend = StorageBackendFactory.create(config)
        container.thread_helper().start_thread(
            container.scraper().folder_scraper, (path, None, "force_all", dst_backend)
        )
        return "刮削任务已提交，正在后台运行。"

    def get_category_config(self, category_name: str) -> tuple[bool, str]:
        """获取二级分类配置"""
        if not category_name:
            return False, "请输入二级分类策略名称"
        if category_name == "config":
            return False, "非法二级分类策略名称"
        category_path = os.path.join(settings.config_path, f"{category_name}.yaml")
        if not os.path.exists(category_path):
            return False, "请保存生成配置文件"
        with open(category_path, encoding="utf-8") as f:
            return True, f.read()

    def update_category_config(self, text: str) -> str:
        """保存二级分类配置"""
        category_path = get_category_path()
        if category_path:
            with open(category_path, "w", encoding="utf-8") as f:
                f.write(text)
        return "保存成功"
