"""刮削器 — 媒体库文件遍历与 NFO 信息读取"""

import os

from app.core.constants import RMT_MEDIAEXT
from app.utils import NfoReader


class MediaLibrary:
    """媒体库工具 — 遍历文件、从 NFO 提取 TMDB ID"""

    @staticmethod
    def get_library_files(in_path, exclude_path=None):
        """获取媒体库文件列表（生成器）"""
        if not os.path.isdir(in_path):
            yield in_path
            return
        for root, dirs, files in os.walk(in_path):
            if exclude_path and any(
                os.path.abspath(root).startswith(os.path.abspath(path)) for path in exclude_path.split(",")
            ):
                continue
            for file in files:
                cur_path = os.path.join(root, file)
                if os.path.splitext(file)[-1].lower() in RMT_MEDIAEXT:
                    yield cur_path

    @staticmethod
    def get_tmdbid_from_nfo(file_path):
        """从 nfo 文件中获取 TMDB ID"""
        if not file_path:
            return None
        xpaths = ["uniqueid[@type='Tmdb']", "uniqueid[@type='tmdb']", "uniqueid[@type='TMDB']", "tmdbid"]
        reader = NfoReader(file_path)
        for xpath in xpaths:
            try:
                tmdbid = reader.get_element_value(xpath)
                if tmdbid:
                    return tmdbid
            except Exception:
                pass
        return None
