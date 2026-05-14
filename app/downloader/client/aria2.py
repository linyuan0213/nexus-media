import os
import re
from typing import Any

import log
from app.downloader.client._base import _IDownloadClient
from app.downloader.client._pyaria2 import PyAria2
from app.schemas.download import Torrent, TorrentStatus
from app.utils import ExceptionUtils, RequestUtils, StringUtils
from app.utils.types import DownloaderType


class Aria2(_IDownloadClient):
    schema = "aria2"
    # 下载器ID
    client_id = "aria2"
    client_type = DownloaderType.ARIA2
    client_name = DownloaderType.ARIA2.value
    _client_config = {}

    _client = None
    host = None
    port = None
    secret = None
    download_dir = []

    def __init__(self, config: dict | None = None):
        if config:
            self._client_config = config
        self.init_config()
        self.connect()

    def init_config(self) -> None:
        if self._client_config:
            self.host = self._client_config.get("host")
            if self.host:
                if not self.host.startswith("http"):
                    self.host = "http://" + self.host
                if self.host.endswith("/"):
                    self.host = self.host[:-1]
            self.port = self._client_config.get("port")
            self.secret = self._client_config.get("secret")
            self.download_dir = self._client_config.get("download_dir") or []
            if self.host and self.port:
                self._client = PyAria2(secret=self.secret, host=self.host, port=self.port)

    @classmethod
    def match(cls, ctype: str) -> Any:
        return ctype in [cls.client_id, cls.client_type, cls.client_name]

    def connect(self) -> Any:
        pass

    def get_status(self) -> Any:
        if not self._client:
            return False
        ver = self._client.getVersion()
        return bool(ver)

    def get_torrents(self, ids: list[str] | str | None = None, status: str | None = None, **kwargs: Any) -> Any:
        if not self._client:
            return []
        ret_torrents = []
        torrent_list: list[Torrent] = []
        if ids:
            if isinstance(ids, list):
                for gid in ids:
                    ret_torrents.append(self._client.tellStatus(gid=gid))
            else:
                ret_torrents = [self._client.tellStatus(gid=ids)]
        elif status:
            if status == "downloading":
                ret_torrents = self._client.tellActive() or [] + self._client.tellWaiting(offset=-1, num=100) or []
            else:
                ret_torrents = self._client.tellStopped(offset=-1, num=1000)
        for torrent in ret_torrents:
            torrent_list.append(self.torrent_properties(torrent=torrent))
        return torrent_list

    def get_downloading_torrents(self, ids: Any = None, tag: Any = None, **kwargs: Any) -> Any:
        return self.get_torrents(status="downloading")

    def get_completed_torrents(self, ids: Any = None, tag: Any = None, **kwargs: Any) -> Any:
        return self.get_torrents(status="completed")

    def set_torrents_status(self, ids: list[str] | str, **kwargs: Any) -> Any:
        return self.delete_torrents(ids=ids, delete_file=False)

    def get_transfer_task(self, tag: str | None = None, match_path: bool = False) -> Any:
        if not self._client:
            return []
        torrents = self.get_completed_torrents()
        trans_tasks = []
        for torrent in torrents:
            name = torrent.name
            if not name:
                continue
            path = torrent.save_path
            if not path:
                continue
            true_path, replace_flag = self.get_replace_path(path, self.download_dir)
            # 开启目录隔离，未进行目录替换的不处理
            if match_path and not replace_flag:
                log.debug(f"【{self.client_name}】{self.name} 开启目录隔离，但 {torrent.name} 未匹配下载目录范围")
                continue
            trans_tasks.append({"path": os.path.join(true_path, name).replace("\\", "/"), "id": torrent.id})
        return trans_tasks

    def get_remove_torrents(self, **kwargs: Any) -> Any:
        return []

    def add_torrent(self, content: str | bytes, download_dir: str | None = None, **kwargs: Any) -> Any:
        if not self._client:
            return None
        if isinstance(content, str):
            # 转换为磁力链
            if re.match("^https*://", content):
                try:
                    p = RequestUtils().get_res(url=content, allow_redirects=False)
                    if p and p.headers.get("Location"):
                        content = p.headers.get("Location")
                except Exception as result:
                    ExceptionUtils.exception_traceback(result)
            return self._client.addUri(uris=[content], options={"dir": download_dir})
        else:
            return self._client.addTorrent(torrent=content, uris=[], options={"dir": download_dir})

    def start_torrents(self, ids: list[str] | str) -> Any:
        if not self._client:
            return False
        return self._client.unpause(gid=ids)

    def stop_torrents(self, ids: list[str] | str) -> Any:
        if not self._client:
            return False
        return self._client.pause(gid=ids)

    def delete_torrents(self, delete_file: bool, ids: list[str] | str) -> Any:
        if not self._client:
            return False
        return self._client.forceRemove(gid=ids)

    def get_download_dirs(self) -> Any:
        return []

    def change_torrent(self, **kwargs: Any) -> Any:
        pass

    def get_downloading_progress(self, **kwargs: Any) -> Any:
        """
        获取正在下载的种子进度
        """
        torrents = self.get_downloading_torrents()
        disp_torrents = []
        for torrent in torrents:
            # 进度
            try:
                progress = torrent.progress * 100
            except ZeroDivisionError:
                progress = 0.0
            if torrent.status in [TorrentStatus.Stopped]:
                state = "Stopped"
                speed = "已暂停"
            else:
                state = "Downloading"
                _dlspeed = StringUtils.str_filesize(torrent.download_speed)
                _upspeed = StringUtils.str_filesize(torrent.upload_speed)
                speed = f"{chr(8595)}{_dlspeed}B/s {chr(8593)}{_upspeed}B/s"

            disp_torrents.append(
                {"id": torrent.id, "name": torrent.name, "speed": speed, "state": state, "progress": progress}
            )

        return disp_torrents

    def set_speed_limit(self, download_limit: int | None = None, upload_limit: int | None = None) -> Any:
        """
        设置速度限制
        :param download_limit: 下载速度限制，单位KB/s
        :param upload_limit: 上传速度限制，单位kB/s
        """
        if not self._client:
            return
        download_limit = download_limit * 1024
        upload_limit = upload_limit * 1024
        try:
            speed_opt = self._client.getGlobalOption()
            if speed_opt["max-overall-upload-limit"] != upload_limit:
                speed_opt["max-overall-upload-limit"] = upload_limit
            if speed_opt["max-overall-download-limit"] != download_limit:
                speed_opt["max-overall-download-limit"] = download_limit
            return self._client.changeGlobalOption(speed_opt)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def get_type(self) -> Any:
        return self.client_type

    def get_files(self, tid: str) -> Any:
        if not self._client:
            return None
        try:
            return self._client.getFiles(gid=tid)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None

    def recheck_torrents(self, ids: list[str] | str) -> Any:
        pass

    def set_torrents_tag(self, ids: list[str] | str, tags: str | list[str]) -> Any:
        pass

    def get_free_space(self, path: str) -> Any:
        pass

    def torrent_properties(self, torrent: dict) -> Torrent:

        torrent_obj = Torrent()
        torrent_obj.id = torrent.get("gid")
        torrent_obj.name = torrent.get("bittorrent", {}).get("info", {}).get("name")
        # 种子大小
        torrent_obj.size = int(torrent.get("totalLength"))
        # 下载量
        torrent_obj.downloaded = int(torrent.get("completedLength"))
        # 状态
        torrent_obj.status = Aria2._judge_status(torrent.get("status"))
        # 下载速度
        torrent_obj.download_speed = torrent.get("downloadSpeed")
        # 上传速度
        torrent_obj.upload_speed = torrent.get("uploadSpeed")
        # 下载进度
        torrent_obj.progress = round(int(torrent.get("completedLength")) / int(torrent.get("totalLength")), 1)
        # 保存路径
        torrent_obj.save_path = torrent.get("dir")

        return torrent_obj

    @staticmethod
    def _judge_status(state: str) -> TorrentStatus:
        state_mapping = {
            "paused": TorrentStatus.Stopped,
            "downloading": TorrentStatus.Downloading,
            "completed": TorrentStatus.Uploading,
            "UNKNOWN": TorrentStatus.Unknown,
        }
        return state_mapping.get(state, TorrentStatus.Unknown)
