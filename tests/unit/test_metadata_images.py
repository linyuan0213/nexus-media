"""ImageResolver 单元测试."""

from app.domain.media_types import ProviderMediaType
from app.media.metadata import (
    Credit,
    ImageAsset,
    ImageResolver,
    MediaMetadata,
    ProviderRef,
)


def _snapshot() -> MediaMetadata:
    return MediaMetadata(
        identity_id="id-1",
        media_type=ProviderMediaType.MOVIE,
        primary_provider="douban",
        refs=[
            ProviderRef(provider="douban", external_id="1"),
            ProviderRef(provider="tmdb", external_id="2"),
        ],
        images={
            "poster": [
                ImageAsset(type="poster", url="tmdb-small", width=300, height=450, provider="tmdb"),
                ImageAsset(type="poster", url="douban-small", width=400, height=600, provider="douban"),
                ImageAsset(type="poster", url="douban-large", width=800, height=1200, provider="douban"),
                ImageAsset(type="poster", url="tmdb-large", width=1000, height=1500, provider="tmdb"),
                ImageAsset(type="poster", url="douban-large", width=800, height=1200, provider="douban"),
            ],
            "backdrop": [ImageAsset(type="backdrop", url="tmdb-backdrop", width=1920, height=1080, provider="tmdb")],
        },
        credits=[
            Credit(name="演员B", role="actor", order=2, image_url="b.jpg"),
            Credit(name="导演", role="director", order=0, image_url="d.jpg"),
            Credit(name="演员A", role="actor", order=1, image_url="a.jpg"),
        ],
    )


def test_candidates_respect_provider_priority_and_resolution():
    candidates = ImageResolver().candidates(_snapshot(), "poster")

    assert candidates == ["douban-large", "douban-small", "tmdb-large", "tmdb-small"]


def test_best_falls_back_to_other_provider():
    snapshot = _snapshot()
    snapshot.images["poster"] = [ImageAsset(type="poster", url="douban-only", width=100, height=150, provider="douban")]

    assert ImageResolver().best(snapshot, "poster") == "douban-only"
    assert ImageResolver().best(snapshot, "backdrop") == "tmdb-backdrop"


def test_min_width_filters_low_resolution():
    candidates = ImageResolver().candidates(_snapshot(), "poster", min_width=900)

    assert candidates == ["tmdb-large"]


def test_actor_candidates_sorted_and_excludes_directors():
    actors = ImageResolver().actor_candidates(_snapshot())

    assert actors == [("演员A", "a.jpg"), ("演员B", "b.jpg")]
