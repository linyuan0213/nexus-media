# -*- coding: utf-8 -*-
"""
媒体元信息 Pydantic 数据模型

替代 MetaBase 中的动态属性设置，提供类型安全和数据验证。
所有字段使用 Optional/默认值以保持向后兼容。
"""
from typing import Optional, List, Dict, Any, Union

from pydantic import BaseModel, Field

from app.utils.types import MediaType


class MediaInfoModel(BaseModel):
    """
    媒体元信息数据模型

    所有字段均可选，保持与原始 MetaBase 动态属性的兼容性。
    解析器（MetaVideo/MetaAnime）填充此模型的字段。
    """

    model_config = {"extra": "allow"}

    # ---- 识别相关 ----
    fileflag: bool = False
    org_string: Optional[str] = None
    rev_string: Optional[str] = None
    subtitle: Optional[str] = None
    type: Optional[MediaType] = None

    # ---- 名称 ----
    cn_name: Optional[str] = None
    en_name: Optional[str] = None
    _name: Optional[str] = None

    # ---- 季/集 ----
    total_seasons: int = 0
    begin_season: Optional[int] = None
    end_season: Optional[int] = None
    total_episodes: int = 0
    begin_episode: Optional[int] = None
    end_episode: Optional[int] = None
    part: Optional[str] = None

    # ---- 资源信息 ----
    resource_type: Optional[str] = None
    resource_effect: Optional[str] = None
    resource_pix: Optional[str] = None
    resource_team: Optional[str] = None
    customization: Optional[str] = None
    video_encode: Optional[str] = None
    audio_encode: Optional[str] = None

    # ---- 分类 ----
    category: str = ""

    # ---- TMDB/IMDB/豆瓣 ID ----
    tmdb_id: Union[int, str] = 0
    imdb_id: str = ""
    tvdb_id: int = 0
    douban_id: Union[int, str] = 0

    # ---- 媒体信息 ----
    keyword: Optional[str] = None
    title: Optional[str] = None
    original_language: Optional[str] = None
    original_title: Optional[str] = None
    release_date: Optional[str] = None
    networks: Optional[List[str]] = None
    runtime: int = 0
    year: Optional[str] = None

    # ---- 图片 ----
    backdrop_path: Optional[str] = None
    poster_path: Optional[str] = None
    fanart_backdrop: Optional[str] = None
    fanart_poster: Optional[str] = None

    # ---- 评分/概述 ----
    vote_average: float = 0.0
    overview: Optional[str] = None

    # ---- TMDB 完整信息 ----
    tmdb_info: Dict[str, Any] = Field(default_factory=dict)

    # ---- 本地状态 ----
    fav: str = "0"
    rss_sites: List[str] = Field(default_factory=list)
    search_sites: List[str] = Field(default_factory=list)

    # ---- 种子附加信息 ----
    site: Optional[str] = None
    site_order: int = 0
    user_name: Optional[str] = None
    enclosure: Optional[str] = None
    res_order: int = 0
    filter_rule: Optional[str] = None
    over_edition: Optional[bool] = None
    size: int = 0
    seeders: int = 0
    peers: int = 0
    description: Optional[str] = None
    page_url: Optional[str] = None
    upload_volume_factor: Optional[float] = None
    download_volume_factor: Optional[float] = None
    hit_and_run: Optional[bool] = None
    labels: Optional[str] = None

    # ---- 订阅/下载 ----
    rssid: Optional[str] = None
    save_path: Optional[str] = None
    download_setting: Optional[Any] = None

    # ---- 识别辅助 ----
    ignored_words: Optional[Any] = None
    replaced_words: Optional[Any] = None
    offset_words: Optional[Any] = None

    # ---- 备注 ----
    note: Dict[str, Any] = Field(default_factory=dict)

    # ---- 类级别共享（非实例字段） ----
    proxies: Optional[Any] = None
