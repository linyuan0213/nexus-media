"""刮削器 — 媒体库文件遍历与 NFO 信息读取"""

import os

from app.core.constants import RMT_MEDIAEXT
from app.storage.backends.base import StorageBackend
from app.utils import NfoReader


class MediaLibrary:
    """媒体库工具 — 遍历文件、从 NFO 提取 TMDB ID"""

    @staticmethod
    def get_library_files(in_path, exclude_path=None, backend: StorageBackend | None = None):
        """获取媒体库文件列表（生成器）"""
        if backend is not None:
            yield from MediaLibrary._get_library_files_remote(in_path, exclude_path, backend)
            return
        if not os.path.isdir(in_path):
            yield in_path
            return
        for root, _dirs, files in os.walk(in_path):
            if exclude_path and any(
                os.path.abspath(root).startswith(os.path.abspath(path)) for path in exclude_path.split(",")
            ):
                continue
            for file in files:
                cur_path = os.path.join(root, file)
                if os.path.splitext(file)[-1].lower() in RMT_MEDIAEXT:
                    yield cur_path

    @staticmethod
    def _get_library_files_remote(in_path, exclude_path, backend: StorageBackend):
        """远程后端文件遍历（递归）"""
        if exclude_path and any(in_path.startswith(path.strip()) for path in exclude_path.split(",")):
            return
        # 优先用 stat 判断；stat 失败但 exists 成功时按扩展名推断
        try:
            info = backend.stat(in_path)
        except Exception:
            info = None
        if info is not None:
            if not info.is_dir:
                yield in_path
            return
        if os.path.splitext(in_path)[-1].lower() in RMT_MEDIAEXT and backend.exists(in_path):
            yield in_path
            return
        try:
            for fi in backend.list_dir(in_path or "/"):
                cur_path = fi.path
                if exclude_path and any(cur_path.startswith(path.strip()) for path in exclude_path.split(",")):
                    continue
                if fi.is_dir:
                    yield from MediaLibrary._get_library_files_remote(cur_path, exclude_path, backend)
                elif os.path.splitext(cur_path)[-1].lower() in RMT_MEDIAEXT:
                    yield cur_path
        except Exception:
            pass

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

    @staticmethod
    def get_tmdbid_from_nfo_remote(file_path, backend: StorageBackend):
        """从远程后端 nfo 文件中获取 TMDB ID"""
        if not file_path:
            return None
        try:
            stream = backend.read_stream(file_path)
            content = stream.read()
            stream.close()
            from io import BytesIO
            from lxml import etree

            root = etree.parse(BytesIO(content)).getroot()
            xpaths = ["uniqueid[@type='Tmdb']", "uniqueid[@type='tmdb']", "uniqueid[@type='TMDB']", "tmdbid"]
            for xp in xpaths:
                try:
                    elem = root.find(xp)
                    if elem is not None and elem.text:
                        return elem.text.strip()
                except Exception:
                    pass
        except Exception:
            pass
        return None
