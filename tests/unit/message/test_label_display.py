"""消息展示：类型与来源使用中文标签."""

from app.domain.enums import SubscribeType
from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.message.core.message_builder import _type_label
from app.utils.string_utils import StringUtils


def test_anime_type_label_is_chinese():
    media = MediaInfo(title="Demo", type=ProviderMediaType.ANIME)
    assert _type_label(media, "default") == "动漫"


def test_anime_profile_label_is_chinese():
    media = MediaInfo(title="Demo", type=ProviderMediaType.ANIME)
    assert _type_label(media, "anime") == "动漫"


def test_anime_profile_overrides_tv_type_label():
    media = MediaInfo(title="Demo", type=ProviderMediaType.SERIES)
    assert _type_label(media, "anime") == "动漫"


def test_type_string_uses_chinese_display_name():
    assert MediaInfo(title="Demo", type=ProviderMediaType.MOVIE).get_type_string() == "类型：电影"
    assert MediaInfo(title="Demo", type=ProviderMediaType.SERIES).get_type_string() == "类型：电视剧"
    assert MediaInfo(title="Demo", type=ProviderMediaType.ANIME).get_type_string() == "类型：动漫"


def test_tv_type_label_is_chinese():
    media = MediaInfo(title="Demo", type=ProviderMediaType.SERIES)
    assert _type_label(media, "default") == "电视剧"


def test_subscribe_type_display_is_chinese():
    assert StringUtils.resolve_in_from_display(SubscribeType.Manual) == "手动"
    assert StringUtils.resolve_in_from_display(SubscribeType.Auto) == "自动"
