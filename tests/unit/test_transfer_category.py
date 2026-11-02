"""转移快照分类统一测试."""

from types import SimpleNamespace

from app.domain.mediatypes import MediaType
from app.services.transfer import filetransfer_service as module
from app.services.transfer.filetransfer_service import FileTransferService


class _Category:
    def __init__(self, name, rules=None, default=False):
        self.name = name
        self.media_type = "movie"
        self.rules = rules or {}
        self.is_default = default
        self.enabled = True


def _snapshot(languages=None):
    return SimpleNamespace(
        media_type=MediaType.MOVIE,
        content_profile="default",
        primary_provider="douban",
        refs=[SimpleNamespace(provider="douban")],
        genres=["剧情"],
        countries=["美国"],
        spoken_languages=languages or [],
        tags=[],
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
    media = SimpleNamespace(type=MediaType.MOVIE)
    assert svc._category_from_snapshot(_snapshot(), media) == "外语电影"
    assert svc._category_from_snapshot(_snapshot(["zh"]), media) == "华语电影"
