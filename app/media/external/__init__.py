"""app.media.external — 外部媒体 API 客户端

基础设施层：直接调用第三方 API（Bangumi、豆瓣等）
"""
from .bangumi import Bangumi
from .douban import DouBan

__all__ = ["Bangumi", "DouBan"]
