# -*- coding: utf-8 -*-
"""
app.media — 媒体处理模块统一公共接口

提供媒体识别、元数据查询、刮削、分类等功能。
所有外部模块应通过此入口导入，不要直接导入子模块。

公共 API：
  - Media           — 媒体识别与 TMDB/豆瓣/Bangumi 查询
  - MetaInfo        — 综合媒体元信息对象
  - MetaBase        — 媒体元信息基类
  - MetaVideo       — 视频元信息
  - MetaAnime       — 动漫元信息
  - Category        — 媒体分类与目录结构
  - DouBan          — 豆瓣数据源
  - Bangumi         — Bangumi 数据源
  - Scraper         — 媒体刮削（NFO/海报）
  - ReleaseGroupsMatcher — 制作组/字幕组匹配器
  - CustomizationMatcher  — 定制化名称匹配器
"""
from .category import Category
from .media import Media
from .scraper import Scraper
from .douban import DouBan
from .bangumi import Bangumi
from .meta import (
    MetaInfo,
    MetaBase,
    MetaVideo,
    MetaAnime,
    ReleaseGroupsMatcher,
    CustomizationMatcher,
)

__all__ = [
    "Media",
    "MetaInfo",
    "MetaBase",
    "MetaVideo",
    "MetaAnime",
    "Category",
    "DouBan",
    "Bangumi",
    "Scraper",
    "ReleaseGroupsMatcher",
    "CustomizationMatcher",
]
