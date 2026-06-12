"""MediaImageResolver — 媒体图片 URL 解析工具

从 MediaInfo 模型中剥离的图片业务逻辑，避免领域模型依赖外部服务。
"""

from app.core.constants import DEFAULT_TMDB_IMAGE


class MediaImageResolver:
    """提供媒体图片 URL 的解析规则，纯工具类，无外部依赖。"""

    @staticmethod
    def get_backdrop_image(media, default=True, original=False):
        """获取背景图 URL。"""
        if media.fanart_backdrop:
            return media.fanart_backdrop
        if media.backdrop_path:
            if original:
                return media.backdrop_path.replace("/w500", "/original")
            return media.backdrop_path
        return DEFAULT_TMDB_IMAGE if default else ""

    @staticmethod
    def get_message_image(media):
        """获取消息通知用图片 URL（优先 backdrop，fallback 到 poster / 默认图）。"""
        if media.fanart_backdrop:
            return media.fanart_backdrop
        if media.backdrop_path:
            return media.backdrop_path
        if media.poster_path:
            return media.poster_path
        return DEFAULT_TMDB_IMAGE

    @staticmethod
    def get_poster_image(media, original=False):
        """获取海报图 URL。"""
        if media.poster_path:
            if original:
                return media.poster_path.replace("/w500", "/original")
            return media.poster_path
        return media.fanart_poster or ""
