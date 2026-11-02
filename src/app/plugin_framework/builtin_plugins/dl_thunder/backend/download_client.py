import hashlib
import os
from typing import Any
from urllib.parse import quote

import log
from app.core.exceptions import InfrastructureError, NetworkError
from app.downloader.client._base import _IDownloadClient
from app.downloader.schema import ConfigField, DownloaderConfigSchema, queue_config_fields
from app.downloader.strategy import RemoveStrategy
from app.schemas.download import Torrent, TorrentStatus

from .pythunder import PyThunder, sanitize_error_text


class Thunder(_IDownloadClient):
    client_id = "thunder"
    client_type = "thunder"
    client_name = "迅雷"
    supports_pt = False  # 迅雷不支持 PT 私有站点种子

    config_schema = DownloaderConfigSchema(
        name="迅雷",
        monitor_enable=True,
        speedlimit_enable=False,
        fields=[
            ConfigField(
                id="host",
                required=True,
                title="IP地址",
                tooltip="配置迅雷NAS设备的IP地址",
                type="text",
                placeholder="192.168.1.100",
            ),
            ConfigField(
                id="port",
                required=True,
                title="端口",
                tooltip="迅雷NAS Web管理端口，默认为2345",
                type="text",
                placeholder="2345",
                default="2345",
            ),
            ConfigField(
                id="token",
                required=False,
                title="认证令牌",
                tooltip="迅雷认证令牌，默认为Basic认证，格式为Basic base64(username:password)",
                type="text",
                placeholder="Basic bGlueXVhbjIxMzpMeTE5OTYwMjEzKio=",
            ),
            *queue_config_fields("nexus", 5),
        ],
    )

    _client_config: dict = {}
    _client = None
    host = None
    port = None
    token = None
    download_dir: list = []
    _recreated_tasks: dict[str, str] = {}

    def __init__(self, config: dict | None = None):
        if config:
            self._client_config = config
        self.init_config()
        self.connect()

    def init_config(self) -> None:
        if self._client_config:
            self.host = self._client_config.get("host")
            self.port = self._client_config.get("port")
            self.token = self._client_config.get("token")
            self.download_dir = self._client_config.get("download_dir") or []
            if self.host and self.port:
                self._client = PyThunder(host=self.host, port=self.port, token=self.token)

    def connect(self) -> None:
        pass

    def _ensure_connected(self) -> bool:
        """客户端缺失时按配置重建；配置缺失则重建后仍为空，返回 False."""
        if self._client:
            return True
        self.init_config()
        return bool(self._client)

    def get_status(self) -> bool:
        if not self._client:
            return False
        try:
            device_id = self._client.get_device_id()
            return bool(device_id)
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]连接测试失败: {e!s}")
            return False

    def get_torrents(
        self, ids: list[str] | str | None = None, status: Any = None, tag: str | list[str] | None = None
    ) -> tuple[list[Torrent], bool]:
        if not self._client:
            return [], True
        try:
            if status == "downloading":
                tasks = self._client.get_downloading_tasks()
            elif status == "completed":
                tasks = self._client.get_complete_tasks()
            else:
                downloading_tasks = self._client.get_downloading_tasks()
                complete_tasks = self._client.get_complete_tasks()
                tasks = downloading_tasks + complete_tasks

            torrent_list: list[Torrent] = []
            for task in tasks:
                torrent = self._task_to_torrent(task)
                if torrent:
                    torrent_list.append(torrent)
            return torrent_list, False
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]获取任务列表失败: {e!s}")
            return [], True

    def get_downloading_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        statuses = [
            TorrentStatus.Downloading,
            TorrentStatus.Paused,
            TorrentStatus.Queued,
            TorrentStatus.Checking,
            TorrentStatus.Pending,
        ]
        torrents, error = self.get_torrents(ids=ids, status=statuses, tag=tag)
        torrents = [t for t in torrents if t.progress * 100 < 100]
        return None if error else torrents

    def get_completed_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        torrents, error = self.get_torrents(status="completed")
        return None if error else torrents

    def _normalize_files(self, raw_files: list[dict]) -> list[dict]:
        return raw_files

    def _resolve_tid(self, tid: str | None) -> str | None:
        if tid and tid in self._recreated_tasks:
            return self._recreated_tasks[tid]
        return tid

    def _get_task_by_id(self, tid: str) -> dict | None:
        if not self._client:
            return None
        try:
            tasks = self._client.get_downloading_tasks(limit=1000) + self._client.get_complete_tasks(limit=1000)
            for task in tasks:
                if task.get("id") == tid:
                    return task
        except Exception as e:
            log.error(f"[{self.client_name}]查找任务失败: {e!s}")
        return None

    def get_files(self, tid: str | None = None) -> list[dict] | None:
        if not self._client or not tid:
            return None
        try:
            task = self._get_task_by_id(tid)
            if not task:
                return None
            params = task.get("params", {})
            download_url = params.get("url", "")
            if not download_url:
                return None
            torrent_info = self._client.get_torrent_info(download_url, extract_info=True)
            if not torrent_info or "files" not in torrent_info:
                return None
            return [
                {
                    "id": f.get("file_index", 0),
                    "name": f.get("name", ""),
                    "size": f.get("size_bytes", 0),
                }
                for f in torrent_info["files"]
            ]
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]获取文件列表失败: {e!s}")
            return None

    def set_file_selection(self, tid: str | None, selected_map: dict[int, bool]) -> bool:
        if not self._client or not tid:
            return True
        try:
            task = self._get_task_by_id(tid)
            if not task:
                return False
            params = task.get("params", {})
            download_url = params.get("url", "")
            save_path = params.get("parent_folder_path", "/downloads/xunlei/")
            if not download_url:
                return False

            selected_indices = [str(fid) for fid, selected in selected_map.items() if selected]
            if not selected_indices:
                return False
            file_indices = ",".join(selected_indices)

            self._client.delete_task(tid, delete_files=False)

            folder_id = self._client._resolve_folder_id(save_path)
            task_info = self._client.download(
                download_urls=download_url,
                destination_path=save_path,
                parent_folder_id=folder_id,
                file_indices=file_indices,
            )
            new_tid = task_info.get("id") if task_info else None
            if new_tid:
                self._recreated_tasks[tid] = str(new_tid)
                log.info(f"[{self.client_name}]任务 {tid} 已拆包重建为 {new_tid}，选中文件: {file_indices}")
                return True
            return False
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]设置文件选择失败: {e!s}")
            return False

    def set_torrents_status(self, ids: list[str] | str, tags: str | list[str] | None = None) -> bool:
        return True

    def set_torrents_tag(self, ids: list[str] | str | None = None, tags: str | list[str] | None = None) -> bool:
        return True

    def get_remove_torrents(self, strategy: RemoveStrategy) -> list[dict]:
        return []

    @staticmethod
    def _bdecode(data: bytes, index: int = 0):
        """最小 bencode 解析；返回 (value, next_index)."""
        marker = data[index : index + 1]
        if marker == b"i":
            end = data.index(b"e", index)
            return int(data[index + 1 : end]), end + 1
        if marker == b"l":
            result = []
            index += 1
            while data[index : index + 1] != b"e":
                value, index = Thunder._bdecode(data, index)
                result.append(value)
            return result, index + 1
        if marker == b"d":
            result = {}
            index += 1
            while data[index : index + 1] != b"e":
                key, index = Thunder._bdecode(data, index)
                value, index = Thunder._bdecode(data, index)
                result[key] = value
            return result, index + 1
        colon = data.index(b":", index)
        length = int(data[index:colon])
        start = colon + 1
        return data[start : start + length], start + length

    @classmethod
    def _torrent_bytes_to_magnet(cls, content: bytes) -> str | None:
        """本地解析 torrent，计算 info_hash 生成磁力；迅雷只接收磁力链接."""
        if not content or content[:1] != b"d":
            return None
        try:
            root, _ = cls._bdecode(content)
            info_marker = content.index(b"4:info")
            info_start = info_marker + len(b"4:info")
            _, info_end = cls._bdecode(content, info_start)
            info_hash = hashlib.sha1(content[info_start:info_end]).hexdigest()
            info = root.get(b"info") or {}
            name = info.get(b"name") if isinstance(info, dict) else None
            name_text = name.decode("utf-8", errors="ignore") if isinstance(name, bytes) else ""
            trackers: list[str] = []
            announce = root.get(b"announce")
            if isinstance(announce, bytes):
                trackers.append(announce.decode("utf-8", errors="ignore"))
            announce_list = root.get(b"announce-list")
            if isinstance(announce_list, list):
                for tier in announce_list:
                    if isinstance(tier, list):
                        for tracker in tier:
                            if isinstance(tracker, bytes):
                                trackers.append(tracker.decode("utf-8", errors="ignore"))
            parts = [f"magnet:?xt=urn:btih:{info_hash}"]
            if name_text:
                parts.append(f"dn={quote(name_text, safe='')}")
            for tracker in dict.fromkeys(trackers):
                if tracker:
                    parts.append(f"tr={quote(tracker, safe='')}")
            return "&".join(parts)
        except Exception as e:  # noqa: BLE001
            log.error(f"[{cls.client_name}]本地解析种子失败: {sanitize_error_text(e)}")
            return None

    @classmethod
    def _select_media_file_indices(cls, content: bytes) -> str:
        """选择视频文件，排除 .url/.txt 和远小于主视频的广告 MP4."""
        if not content or content[:1] != b"d":
            return ""
        try:
            root, _ = cls._bdecode(content)
            info = root.get(b"info") or {}
            files = info.get(b"files") if isinstance(info, dict) else None
            if not isinstance(files, list) or not files:
                return ""
            media = {".mp4", ".mkv", ".avi", ".wmv", ".ts", ".m2ts", ".mov", ".flv", ".webm"}
            candidates: list[tuple[int, str, int]] = []
            for index, item in enumerate(files):
                if not isinstance(item, dict):
                    continue
                path = item.get(b"path")
                if not isinstance(path, list) or not path:
                    continue
                name = "/".join(str(part, "utf-8", "ignore") if isinstance(part, bytes) else str(part) for part in path)
                ext = os.path.splitext(name)[1].lower()
                size = int(item.get(b"length") or 0)
                if ext in media and size > 0:
                    candidates.append((index, name, size))
            if not candidates:
                return ""
            largest = max(size for _, _, size in candidates)
            selected = [index for index, _, size in candidates if size >= largest * 0.1]
            return ",".join(str(index) for index in selected)
        except Exception:
            return ""

    def add_torrent(self, content: str | bytes, **kwargs) -> bool:
        result = self.add_torrent_and_get_id(content, **kwargs)
        return result is not None and result != ""

    def add_torrent_and_get_id(
        self,
        content: Any,
        is_paused: bool = False,
        download_dir: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        upload_limit: int | None = None,
        download_limit: int | None = None,
        ratio_limit: float | None = None,
        seeding_time_limit: int | None = None,
        cookie: str | None = None,
        **kwargs: Any,
    ) -> str | None:
        self._set_last_add_error("")
        if not self._ensure_connected() or not self._client:
            self._set_last_add_error("迅雷未连接或连接配置无效")
            return None
        try:
            # 插件调用链可能把 bytes 序列化成 list/bytearray/dict；先统一还原。
            if isinstance(content, memoryview):
                content = content.tobytes()
            elif isinstance(content, bytearray):
                content = bytes(content)
            elif isinstance(content, (list, tuple)) and all(
                isinstance(item, int) and 0 <= item <= 255 for item in content
            ):
                content = bytes([int(item) for item in content])
            elif isinstance(content, dict):
                for key in ("content", "data", "torrent", "bytes", "body"):
                    value = content.get(key)
                    if isinstance(value, memoryview):
                        content = value.tobytes()
                        break
                    if isinstance(value, bytearray):
                        content = bytes(value)
                        break
                    if isinstance(value, (bytes, str)):
                        content = value
                        break
            elif not isinstance(content, (str, bytes)):
                attr = getattr(content, "content", None)
                if isinstance(attr, (bytes, bytearray, memoryview)):
                    content = bytes(attr)
            if isinstance(content, bytes):
                log.debug(f"[{self.client_name}]add_torrent 收到二进制种子: {len(content)} bytes")
            else:
                log.debug(f"[{self.client_name}]add_torrent 内容类型: {type(content).__name__}")
            if isinstance(content, bytes):
                # 下载流水线会把 .torrent 读成 bytes；迅雷只接受磁力/种子路径，
                # 这里落临时文件转磁力，转换后立即删除。
                if content.startswith(b"magnet:"):
                    download_url = content.decode("utf-8", errors="ignore")
                else:
                    download_url = self._torrent_bytes_to_magnet(content)
                    if not download_url:
                        self._set_last_add_error("二进制种子无法转换为磁力链接")
                        return None
            elif isinstance(content, str):
                if content.startswith("magnet:"):
                    download_url = content
                elif content.endswith(".torrent") or os.path.exists(content):
                    try:
                        with open(content, "rb") as handle:
                            torrent_data = handle.read()
                    except OSError:
                        self._set_last_add_error(f"种子文件不存在或无法读取：{content}")
                        return None
                    magnet_url = self._torrent_bytes_to_magnet(torrent_data)
                    if not magnet_url:
                        log.error(f"[{self.client_name}]种子文件转换磁力链接失败")
                        self._set_last_add_error("种子文件无法转换为磁力链接")
                        return None
                    download_url = magnet_url
                else:
                    download_url = content
            else:
                self._set_last_add_error(f"迅雷下载器收到不支持的种子内容类型：{type(content).__name__}")
                return None

            folder_id = self._client._resolve_folder_id(download_dir or "/downloads/xunlei/")
            file_indices = kwargs.get("file_indices")
            file_names = kwargs.get("file_names")
            if isinstance(content, bytes) and not file_indices:
                file_indices = self._select_media_file_indices(content) or None
                if file_indices:
                    log.info(f"[{self.client_name}]选择视频文件索引: {file_indices}")
            task_info = self._client.download(
                download_urls=download_url,
                destination_path=download_dir or "/downloads/xunlei/",
                parent_folder_id=folder_id,
                file_indices=file_indices,
                file_names=file_names,
            )
            task_id = task_info.get("id") if task_info else None
            if not task_id:
                self._set_last_add_error("迅雷未返回任务 ID（可能重复任务、保存路径无效或空间不足）")
                return None
            return str(task_id)
        except (InfrastructureError, NetworkError) as e:
            self._set_last_add_error(sanitize_error_text(e))
            raise
        except Exception as e:
            reason = sanitize_error_text(e) or "未知错误"
            self._set_last_add_error(reason)
            log.error(f"[{self.client_name}]添加下载任务失败: {reason}")
            return None

    def start_torrents(self, ids: list[str] | str | None = None) -> bool:
        if not self._client:
            return False
        try:
            if ids is None:
                return False
            if not isinstance(ids, list):
                ids = [ids]
            success = True
            for task_id in ids:
                resolved = self._resolve_tid(task_id)
                result = self._client.resume_task(str(resolved))
                if not result:
                    success = False
            return success
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]启动任务失败: {e!s}")
            return False

    def stop_torrents(self, ids: list[str] | str | None = None) -> bool:
        if not self._client:
            return False
        try:
            if ids is None:
                return False
            if not isinstance(ids, list):
                ids = [ids]
            success = True
            for task_id in ids:
                resolved = self._resolve_tid(task_id)
                result = self._client.pause_task(str(resolved))
                if not result:
                    success = False
            return success
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]暂停任务失败: {e!s}")
            return False

    def delete_torrents(self, delete_file: bool = False, ids: list[str] | str | None = None) -> bool:
        if not self._client:
            return False
        try:
            if ids is None:
                return False
            if not isinstance(ids, list):
                ids = [ids]
            success = True
            for task_id in ids:
                resolved = self._resolve_tid(task_id)
                result = self._client.delete_task(str(resolved), delete_files=bool(delete_file))
                if not result:
                    success = False
            return success
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]删除任务失败: {e!s}")
            return False

    def get_download_dirs(self) -> list[str]:
        return self.download_dir

    def change_torrent(self, tid: str | None = None, **kwargs: Any) -> bool:
        return True

    def set_speed_limit(self, download_limit: int | None = None, upload_limit: int | None = None) -> bool:
        return True

    def recheck_torrents(self, ids: list[str] | str | None = None) -> bool:
        return True

    def get_free_space(self, path: str) -> int | None:
        return 0

    def _map_status(self, raw_state: str) -> TorrentStatus:
        mapping = {
            "PHASE_TYPE_COMPLETE": TorrentStatus.Uploading,
            "PHASE_TYPE_RUNNING": TorrentStatus.Downloading,
            "PHASE_TYPE_PENDING": TorrentStatus.Downloading,
            "PHASE_TYPE_PAUSED": TorrentStatus.Stopped,
            "PHASE_TYPE_ERROR": TorrentStatus.Error,
        }
        return mapping.get(raw_state, TorrentStatus.Unknown)

    @property
    def _supported_statuses(self) -> list[TorrentStatus]:
        return [
            TorrentStatus.Downloading,
            TorrentStatus.Uploading,
            TorrentStatus.Stopped,
            TorrentStatus.Error,
            TorrentStatus.Unknown,
        ]

    def _task_to_torrent(self, task: dict[str, Any]) -> Torrent | None:
        try:
            torrent = Torrent()
            torrent.id = task.get("id", "")
            torrent.name = task.get("name", "")
            file_size = task.get("file_size", 0)
            if isinstance(file_size, str):
                try:
                    torrent.size = int(file_size)
                except ValueError:
                    torrent.size = 0
            else:
                torrent.size = file_size

            phase = task.get("phase", "")
            progress = task.get("progress", 0)
            if isinstance(progress, (int, float)):
                torrent.progress = round(progress / 100.0, 2)
            else:
                torrent.progress = 0.0

            if phase == "PHASE_TYPE_COMPLETE":
                torrent.status = TorrentStatus.Uploading
                torrent.downloaded = torrent.size
                torrent.progress = 1.0
            elif phase in ["PHASE_TYPE_RUNNING", "PHASE_TYPE_PENDING"]:
                torrent.status = TorrentStatus.Downloading
                torrent.downloaded = int(torrent.size * torrent.progress)
            elif phase == "PHASE_TYPE_PAUSED":
                torrent.status = TorrentStatus.Stopped
            elif phase == "PHASE_TYPE_ERROR":
                torrent.status = TorrentStatus.Error
            else:
                torrent.status = TorrentStatus.Unknown

            params = task.get("params", {})
            speed_str = params.get("speed", "0")
            try:
                torrent.download_speed = int(float(speed_str))
            except (ValueError, TypeError):
                torrent.download_speed = 0

            torrent.upload_speed = 0
            torrent.save_path = params.get("parent_folder_path", "")
            return torrent
        except (InfrastructureError, NetworkError):
            raise
        except Exception as e:
            log.error(f"[{self.client_name}]转换任务信息失败: {e!s}")
            return None
