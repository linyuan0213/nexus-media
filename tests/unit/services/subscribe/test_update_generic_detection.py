"""多元数据订阅在编辑时应走通用更新，不强制 TMDB."""

from types import SimpleNamespace

from app.services.subscribe.management.update_service import SubscribeUpdateService


def _row(**kwargs):
    base = {
        "ANCHOR_PROVIDER": "",
        "CONTENT_PROFILE": "",
        "TMDBID": "",
        "PROVIDER": "",
        "METADATA_REF": "",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestGenericSubscriptionDetection:
    def test_tmdb_movie_is_not_generic(self):
        assert not SubscribeUpdateService._is_generic_subscription(
            _row(ANCHOR_PROVIDER="tmdb", TMDBID="123", PROVIDER="tmdb", METADATA_REF="tmdb:123")
        )

    def test_source_provider_routes_to_generic(self):
        assert SubscribeUpdateService._is_generic_subscription(_row(PROVIDER="javdb"))

    def test_metadata_ref_routes_to_generic(self):
        assert SubscribeUpdateService._is_generic_subscription(_row(PROVIDER="tmdb", METADATA_REF="javdb:P0dyv"))

    def test_non_default_profile_routes_to_generic(self):
        assert SubscribeUpdateService._is_generic_subscription(_row(CONTENT_PROFILE="adult"))
