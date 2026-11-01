"""转移：聚合目录命中多条下载记录时，应按文件名消歧取正确 TMDB。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.transfer.filetransfer_service import FileTransferService


def _service(records, tmp_path):
    parent = tmp_path / "anime"
    parent.mkdir()
    file_path = parent / "【10月】与暗黑召唤师秘密恋爱中 01【完全无修版】.mp4"
    file_path.write_bytes(b"x")

    svc = FileTransferService.__new__(FileTransferService)
    repo = MagicMock()
    repo.get_download_history_by_path.return_value = None
    repo.count_download_history_by_path.return_value = len(records)
    repo.get_download_history_list_by_path.return_value = records
    setattr(svc, "_history", SimpleNamespace(download_repo=repo))
    svc.media = MagicMock()
    svc.media.get_tmdb_info.return_value = {"id": 335790, "name": "黑暗召唤师在地下恋爱中"}
    return svc, str(file_path)


def test_disambiguates_by_filename_in_aggregated_dir(tmp_path):
    records = [
        SimpleNamespace(
            TMDBID=999,
            TYPE="anime",
            SE="S01 E09",
            TORRENT="[Group] 完全不相干的剧集 - 09",
            TITLE="不相干",
        ),
        SimpleNamespace(
            TMDBID=335790,
            TYPE="anime",
            SE="S01 E01",
            TORRENT="[完全无修版] 与暗黑召唤师秘密恋爱中 - 01 [简／繁] (1080p)",
            TITLE="黑暗召唤师在地下恋爱中",
        ),
    ]
    svc, file_path = _service(records, tmp_path)
    tmdb_info, media_type, _s, _e = svc._lookup_download_record(file_path)
    assert tmdb_info is not None
    assert media_type == MediaType.ANIME


def test_ambiguous_records_return_none(tmp_path):
    records = [
        SimpleNamespace(TMDBID=1, TYPE="anime", SE="S01 E01", TORRENT="[A] 甲剧 - 01", TITLE="甲剧"),
        SimpleNamespace(TMDBID=2, TYPE="anime", SE="S01 E01", TORRENT="[B] 乙剧 - 01", TITLE="乙剧"),
    ]
    svc, file_path = _service(records, tmp_path)
    tmdb_info, media_type, _s, _e = svc._lookup_download_record(file_path)
    assert tmdb_info is None and media_type is None


def test_same_tmdb_multiple_records_not_ambiguous(tmp_path):
    """同一部剧的多条记录（同名同 TMDB）分列前二，不应判为歧义。"""
    records = [
        SimpleNamespace(
            TMDBID=335790,
            TYPE="anime",
            SE="S01 E01",
            TORRENT="[完全无修版] 与暗黑召唤师秘密恋爱中 - 01 [简／繁] (1080p)",
            TITLE="黑暗召唤师在地下恋爱中",
        ),
        SimpleNamespace(
            TMDBID=335790,
            TYPE="anime",
            SE="S01 E02",
            TORRENT="[完全无修版] 与暗黑召唤师秘密恋爱中 - 02 [简／繁] (1080p)",
            TITLE="黑暗召唤师在地下恋爱中",
        ),
        SimpleNamespace(TMDBID=295071, TYPE="anime", SE="S01 E11", TORRENT="[ANi] 再见菈菈 - 11", TITLE="再见菈菈"),
    ]
    svc, file_path = _service(records, tmp_path)
    tmdb_info, media_type, _s, _e = svc._lookup_download_record(file_path)
    assert tmdb_info is not None
    assert media_type == MediaType.ANIME


def test_apply_download_record_hint_keeps_anchor_without_tmdb():
    media = SimpleNamespace(
        anchor_provider=None,
        anchor_external_id=None,
        identity_id=None,
        content_profile="default",
        poster_path=None,
        title="",
    )
    record = SimpleNamespace(
        ANCHOR_PROVIDER="content_id",
        ANCHOR_EXTERNAL_ID="CUSTOM-0001",
        IDENTITY_ID="I1",
        CONTENT_PROFILE="custom",
        POSTER="http://poster",
        TITLE="Custom Title",
    )

    FileTransferService._apply_download_record_hint(media, record)

    assert media.anchor_provider == "content_id"
    assert media.anchor_external_id == "CUSTOM-0001"
    assert media.identity_id == "I1"
    assert media.content_profile == "custom"
    assert media.poster_path == "http://poster"
    assert media.title == "Custom Title"
