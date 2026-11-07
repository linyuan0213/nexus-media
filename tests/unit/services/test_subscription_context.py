"""订阅上下文解析回归."""

from types import SimpleNamespace

from app.domain.media_types import ProviderMediaType
from app.services import subscription_context


def test_tv_context_maps_orm_fields_and_image(monkeypatch):
    row = SimpleNamespace(
        ID=7,
        NAME="龙珠超 比鲁斯",
        YEAR="2026",
        SEASON="S01",
        IMAGE="https://img/poster.jpg",
        TMDBID="1399",
        IDENTITY_ID="01IDENTITY",
        ANCHOR_PROVIDER="tmdb",
        ANCHOR_EXTERNAL_ID="1399",
        CONTENT_PROFILE="default",
    )

    class Repo:
        def get_all(self, rssid=None):
            return [row] if rssid == 7 else []

    monkeypatch.setattr(subscription_context, "SubscribeTvRepositoryAdapter", Repo)
    item = SimpleNamespace(type=ProviderMediaType.SERIES, rssid=7)

    ctx = subscription_context.resolve_subscription_context(item)

    assert ctx is not None
    assert ctx.name == "龙珠超 比鲁斯"
    assert ctx.image == "https://img/poster.jpg"
    assert ctx.anchor_provider == "tmdb"
    assert ctx.type == ProviderMediaType.SERIES


def test_context_falls_back_to_tmdb_when_rssid_missing(monkeypatch):
    row = SimpleNamespace(ID=8, NAME="测试", YEAR="2024", TMDBID="100", IMAGE="poster")
    seen = []

    class Repo:
        def get_all(self, rssid=None):
            seen.append(rssid)
            return [row]

    monkeypatch.setattr(subscription_context, "SubscribeMovieRepositoryAdapter", Repo)
    item = SimpleNamespace(type="movie", tmdb_id="100")

    ctx = subscription_context.resolve_subscription_context(item)

    assert ctx is not None
    assert ctx.id == 8
    assert ctx.image == "poster"
    assert seen == [None]
