"""展示图片转换器回归：所有展示入口共用同一套插件规则."""

from urllib.parse import quote

from app.domain.media_types import ProviderMediaType
from app.media.display_image_policy import (
    clear_display_image_transformers,
    register_display_image_transformer,
    transform_display_image,
    unregister_display_image_transformer,
)
from app.media.message_image_policy import (
    clear_message_image_transformers,
    register_message_image_transformer,
)
from app.media.metadata.models import ImageAsset, MediaMetadata
from app.media.models import MediaInfo


def test_display_transformer_applies_by_profile():
    clear_display_image_transformers()
    register_display_image_transformer(lambda profile, url: "/img/blur?url=x" if profile == "demo" and url else url)
    try:
        assert transform_display_image("demo", "http://a.jpg") == "/img/blur?url=x"
        assert transform_display_image("default", "http://a.jpg") == "http://a.jpg"
    finally:
        clear_display_image_transformers()


def test_display_transformer_unregister_stops_rewrite():
    clear_display_image_transformers()

    def transformer(profile, url):
        return "/blur" if url else url

    register_display_image_transformer(transformer)
    unregister_display_image_transformer(transformer)
    assert transform_display_image("demo", "http://a.jpg") == "http://a.jpg"


def test_display_transformer_ignores_plugin_errors():
    clear_display_image_transformers()

    def broken(profile, url):
        raise RuntimeError("boom")

    register_display_image_transformer(broken)
    try:
        assert transform_display_image("demo", "http://a.jpg") == "http://a.jpg"
    finally:
        clear_display_image_transformers()


def test_media_info_message_image_uses_display_transformer():
    clear_display_image_transformers()
    clear_message_image_transformers()
    register_display_image_transformer(lambda profile, url: "/img/blur?url=x" if profile == "demo" and url else url)
    try:
        media = MediaInfo(title="T", type=ProviderMediaType.MOVIE)
        media.content_profile = "demo"
        media.poster_path = "http://a.jpg"
        assert media.get_message_image() == "/img/blur?url=x"
    finally:
        clear_display_image_transformers()
        clear_message_image_transformers()


def test_media_info_message_image_uses_snapshot_fanart_without_tmdb_placeholder():
    clear_display_image_transformers()
    clear_message_image_transformers()
    media = MediaInfo(title="TC-268", type=ProviderMediaType.MOVIE)
    media.content_profile = "demo"
    setattr(
        media,
        "snapshot",
        MediaMetadata(
            identity_id="x",
            images={"fanart": [ImageAsset(type="fanart", url="http://plugin/fanart.jpg")]},
        ),
    )

    assert media.get_message_image() == "http://plugin/fanart.jpg"


def test_message_image_can_be_blurred_while_page_image_is_clear():
    clear_display_image_transformers()
    clear_message_image_transformers()
    register_display_image_transformer(lambda profile, url: url)
    register_message_image_transformer(lambda profile, url: "/img/blur?url=x" if profile == "demo" and url else url)
    try:
        media = MediaInfo(title="T", type=ProviderMediaType.MOVIE)
        media.content_profile = "demo"
        media.poster_path = "http://a.jpg"
        assert media.get_message_image() == "/img/blur?url=x"
    finally:
        clear_display_image_transformers()
        clear_message_image_transformers()


def test_message_image_does_not_fall_back_to_display_blur_when_message_rule_exists():
    clear_display_image_transformers()
    clear_message_image_transformers()
    register_display_image_transformer(lambda profile, url: "/img/blur?url=x" if profile == "demo" and url else url)
    register_message_image_transformer(lambda profile, url: url)
    try:
        media = MediaInfo(title="T", type=ProviderMediaType.MOVIE)
        media.content_profile = "demo"
        media.poster_path = "http://a.jpg"
        assert media.get_message_image() == "http://a.jpg"
    finally:
        clear_display_image_transformers()
        clear_message_image_transformers()


def test_message_poster_uses_message_policy_but_page_poster_stays_clear():
    clear_display_image_transformers()
    clear_message_image_transformers()
    register_display_image_transformer(lambda profile, url: "/display" if url else url)
    register_message_image_transformer(lambda profile, url: "/message" if url else url)
    try:
        media = MediaInfo(title="T", type=ProviderMediaType.MOVIE)
        media.content_profile = "demo"
        media.poster_path = "http://a.jpg"
        assert media.get_poster_image() == "http://a.jpg"
        assert media.get_message_image() == "/message"
        assert media.get_message_poster_image() == "/message"
    finally:
        clear_display_image_transformers()
        clear_message_image_transformers()


def test_display_transformer_unwraps_stored_blur_when_rule_is_disabled():
    clear_display_image_transformers()
    register_display_image_transformer(lambda profile, url: url)
    blur = f"/img/blur?url={quote('http://a.jpg', safe='')}&radius=24"
    try:
        assert transform_display_image("custom", blur) == "http://a.jpg"
    finally:
        clear_display_image_transformers()
