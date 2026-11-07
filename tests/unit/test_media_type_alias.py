"""媒体类型 API 别名归一化测试."""

# 先完成仓储包初始化，避免 system_config 与 repositories 的既有循环导入。
import app.db.repositories  # noqa: F401
from app.domain.media_types import ProviderMediaType, normalize_media_type_input
from app.services.system.info import WebSearchService


def test_unknown_type_is_not_rewritten_to_demo_profile():
    media_type, profile = normalize_media_type_input("av", "default")

    assert media_type == "av"
    assert profile == "default"


def test_legacy_type_keeps_explicit_profile():
    media_type, profile = normalize_media_type_input("AV", "demo")

    assert media_type == "AV"
    assert profile == "demo"


def test_regular_media_type_is_unchanged():
    media_type, profile = normalize_media_type_input("tv", "default")

    assert media_type == "tv"
    assert profile == "default"


def test_web_search_does_not_default_unknown_plugin_profile_to_movie():
    captured = {}

    def search_fn(**kwargs):
        captured.update(kwargs)
        return 1, ""

    WebSearchService(search_fn).search(
        "CONTENT-001",
        media_type="legacy-type",
        filters={"content_profile": "plugin-profile"},
    )

    assert captured["media_type"] == "legacy-type"
    assert captured["filters"]["content_profile"] == "plugin-profile"


def test_canonical_media_type_values():
    assert ProviderMediaType.SERIES.value == "tv"
    assert ProviderMediaType.from_value("series") is ProviderMediaType.SERIES
    assert ProviderMediaType.from_value("电影") is ProviderMediaType.MOVIE
