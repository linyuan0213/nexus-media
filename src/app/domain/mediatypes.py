"""媒体类型值对象."""

from enum import Enum


class MediaType(Enum):
    TV = "tv"
    MOVIE = "movie"
    ANIME = "anime"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return _MEDIA_TYPE_DISPLAY_NAMES.get(self, "未知")

    @classmethod
    def from_string(cls, value: str) -> "MediaType":
        normalized = str(value).strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.UNKNOWN

    def __str__(self) -> str:
        return self.value


_MEDIA_TYPE_DISPLAY_NAMES: dict[MediaType, str] = {
    MediaType.MOVIE: "电影",
    MediaType.TV: "电视剧",
    MediaType.ANIME: "动漫",
    MediaType.UNKNOWN: "未知",
}
