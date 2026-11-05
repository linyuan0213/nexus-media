"""消息展示：类型与来源使用中文标签."""

from app.domain.enums import SubscribeType
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.message.core.message_builder import _type_label
from app.utils.string_utils import StringUtils


def test_anime_type_label_is_chinese():
    media = MediaInfo(title="Demo", type=MediaType.ANIME)
    assert _type_label(media, "default") == "动漫"


def test_tv_type_label_is_chinese():
    media = MediaInfo(title="Demo", type=MediaType.TV)
    assert _type_label(media, "default") == "电视剧"


def test_subscribe_type_display_is_chinese():
    assert StringUtils.resolve_in_from_display(SubscribeType.Manual) == "手动"
    assert StringUtils.resolve_in_from_display(SubscribeType.Auto) == "自动"
