"""目录同步：目标硬链接被删除后应重新视为缺失，触发重新硬链接。

回归：`get_no_exists_medias` 的转移历史判断此前只看源文件是否存在，
目标媒体文件被删除后仍被当作“已转移”，导致同步不再硬链接。
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.transfer.filetransfer_service import FileTransferService


def _svc(exists: bool, tmp_path, dest_filename="E05.mkv"):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"x")
    svc = FileTransferService.__new__(FileTransferService)
    svc._history = MagicMock()
    svc._existence = MagicMock()
    svc._history.get_transfer_info_by.return_value = [
        SimpleNamespace(
            source_path=str(src),
            season_episode="S01E05",
            dest_path=str(tmp_path / "lib"),
            dest_filename=dest_filename,
            dst_backend=None,
        )
    ]
    svc._existence.exists.return_value = exists
    svc._existence.get_no_exists_medias.return_value = [1, 2, 3]
    return svc


def _meta():
    return SimpleNamespace(type=MediaType.TV, tmdb_id=1)


def test_dest_exists_history_counts_transferred(tmp_path):
    svc = _svc(exists=True, tmp_path=tmp_path)
    result = svc.get_no_exists_medias(_meta(), season=1, total_num=12)
    assert set(result) == {1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12}
    cast(Any, svc._existence).get_no_exists_medias.assert_not_called()


def test_dest_deleted_falls_back_to_rescan(tmp_path):
    svc = _svc(exists=False, tmp_path=tmp_path)
    result = svc.get_no_exists_medias(_meta(), season=1, total_num=12)
    # 目标被删除 → 历史不计入 → 回退文件扫码（重新视为缺失）
    assert result == [1, 2, 3]
    cast(Any, svc._existence).get_no_exists_medias.assert_called_once()


def _svc_for_dedup(tmp_path, dest_exists: bool):
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    file_item = src_dir / "E01.mkv"
    file_item.write_bytes(b"x")
    dest_dir = tmp_path / "lib" / "Show" / "S01"
    dest_file = dest_dir / "E01.mkv"
    if dest_exists:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(b"y")

    svc = FileTransferService.__new__(FileTransferService)
    svc._history = MagicMock()
    svc._existence = MagicMock()
    svc._existence.is_media_exists.return_value = (
        dest_exists,
        str(dest_dir),
        dest_exists,
        str(dest_file),
    )
    svc._history.get_transfer_info_by.return_value = [
        SimpleNamespace(
            source_path=str(src_dir),
            season_episode="S01E01",
            dest_path=str(dest_dir),
            dest_filename="E01.mkv",
        )
    ]
    svc._engine = MagicMock()
    svc._replicate_to_enabled_backends = MagicMock()
    return svc, file_item


def _media():
    return SimpleNamespace(
        type=MediaType.TV,
        tmdb_id=1,
        begin_season=1,
        begin_episode=1,
        get_season_episode_string=lambda: "S01E01",
    )


def test_file_dedup_relinks_when_dest_missing(tmp_path):
    """回归 #196：目标硬链接被删除后，转移历史不应再阻止重新转移（重新硬链接）."""
    svc, file_item = _svc_for_dedup(tmp_path, dest_exists=False)

    svc._do_transfer_file(
        str(file_item),
        _media(),
        str(tmp_path / "lib"),
        None,
        "link",
        str(file_item),
        str(tmp_path / "lib"),
        False,
        [],
    )

    cast(Any, svc._engine).transfer.assert_called_once()
    cast(Any, svc._history).insert_transfer_blacklist.assert_not_called()


def test_file_dedup_skips_when_dest_exists(tmp_path):
    svc, file_item = _svc_for_dedup(tmp_path, dest_exists=True)

    svc._do_transfer_file(
        str(file_item),
        _media(),
        str(tmp_path / "lib"),
        None,
        "link",
        str(file_item),
        str(tmp_path / "lib"),
        False,
        [],
    )

    cast(Any, svc._engine).transfer.assert_not_called()
    cast(Any, svc._history).insert_transfer_blacklist.assert_called_once()
