"""转移快照分类统一测试."""

from types import SimpleNamespace

from app.domain.media_types import ProviderMediaType
from app.services.transfer import filetransfer_service as module
from app.services.transfer.filetransfer_service import FileTransferService


class _Category:
    def __init__(self, name, rules=None, default=False):
        self.name = name
        self.media_type = "movie"
        self.rules = rules or {}
        self.is_default = default
        self.enabled = True


def _snapshot(languages=None, fields=None, genres=None, countries=None):
    return SimpleNamespace(
        media_type=ProviderMediaType.MOVIE,
        content_profile="default",
        primary_provider="douban",
        refs=[SimpleNamespace(provider="douban")],
        genres=["剧情"] if genres is None else genres,
        countries=["美国"] if countries is None else countries,
        spoken_languages=languages or [],
        tags=[],
        fields=fields or {},
    )


def test_snapshot_category_uses_unified_rules(monkeypatch):
    monkeypatch.setattr(
        module.CategoryConfigRepositoryAdapter,
        "get_all",
        lambda _self: [
            _Category("华语电影", {"original_language": "zh"}),
            _Category("外语电影", default=True),
        ],
    )
    svc = FileTransferService.__new__(FileTransferService)
    media = SimpleNamespace(type=ProviderMediaType.MOVIE)
    assert svc._category_from_snapshot(_snapshot(), media) == "外语电影"
    assert svc._category_from_snapshot(_snapshot(["zh"]), media) == "华语电影"


def test_snapshot_category_reads_original_language_field(monkeypatch):
    """快照的 original_language 在 fields 里，必须参与匹配（TMDB 华语片）."""
    monkeypatch.setattr(
        module.CategoryConfigRepositoryAdapter,
        "get_all",
        lambda _self: [
            _Category("华语电影", {"original_language": "zh,cn,bo,za"}),
            _Category("外语电影", default=True),
        ],
    )
    svc = FileTransferService.__new__(FileTransferService)
    media = SimpleNamespace(type=ProviderMediaType.MOVIE)
    snapshot = _snapshot(fields={"original_language": SimpleNamespace(value="zh")})
    assert svc._category_from_snapshot(snapshot, media) == "华语电影"


def test_snapshot_category_matches_chinese_dialect_names(monkeypatch):
    """豆瓣返回“汉语普通话/粤语”，应归入华语而不是外语."""
    monkeypatch.setattr(
        module.CategoryConfigRepositoryAdapter,
        "get_all",
        lambda _self: [
            _Category("华语电影", {"original_language": "zh,cn,bo,za"}),
            _Category("外语电影", default=True),
        ],
    )
    svc = FileTransferService.__new__(FileTransferService)
    media = SimpleNamespace(type=ProviderMediaType.MOVIE)
    assert svc._category_from_snapshot(_snapshot(["汉语普通话"]), media) == "华语电影"
    assert svc._category_from_snapshot(_snapshot(["粤语"]), media) == "华语电影"
