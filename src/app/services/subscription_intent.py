"""统一的订阅意图解析：provider 能力、ID 格式、画像和策略."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.mediatypes import MediaType
from app.media.metadata.providers.tmdb import TmdbProvider
from app.media.metadata.registry import registry as metadata_registry

_LEGACY_DESCRIPTORS = {"tmdb": TmdbProvider.descriptor}


@dataclass(frozen=True)
class SubscriptionIntent:
    provider: str
    external_id: str
    name: str
    content_profile: str
    media_type: MediaType
    mediaid: str
    metadata_ref: str | None
    metadata_policy: str | None
    keyword: str | None
    allow_private: bool


def _descriptor(provider: str):
    item = metadata_registry.get_provider(provider) if provider else None
    if item is None:
        # 订阅工具可能早于 MetadataService 被调用；TMDB 是内置旧 ID 来源。
        return _LEGACY_DESCRIPTORS.get(provider)
    return getattr(item, "descriptor", None)


def resolve_subscription(
    provider: str,
    external_id: str,
    name: str,
    *,
    content_profile: str | None = None,
    metadata_policy: str | None = None,
) -> SubscriptionIntent | None:
    provider = str(provider or "").strip().lower()
    external_id = str(external_id or "").strip()
    if not provider or not external_id:
        return None
    descriptor = _descriptor(provider)
    if descriptor is None:
        return None
    profile = str(content_profile or descriptor.default_content_profile or "default")
    if profile == "default":
        profiles = {
            str(item)
            for item in getattr(descriptor, "content_profiles", frozenset())
            if str(item) and str(item) != "default"
        }
        if profiles:
            profile = sorted(profiles)[0]
    media_type = (
        descriptor.default_provider_media_type.to_media_type()
        if descriptor.default_provider_media_type is not None
        else (MediaType.TV if profile == "anime" else MediaType.MOVIE)
    )
    declared_format = str(getattr(descriptor, "subscription_id_format", "") or "")
    id_format = declared_format or ("{provider}:{id}" if profile != "default" else "{id}")
    mediaid = id_format.format(provider=provider, id=external_id)
    # 没有声明正式订阅 ID 格式的来源视为插件锚点，需要 metadata_ref。
    ref = (
        f"{provider}:{external_id}"
        if bool(getattr(descriptor, "subscription_ref", False)) or not declared_format
        else None
    )
    if metadata_policy:
        policy = metadata_policy
    elif str(getattr(descriptor, "default_subscription_policy", "") or ""):
        policy = str(descriptor.default_subscription_policy)
    elif profile != "default":
        policy = f"provider_only:{profile}"
    else:
        policy = None
    return SubscriptionIntent(
        provider=provider,
        external_id=external_id,
        name=name or external_id,
        content_profile=profile,
        media_type=media_type,
        mediaid=mediaid,
        metadata_ref=ref,
        metadata_policy=policy,
        keyword=external_id if profile != "default" else None,
        allow_private=str(getattr(descriptor, "visibility", "public")) == "private",
    )
