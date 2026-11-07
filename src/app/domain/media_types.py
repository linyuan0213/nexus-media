"""媒体类型注册表：结构类型与插件自定义内容类型解耦."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProviderMediaType(str, Enum):
    """唯一内容类型值对象；TV/SERIES 是同一外部协议值."""

    SERIES = "tv"
    MOVIE = "movie"
    ANIME = "anime"
    UNKNOWN = "unknown"

    @classmethod
    def from_value(cls, value: Any) -> "ProviderMediaType":
        if isinstance(value, cls):
            return value
        raw_value = value.value if isinstance(value, Enum) else value
        raw = str(raw_value or "").strip().lower()
        if raw in {"movie", "film", "电影"}:
            return cls.MOVIE
        if raw in {"series", "show", "tv", "episode", "episodic", "电视剧", "剧集"}:
            return cls.SERIES
        if raw in {"anime", "动漫"}:
            return cls.ANIME
        return cls.UNKNOWN

    @property
    def kind(self) -> "MediaKind":
        if self == ProviderMediaType.MOVIE:
            return MediaKind.MOVIE
        if self in {ProviderMediaType.SERIES, ProviderMediaType.ANIME}:
            return MediaKind.EPISODIC
        return MediaKind.UNKNOWN

    @property
    def display_name(self) -> str:
        return _MEDIA_TYPE_DISPLAY_NAMES.get(self, "未知")

    def __str__(self) -> str:
        return self.value


_MEDIA_TYPE_DISPLAY_NAMES: dict[ProviderMediaType, str] = {
    ProviderMediaType.MOVIE: "电影",
    ProviderMediaType.SERIES: "电视剧",
    ProviderMediaType.ANIME: "动漫",
    ProviderMediaType.UNKNOWN: "未知",
}


class MediaKind(str, Enum):
    MOVIE = "movie"
    EPISODIC = "episodic"
    UNKNOWN = "unknown"


def provider_media_type_of(value: Any) -> ProviderMediaType:
    """把内部类型/外部协议值归一为 ProviderMediaType；未知值不猜测."""
    return ProviderMediaType.from_value(value)


def external_protocol_type(value: Any, *, anime_as_series: bool = True) -> ProviderMediaType:
    """归一为外部协议类型；仅支持 movie/tv 的协议把动漫视为剧集."""
    provider_type = provider_media_type_of(value)
    if anime_as_series and provider_type == ProviderMediaType.ANIME:
        return ProviderMediaType.SERIES
    return provider_type


def external_protocol_value(value: Any, *, anime_as_series: bool = True) -> str:
    """输出外部协议字符串（movie/tv/anime/unknown）."""
    return external_protocol_type(value, anime_as_series=anime_as_series).value


def media_kind_of(value: Any) -> MediaKind:
    """返回内部结构类型，用于电影/连续性判断."""
    return provider_media_type_of(value).kind


@dataclass(frozen=True)
class MediaTypeDescriptor:
    key: str
    kind: MediaKind
    display_name: str
    code_identity: bool = False
    aliases: tuple[str, ...] = ()
    content_profiles: tuple[str, ...] = ()
    plugin_id: str | None = None


@dataclass(frozen=True)
class MediaTypeRef:
    key: str
    kind: MediaKind
    display_name: str
    content_profile: str = "default"
    code_identity: bool = False

    @property
    def content_type(self) -> ProviderMediaType:
        if self.key == ProviderMediaType.ANIME.value:
            return ProviderMediaType.ANIME
        if self.kind == MediaKind.MOVIE:
            return ProviderMediaType.MOVIE
        if self.kind == MediaKind.EPISODIC:
            return ProviderMediaType.SERIES
        return ProviderMediaType.UNKNOWN


_CORE = {
    "movie": MediaTypeDescriptor("movie", MediaKind.MOVIE, "电影", aliases=("电影",)),
    "tv": MediaTypeDescriptor("tv", MediaKind.EPISODIC, "电视剧", aliases=("电视剧", "series", "show")),
    "anime": MediaTypeDescriptor("anime", MediaKind.EPISODIC, "动漫", aliases=("动漫",), content_profiles=("anime",)),
    "unknown": MediaTypeDescriptor("unknown", MediaKind.UNKNOWN, "未知"),
}
_CORE_ALIASES = {
    **{alias.lower(): key for key, descriptor in _CORE.items() for alias in descriptor.aliases},
    **{key: key for key in _CORE},
}


class MediaTypeRegistry:
    """类型描述符注册表；插件只能注册 `plugin:` 命名空间."""

    def __init__(self) -> None:
        self._descriptors: dict[str, MediaTypeDescriptor] = dict(_CORE)

    def register(self, descriptor: MediaTypeDescriptor) -> None:
        key = str(descriptor.key or "").strip()
        if not key:
            raise ValueError("media type key 不能为空")
        if not key.startswith("plugin:"):
            raise ValueError("插件媒体类型必须以 plugin: 开头")
        self._descriptors[key] = descriptor

    def unregister_namespace(self, namespace: str) -> None:
        prefix = namespace if namespace.startswith("plugin:") else f"plugin:{namespace}"
        for key in [key for key in self._descriptors if key.startswith(prefix)]:
            self._descriptors.pop(key, None)

    def get(self, key: str | None) -> MediaTypeDescriptor | None:
        return self._descriptors.get(str(key or "").strip())

    def resolve(self, value: Any = None, content_profile: str | None = "default") -> MediaTypeRef:
        if isinstance(value, MediaTypeRef):
            return value
        if isinstance(value, ProviderMediaType):
            key = value.value
        else:
            raw = str(value or "").strip()
            key = raw if raw in self._descriptors else _CORE_ALIASES.get(raw.lower(), "")
            if not key:
                parsed = ProviderMediaType.from_value(raw)
                key = parsed.value if parsed != ProviderMediaType.UNKNOWN else ""
        descriptor = self._descriptors.get(key) or _CORE["unknown"]
        profile = str(content_profile or "").strip() or "default"
        return MediaTypeRef(
            key=descriptor.key,
            kind=descriptor.kind,
            display_name=descriptor.display_name,
            content_profile=profile,
            code_identity=descriptor.code_identity,
        )

    def from_payload(self, payload: dict[str, Any] | None) -> MediaTypeRef:
        """兼容旧 Redis payload：新 key/kind 优先，旧 media_type/type 自动解析."""
        data = payload or {}
        profile = str(data.get("content_profile") or "default")
        key = str(data.get("media_type_key") or "").strip()
        kind_value = str(data.get("media_kind") or "").strip()
        if key:
            resolved = self.resolve(key, profile)
            if resolved.key == "unknown" and kind_value:
                try:
                    kind = MediaKind(kind_value)
                except ValueError:
                    kind = MediaKind.UNKNOWN
                descriptor = self._descriptors.get(key)
                return MediaTypeRef(
                    key=key,
                    kind=kind,
                    display_name=descriptor.display_name if descriptor is not None else key,
                    content_profile=profile,
                )
            return resolved
        return self.resolve_profile(profile) or self.resolve(data.get("media_type") or data.get("type"), profile)

    def resolve_profile(self, content_profile: str | None) -> MediaTypeRef | None:
        """按 content profile 找插件/核心描述符；找不到返回 None，不默认 movie."""
        profile = str(content_profile or "").strip()
        if not profile or profile == "default":
            return None
        matches = [descriptor for descriptor in self._descriptors.values() if profile in descriptor.content_profiles]
        if not matches:
            return None
        descriptor = sorted(matches, key=lambda item: item.key != "anime")[0]
        return self.resolve(descriptor.key, profile)

    def all(self) -> tuple[MediaTypeDescriptor, ...]:
        return tuple(self._descriptors.values())


def normalize_media_type_input(
    value: str | None,
    content_profile: str | None = None,
) -> tuple[str | None, str]:
    """归一化 API 入参中的展示类型别名，返回 (media_type, content_profile)."""
    profile = str(content_profile or "").strip() or "default"
    return value, profile


media_type_registry = MediaTypeRegistry()
