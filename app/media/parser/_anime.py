"""
动漫标题解析 — 兼容导出（已拆分到 anime/ 子包）
"""

from app.media.parser.anime import parse_anime_title

__all__ = ["parse_anime_title"]
