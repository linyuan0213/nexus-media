# -*- coding: utf-8 -*-
"""媒体路径配置服务 — 从数据库读取，兼容 YAML 回退"""
import json
from typing import List, Optional

from app.db.repositories.config_repo_adapter import MediaConfigRepositoryAdapter
from config import Config


class MediaConfigService:
    """媒体库路径配置服务"""

    def __init__(self, repo: Optional[MediaConfigRepositoryAdapter] = None):
        self._repo = repo or MediaConfigRepositoryAdapter()
        self._yaml_fallback = Config().get_config("media") or {}

    @staticmethod
    def _parse_paths(val) -> List[str]:
        if not val:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else [parsed]
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def get_config(self) -> dict:
        db_cfg = self._repo.get_media_config()
        return {
            "movie_path": self._parse_paths(db_cfg.MOVIE_PATH) if db_cfg and db_cfg.MOVIE_PATH else (self._yaml_fallback.get("movie_path") or []),
            "tv_path": self._parse_paths(db_cfg.TV_PATH) if db_cfg and db_cfg.TV_PATH else (self._yaml_fallback.get("tv_path") or []),
            "anime_path": self._parse_paths(db_cfg.ANIME_PATH) if db_cfg and db_cfg.ANIME_PATH else (self._yaml_fallback.get("anime_path") or []),
            "unknown_path": self._parse_paths(db_cfg.UNKNOWN_PATH) if db_cfg and db_cfg.UNKNOWN_PATH else (self._yaml_fallback.get("unknown_path") or []),
        }

    def add_path(self, path_type: str, path: str) -> bool:
        """添加路径"""
        self._repo.add_path(path_type, path)
        return True

    def remove_path(self, path_type: str, path: str) -> bool:
        """移除路径"""
        self._repo.remove_path(path_type, path)
        return True

    def update_path(self, path_type: str, old_path: str, new_path: str) -> bool:
        """更新路径"""
        self._repo.update_path(path_type, old_path, new_path)
        return True

    def set_config(self, movie_path: List[str], tv_path: List[str],
                   anime_path: List[str], unknown_path: List[str]) -> bool:
        """一次性保存整个配置"""
        self._repo.set_media_config(
            movie_path=json.dumps(movie_path) if movie_path else '',
            tv_path=json.dumps(tv_path) if tv_path else '',
            anime_path=json.dumps(anime_path) if anime_path else '',
            unknown_path=json.dumps(unknown_path) if unknown_path else '',
        )
        return True
