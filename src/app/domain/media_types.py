"""媒体类型注册表：结构类型与插件自定义内容类型解耦."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.mediatypes import MediaType


class MediaKind(str, Enum):
    MOVIE = "movie"
    EPISODIC = "episodic"
    UNKNOWN = "unknown"


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

    def resolve(self, value: Any = None, content_profile: str = "default") -> MediaTypeRef:
        if isinstance(value, MediaTypeRef):
            return value
        if isinstance(value, MediaType):
            key = value.value
        else:
            raw = str(value or "").strip()
            key = raw if raw in self._descriptors else _CORE_ALIASES.get(raw.lower(), "")
            if not key:
                parsed = MediaType.from_string(raw)
                key = parsed.value if parsed != MediaType.UNKNOWN else ""
        descriptor = self._descriptors.get(key) or _CORE["unknown"]
        profile = str(content_profile or "").strip() or "default"
        return MediaTypeRef(
            key=descriptor.key,
            kind=descriptor.kind,
            display_name=descriptor.display_name,
            content_profile=profile,
            code_identity=descriptor.code_identity,
        )

    def all(self) -> tuple[MediaTypeDescriptor, ...]:
        return tuple(self._descriptors.values())


media_type_registry = MediaTypeRegistry()
