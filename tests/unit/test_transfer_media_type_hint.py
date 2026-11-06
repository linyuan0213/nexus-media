"""转移时用下载记录纠正媒体类型."""

from types import SimpleNamespace

from app.domain.mediatypes import MediaType
from app.services.transfer.filetransfer_service import FileTransferService


def test_download_record_type_overrides_parser_type():
    media = SimpleNamespace(type=MediaType.TV, anchor_provider=None, content_profile=None, poster_path=None)
    record = SimpleNamespace(
        TYPE="movie",
        ANCHOR_PROVIDER="content_id",
        ANCHOR_EXTERNAL_ID="DEMO-969",
        IDENTITY_ID="identity-demo",
        CONTENT_PROFILE="demo",
        POSTER=None,
        TITLE="Demo title",
    )
    FileTransferService._apply_download_record_hint(media, record)
    assert media.type == MediaType.MOVIE


def test_anime_profile_overrides_legacy_tv_record_type():
    """历史动漫下载记录 TYPE=tv 时，按动画画像纠正为动漫，避免进电视剧库."""
    media = SimpleNamespace(type=MediaType.TV, anchor_provider=None, content_profile=None, poster_path=None)
    record = SimpleNamespace(
        TYPE="tv",
        ANCHOR_PROVIDER="bangumi",
        ANCHOR_EXTERNAL_ID="400602",
        IDENTITY_ID="identity-anime",
        CONTENT_PROFILE="anime",
        POSTER=None,
        TITLE="Demo anime",
    )
    FileTransferService._apply_download_record_hint(media, record)
    assert media.type == MediaType.ANIME
