"""批量重命名计划生成测试."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from app.domain.media_types import ProviderMediaType
from app.services.transfer.library_rename_metadata import LibraryMetadataResolver
from app.services.transfer.library_rename_models import RenameScope
from app.services.transfer.library_rename_planner import LibraryRenamePlanner
from app.storage.backends.base import FileInfo, StorageBackend


class _FakeMediaConfig:
    def __init__(self, root: str):
        self.root = root

    def get_config(self):
        return {
            "movie_path": [self.root],
            "tv_path": [],
            "anime_path": [],
            "movie_backend": ["local"],
            "tv_backend": [],
            "anime_backend": [],
        }


class _FakeRepo:
    def get_history_by_dest(self, *_args):
        return []

    def get_metadata(self, *_args):
        return None


class _FakeDownloadRepo:
    def get_by_path(self, *_args):
        return None

    def get_by_title(self, *_args):
        return []


class _FakeCategoryRepo:
    def get_all(self):
        return []


class _FakeStorageRepo:
    def get_by_id(self, _sid):
        return None


class _FakeMediaServer:
    def get_libraries(self):
        return []


class _FakeResolver:
    _movie_dir_rmt_format = "{title} ({year})"
    _movie_file_rmt_format = "{title} ({year})"
    _tv_dir_rmt_format = "{title} ({year})"
    _tv_season_rmt_format = "Season {season}"
    _tv_file_rmt_format = "{title} - {season_episode}"
    _movie_category_flag = False
    _tv_category_flag = False
    _anime_category_flag = False

    def get_movie_dest_path(self, media, _adapter=None, _snapshot=None):
        return f"{media.title} ({media.year})", f"{media.title} ({media.year})"

    def get_tv_dest_path(self, media, _adapter=None, _snapshot=None):
        return (
            f"{media.title} ({media.year})",
            f"Season {media.begin_season}",
            f"{media.title} - S{media.begin_season:02d}E{media.begin_episode:02d}",
        )

    def get_dest_path_by_info(self, root, media, _adapter=None, _snapshot=None):
        return f"{root}/{media.title} ({media.year})"


def test_planner_generates_rename_item_from_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.transfer.library_rename_planner.TransferPathResolver.from_settings",
        classmethod(lambda _cls, _cfg: _FakeResolver()),
    )
    root = tmp_path / "movies"
    root.mkdir()
    video = root / "The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv"
    video.write_bytes(b"video")

    resolver = LibraryMetadataResolver(
        media_server=_FakeMediaServer(),
        rename_repo=_FakeRepo(),
        download_repo=_FakeDownloadRepo(),
    )
    planner = LibraryRenamePlanner(
        _FakeMediaConfig(str(root)),
        _FakeStorageRepo(),
        resolver,
        media_service=SimpleNamespace(),
        category_repo=_FakeCategoryRepo(),
    )
    scope = RenameScope(
        media_types=[ProviderMediaType.MOVIE],
        roots=[str(root)],
        use_mediaserver_metadata=False,
    )
    snapshot = planner.prepare(scope)
    items = planner.build_items(scope)

    assert snapshot["movie_name_format"]
    assert len(items) == 1
    item = items[0]
    assert item["ACTION"] == "rename"
    assert item["OLD_PATH"] == str(video)
    assert "The Matrix" in item["NEW_PATH"]


class _FakeRemoteBackend:
    def list_dir(self, path):
        if path == "/remote":
            yield FileInfo(path="/remote/Show", size=0, mtime=0, is_dir=True)
            yield FileInfo(path="/remote/poster.jpg", size=1, mtime=0, is_dir=False)
        elif path == "/remote/Show":
            yield FileInfo(path="/remote/Show/Episode.mkv", size=1, mtime=0, is_dir=False)


def test_remote_scan_walks_directories():
    resolver = LibraryMetadataResolver(
        media_server=_FakeMediaServer(),
        rename_repo=_FakeRepo(),
        download_repo=_FakeDownloadRepo(),
    )
    planner = LibraryRenamePlanner(
        _FakeMediaConfig("/remote"),
        _FakeStorageRepo(),
        resolver,
        media_service=SimpleNamespace(),
        category_repo=_FakeCategoryRepo(),
    )
    paths = list(planner._iter_remote_files("/remote", cast(StorageBackend, _FakeRemoteBackend())))
    assert paths == ["/remote/Show/Episode.mkv"]
