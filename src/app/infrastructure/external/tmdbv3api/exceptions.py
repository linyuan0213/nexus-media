"""
兼容旧导入路径：app.infrastructure.external.tmdbv3api.exceptions.TMDbError
实际定义已迁移至 app.core.exceptions.TMDBError
"""

from app.core.exceptions import TMDBError as TMDbError

__all__ = ["TMDbError"]
