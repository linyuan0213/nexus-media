"""默认订阅设置键：支持按用户维度覆盖，全局配置作为兜底."""

from typing import Any

from app.domain.enums import SystemConfigKey
from app.domain.mediatypes import MediaType


def default_setting_key(
    media_type: MediaType | None,
    content_profile: str | None = None,
    user_id: int | str | None = None,
) -> str:
    """生成默认订阅设置键；user_id 非空时附加用户作用域."""
    if media_type in (MediaType.TV, MediaType.ANIME):
        key = SystemConfigKey.DefaultSubscribeSettingTV.value
    else:
        key = SystemConfigKey.DefaultSubscribeSettingMovie.value
        profile = str(content_profile or "").strip()
        if profile and profile != "default":
            key = f"{key}::{profile}"
    if user_id is not None and str(user_id).strip():
        key = f"{key}::u{user_id}"
    return key


def get_default_setting(
    system_config: Any,
    media_type: MediaType | None,
    content_profile: str | None = None,
    user_id: int | str | None = None,
) -> dict:
    """读取用户默认订阅设置；用户级缺失时回退全局."""
    if system_config is None:
        return {}
    value = system_config.get(default_setting_key(media_type, content_profile, user_id))
    if not isinstance(value, dict) and user_id is not None:
        value = system_config.get(default_setting_key(media_type, content_profile, None))
    return value if isinstance(value, dict) else {}
