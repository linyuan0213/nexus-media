from typing import Protocol, runtime_checkable

from app.downloader.strategy import RemoveStrategy
from app.schemas.download import Torrent, TorrentStatus


@runtime_checkable
class IDownloadClient(Protocol):
    client_id: str
    client_type: str
    client_name: str

    @classmethod
    def match(cls, ctype: str) -> bool:
        ...

    def get_type(self) -> str:
        ...

    def connect(self) -> None:
        ...

    def get_status(self) -> bool:
        ...

    def get_torrents(
        self,
        ids: list[str] | str | None = None,
        status: list[TorrentStatus] | TorrentStatus | None = None,
        tag: str | list[str] | None = None,
    ) -> tuple[list[Torrent], bool]:
        ...

    def get_downloading_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        ...

    def get_completed_torrents(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[Torrent] | None:
        ...

    def get_files(self, tid: str | None = None) -> list[dict] | None:
        ...

    def set_torrents_status(self, ids: list[str] | str, tags: str | list[str] | None = None) -> bool:
        ...

    def set_torrents_tag(
        self, ids: list[str] | str | None = None, tags: str | list[str] | None = None
    ) -> bool:
        ...

    def get_transfer_task(self, tag: str | None = None, match_path: bool | None = None) -> list[dict]:
        ...

    def get_remove_torrents(self, strategy: RemoveStrategy) -> list[dict]:
        ...

    def add_torrent(self, content: str | bytes, **kwargs) -> bool:
        ...

    def start_torrents(self, ids: list[str] | str | None = None) -> bool:
        ...

    def stop_torrents(self, ids: list[str] | str | None = None) -> bool:
        ...

    def delete_torrents(self, delete_file: bool = False, ids: list[str] | str | None = None) -> bool:
        ...

    def get_download_dirs(self) -> list[str]:
        ...

    def change_torrent(self, tid: str | None = None, **kwargs) -> bool:
        ...

    def get_downloading_progress(
        self, ids: list[str] | str | None = None, tag: str | list[str] | None = None
    ) -> list[dict]:
        ...

    def set_speed_limit(
        self, download_limit: int | None = None, upload_limit: int | None = None
    ) -> bool:
        ...

    def recheck_torrents(self, ids: list[str] | str | None = None) -> bool:
        ...

    def get_free_space(self, path: str) -> int | None:
        ...
