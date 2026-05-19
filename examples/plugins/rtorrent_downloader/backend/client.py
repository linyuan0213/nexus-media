"""
rTorrent 下载器客户端实现

通过 XML-RPC 与 rTorrent/ruTorrent 通信。
支持 SCGI 和 HTTP XML-RPC 协议。
"""

import socket
import urllib.parse
from typing import Any
from xmlrpc.client import ServerProxy, Transport, loads

import log
from app.downloader.client._base import _IDownloadClient
from app.downloader.schema import ConfigField, DownloaderConfigSchema
from app.schemas.download import Torrent, TorrentStatus
from app.utils import ExceptionUtils


class SCGITransport(Transport):
    """SCGI Transport for XML-RPC"""

    def request(  # type: ignore[override]
        self, host: str, handler: str, request_body: bytes, verbose: bool = False
    ) -> Any:
        parsed = urllib.parse.urlparse(host)
        if parsed.scheme == "scgi":
            addr = parsed.hostname or "localhost"
            port = parsed.port or 5000
            sock = socket.create_connection((addr, port))
        else:
            raise ValueError(f"Unsupported SCGI URL: {host}")

        headers = [
            b"CONTENT_LENGTH",
            str(len(request_body)).encode(),
            b"SCGI",
            b"1",
        ]
        header_bytes = b"\x00".join(headers) + b"\x00"
        netstring = str(len(header_bytes)).encode() + b":" + header_bytes + b","

        sock.sendall(netstring + request_body)
        response = sock.makefile("rb").read()
        sock.close()

        # Parse HTTP-like response
        header_end = response.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = response.find(b"\n\n")
        body = response[header_end + 4 :]

        return loads(body)[0][0]


class Rtorrent(_IDownloadClient):
    client_id = "rtorrent"
    client_type = "rtorrent"
    client_name = "rTorrent"

    config_schema = DownloaderConfigSchema(
        name="rTorrent",
        icon_url="/api/plugin-framework/plugins/rtorrent_downloader/assets/static/icon.png",
        monitor_enable=True,
        speedlimit_enable=False,
        fields=[
            ConfigField(
                id="host",
                required=True,
                title="地址",
                tooltip="rTorrent XML-RPC 地址，支持 http:// 或 scgi://",
                type="text",
                placeholder="http://127.0.0.1:8080/RPC2",
            ),
            ConfigField(
                id="username",
                required=False,
                title="用户名",
                type="text",
                placeholder="admin",
            ),
            ConfigField(
                id="password",
                required=False,
                title="密码",
                type="password",
                placeholder="password",
            ),
        ],
    )

    _client_config: dict = {}
    _client = None
    host = None
    username = None
    password = None
    download_dir: list = []

    def __init__(self, config: dict | None = None):
        if config:
            self._client_config = config
        self.init_config()
        self.connect()

    def init_config(self) -> None:
        if self._client_config:
            self.host = self._client_config.get("host", "")
            self.username = self._client_config.get("username", "")
            self.password = self._client_config.get("password", "")
            self.download_dir = self._client_config.get("download_dir") or []
            self.name = self._client_config.get("name", "")

    def connect(self) -> None:
        if not self.host:
            return
        try:
            if self.host.startswith("scgi://"):
                self._client = ServerProxy(self.host, transport=SCGITransport())
            else:
                if self.username and self.password:
                    parsed = urllib.parse.urlparse(self.host)
                    netloc = (
                        f"{urllib.parse.quote(self.username)}:{urllib.parse.quote(self.password)}@{parsed.hostname}"
                    )
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    url = urllib.parse.urlunparse((
                        parsed.scheme,
                        netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    ))
                    self._client = ServerProxy(url)
                else:
                    self._client = ServerProxy(self.host)
        except Exception as e:
            log.error(f"【{self.client_name}】连接失败: {e}")
            self._client = None

    def get_status(self) -> bool:
        if not self._client:
            return False
        try:
            result = self._client.system.client_version()
            return bool(result)
        except Exception:
            return False

    def get_torrents(
        self,
        ids: list[str] | str | None = None,
        status: Any = None,
        tag: str | list[str] | None = None,
    ) -> tuple[list[Torrent], bool]:
        if not self._client:
            return [], True
        try:
            fields = [
                "d.hash=",
                "d.name=",
                "d.size_bytes=",
                "d.completed_bytes=",
                "d.ratio=",
                "d.up.rate=",
                "d.down.rate=",
                "d.is_open=",
                "d.is_active=",
                "d.is_hash_checking=",
                "d.state=",
                "d.complete=",
                "d.directory=",
                "d.custom1=",
                "d.creation_date=",
                "d.tracker_size=",
            ]

            # Get all torrents
            raw_list: list[Any] = self._client.d.multicall2("", "main", *fields)  # type: ignore[assignment]

            torrent_list: list[Torrent] = []
            for raw in raw_list:
                if not raw or len(raw) < len(fields):
                    continue
                torrent = self._parse_torrent(raw)
                if ids:
                    id_list = ids if isinstance(ids, list) else [ids]
                    if torrent.id not in id_list:
                        continue
                if status:
                    if isinstance(status, list):
                        if torrent.status not in status:
                            continue
                    elif torrent.status != status:
                        continue
                if tag:
                    tag_list = tag if isinstance(tag, list) else [tag]
                    labels = torrent.labels or []
                    if not any(t in labels for t in tag_list):
                        continue
                torrent_list.append(torrent)
            return torrent_list, False
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return [], True

    def _parse_torrent(self, raw: list) -> Torrent:
        t = Torrent()
        t.id = raw[0]  # hash
        t.name = raw[1] or ""
        t.size = int(raw[2] or 0)
        t.downloaded = int(raw[3] or 0)
        t.ratio = round(float(raw[4] or 0) / 1000, 2)
        t.upload_speed = int(raw[5] or 0)
        t.download_speed = int(raw[6] or 0)
        is_open = int(raw[7] or 0)
        is_active = int(raw[8] or 0)
        is_hash_checking = int(raw[9] or 0)
        state = int(raw[10] or 0)
        complete = int(raw[11] or 0)
        t.save_path = raw[12] or ""
        t.labels = [raw[13]] if raw[13] else []
        t.progress = round(t.downloaded / t.size, 2) if t.size else 0.0

        t.status = self._map_status_from_flags(is_open, is_active, is_hash_checking, state, complete)
        return t

    @staticmethod
    def _map_status_from_flags(
        is_open: int, is_active: int, is_hash_checking: int, state: int, complete: int
    ) -> TorrentStatus:
        if is_hash_checking:
            return TorrentStatus.Checking
        if not is_open:
            return TorrentStatus.Stopped
        if is_active:
            if complete:
                return TorrentStatus.Uploading
            return TorrentStatus.Downloading
        if state == 0:
            return TorrentStatus.Paused
        return TorrentStatus.Unknown

    def get_downloading_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        torrents, error = self.get_torrents(
            ids=ids,
            status=[TorrentStatus.Downloading, TorrentStatus.Checking, TorrentStatus.Queued],
            tag=tag,
        )
        return None if error else torrents

    def get_completed_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        torrents, error = self.get_torrents(
            ids=ids, status=[TorrentStatus.Uploading, TorrentStatus.Paused, TorrentStatus.Stopped], tag=tag
        )
        return None if error else torrents

    def get_files(self, tid: str | None = None) -> list[dict] | None:
        if not self._client or not tid:
            return None
        try:
            files: list[Any] = self._client.f.multicall(tid, "", "f.path=", "f.size_bytes=", "f.completed_chunks=")  # type: ignore[assignment]
            return [
                {
                    "path": f[0],
                    "size": f[1],
                    "completed": f[2],
                }
                for f in files
            ]
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return None

    def set_torrents_status(self, ids: list[str] | str, tags: str | list[str] | None = None) -> bool:
        return self.set_torrents_tag(ids=ids, tags="已整理")

    def set_torrents_tag(self, ids: list[str] | str | None = None, tags: str | list[str] | None = None) -> bool:
        if not self._client or not ids:
            return False
        try:
            id_list = ids if isinstance(ids, list) else [ids]
            tag_str = tags if isinstance(tags, str) else ";".join(tags or [])
            for tid in id_list:
                self._client.d.custom1.set(tid, tag_str)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def add_torrent(self, content: str | bytes, **kwargs) -> bool:
        if not self._client:
            return False
        try:
            download_dir = kwargs.get("download_dir", "")
            if isinstance(content, str):
                if content.startswith("magnet:"):
                    if download_dir:
                        self._client.load.start("", content, f'd.directory.set="{download_dir}"')
                    else:
                        self._client.load.start("", content)
                else:
                    # URL to torrent file
                    if download_dir:
                        self._client.load.start("", content, f'd.directory.set="{download_dir}"')
                    else:
                        self._client.load.start("", content)
            else:
                # Binary content - use load.raw
                import base64

                b64 = base64.b64encode(content).decode()
                if download_dir:
                    self._client.load.raw_start("", b64, f'd.directory.set="{download_dir}"')
                else:
                    self._client.load.raw_start("", b64)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def start_torrents(self, ids: list[str] | str | None = None) -> bool:
        if not self._client or not ids:
            return False
        try:
            id_list = ids if isinstance(ids, list) else [ids]
            for tid in id_list:
                self._client.d.start(tid)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def stop_torrents(self, ids: list[str] | str | None = None) -> bool:
        if not self._client or not ids:
            return False
        try:
            id_list = ids if isinstance(ids, list) else [ids]
            for tid in id_list:
                self._client.d.stop(tid)
                self._client.d.close(tid)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def delete_torrents(self, delete_file: bool = False, ids: list[str] | str | None = None) -> bool:
        if not self._client or not ids:
            return False
        try:
            id_list = ids if isinstance(ids, list) else [ids]
            for tid in id_list:
                if delete_file:
                    self._client.d.erase(tid)
                else:
                    self._client.d.erase(tid)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def get_download_dirs(self) -> list[str]:
        return []

    def change_torrent(self, tid: str | None = None, **kwargs: Any) -> bool:
        if not self._client or not tid:
            return False
        try:
            if "save_path" in kwargs:
                self._client.d.directory.set(tid, kwargs["save_path"])
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def set_speed_limit(self, download_limit: int | None = None, upload_limit: int | None = None) -> bool:
        return True

    def recheck_torrents(self, ids: list[str] | str | None = None) -> bool:
        if not self._client or not ids:
            return False
        try:
            id_list = ids if isinstance(ids, list) else [ids]
            for tid in id_list:
                self._client.d.check_hash(tid)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def get_free_space(self, path: str) -> int | None:
        return None

    def _map_status(self, raw_state: Any) -> TorrentStatus:
        return TorrentStatus.Unknown

    @property
    def _supported_statuses(self) -> list[TorrentStatus]:
        return [
            TorrentStatus.Downloading,
            TorrentStatus.Uploading,
            TorrentStatus.Checking,
            TorrentStatus.Paused,
            TorrentStatus.Stopped,
            TorrentStatus.Unknown,
        ]
