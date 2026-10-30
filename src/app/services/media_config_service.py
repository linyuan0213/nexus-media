"""媒体路径配置服务 — 从数据库读取，兼容 YAML 回退"""

import json

from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.core.settings import settings
from app.db.repositories.config_repo_adapter import MediaConfigRepositoryAdapter
from app.utils.json_utils import JsonUtils


class MediaConfigService:
    """媒体库路径配置服务"""

    LAYOUT_FLAT = "flat"
    LAYOUT_CATEGORY = "category"
    DEFAULT_LAYOUTS = {"movie": LAYOUT_CATEGORY, "tv": LAYOUT_CATEGORY, "anime": LAYOUT_FLAT}

    def __init__(self, repo: MediaConfigRepositoryAdapter):
        self._repo = repo
        self._yaml_fallback = settings.get("media") or {}

    @staticmethod
    def _parse_paths(val) -> list[str]:
        if not val:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = JsonUtils.loads(val)
                return parsed if isinstance(parsed, list) else [parsed]
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @classmethod
    def _parse_layout(cls, value, media_type: str) -> str:
        candidate = str(value or "").strip().lower()
        if candidate in {cls.LAYOUT_FLAT, cls.LAYOUT_CATEGORY}:
            return candidate
        return cls.DEFAULT_LAYOUTS[media_type]

    @staticmethod
    def _parse_backends(val) -> list[str]:
        if not val:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = JsonUtils.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def get_config(self) -> dict:
        db_cfg = self._repo.get_media_config()
        movie_path = (
            self._parse_paths(db_cfg.MOVIE_PATH or "")
            if db_cfg and db_cfg.MOVIE_PATH is not None
            else (self._yaml_fallback.get("movie_path") or [])
        )
        tv_path = (
            self._parse_paths(db_cfg.TV_PATH or "")
            if db_cfg and db_cfg.TV_PATH is not None
            else (self._yaml_fallback.get("tv_path") or [])
        )
        anime_path = (
            self._parse_paths(db_cfg.ANIME_PATH or "")
            if db_cfg and db_cfg.ANIME_PATH is not None
            else (self._yaml_fallback.get("anime_path") or [])
        )
        unknown_path = (
            self._parse_paths(db_cfg.UNKNOWN_PATH or "")
            if db_cfg and db_cfg.UNKNOWN_PATH is not None
            else (self._yaml_fallback.get("unknown_path") or [])
        )
        movie_backend = (
            self._parse_backends(db_cfg.MOVIE_BACKEND or "") if db_cfg and db_cfg.MOVIE_BACKEND is not None else []
        )
        tv_backend = self._parse_backends(db_cfg.TV_BACKEND or "") if db_cfg and db_cfg.TV_BACKEND is not None else []
        anime_backend = (
            self._parse_backends(db_cfg.ANIME_BACKEND or "") if db_cfg and db_cfg.ANIME_BACKEND is not None else []
        )
        unknown_backend = (
            self._parse_backends(db_cfg.UNKNOWN_BACKEND or "") if db_cfg and db_cfg.UNKNOWN_BACKEND is not None else []
        )
        layouts = {
            "movie": self._parse_layout(
                getattr(db_cfg, "MOVIE_LAYOUT", None) if db_cfg else None,
                "movie",
            ),
            "tv": self._parse_layout(
                getattr(db_cfg, "TV_LAYOUT", None) if db_cfg else None,
                "tv",
            ),
            "anime": self._parse_layout(
                getattr(db_cfg, "ANIME_LAYOUT", None) if db_cfg else None,
                "anime",
            ),
        }
        if not db_cfg:
            layouts = {
                "movie": self._parse_layout(self._yaml_fallback.get("movie_layout"), "movie"),
                "tv": self._parse_layout(self._yaml_fallback.get("tv_layout"), "tv"),
                "anime": self._parse_layout(self._yaml_fallback.get("anime_layout"), "anime"),
            }
        return {
            "movie_path": movie_path,
            "tv_path": tv_path,
            "anime_path": anime_path,
            "unknown_path": unknown_path,
            "movie_backend": movie_backend,
            "tv_backend": tv_backend,
            "anime_backend": anime_backend,
            "unknown_backend": unknown_backend,
            "movie_layout": layouts["movie"],
            "tv_layout": layouts["tv"],
            "anime_layout": layouts["anime"],
        }

    def add_path(self, path_type: str, path: str, backend: str = "") -> bool:
        """添加路径"""
        self._repo.add_path(path_type, path, backend)
        return True

    def remove_path(self, path_type: str, path: str) -> bool:
        """移除路径"""
        self._repo.remove_path(path_type, path)
        return True

    def update_path(self, path_type: str, old_path: str, new_path: str, backend: str = "") -> bool:
        """更新路径"""
        self._repo.update_path(path_type, old_path, new_path, backend)
        return True

    def set_config(
        self,
        movie_path: list[str],
        tv_path: list[str],
        anime_path: list[str],
        unknown_path: list[str],
        movie_backend: list[str] | None = None,
        tv_backend: list[str] | None = None,
        anime_backend: list[str] | None = None,
        unknown_backend: list[str] | None = None,
        movie_layout: str = LAYOUT_CATEGORY,
        tv_layout: str = LAYOUT_CATEGORY,
        anime_layout: str = LAYOUT_FLAT,
    ) -> bool:
        """一次性保存整个配置"""
        self._repo.set_media_config(
            movie_path=JsonUtils.dumps(movie_path) if movie_path else "",
            tv_path=JsonUtils.dumps(tv_path) if tv_path else "",
            anime_path=JsonUtils.dumps(anime_path) if anime_path else "",
            unknown_path=JsonUtils.dumps(unknown_path) if unknown_path else "",
            movie_backend=JsonUtils.dumps(movie_backend) if movie_backend else "",
            tv_backend=JsonUtils.dumps(tv_backend) if tv_backend else "",
            anime_backend=JsonUtils.dumps(anime_backend) if anime_backend else "",
            unknown_backend=JsonUtils.dumps(unknown_backend) if unknown_backend else "",
            movie_layout=self._parse_layout(movie_layout, "movie"),
            tv_layout=self._parse_layout(tv_layout, "tv"),
            anime_layout=self._parse_layout(anime_layout, "anime"),
        )
        return True

    def set_layouts(self, movie_layout: str, tv_layout: str, anime_layout: str) -> bool:
        """只更新三类媒体库的目录结构."""
        self._repo.set_media_layouts(
            self._parse_layout(movie_layout, "movie"),
            self._parse_layout(tv_layout, "tv"),
            self._parse_layout(anime_layout, "anime"),
        )
        return True
