"""
媒体订阅工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._media_subscribe 处理

支持添加电影/电视剧/动漫的 RSS 订阅，有新资源时自动下载
"""

from app.agent.tools.base import BaseTool, ToolRegistry


class MediaSubscribeTool(BaseTool):
    """媒体订阅工具"""

    name = "media_subscribe"
    description = "添加媒体订阅（RSS 订阅），有新资源时自动下载。支持电影、电视剧、动漫订阅。"
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "媒体标题（必填）",
            },
            "media_type": {
                "type": "string",
                "enum": ["movie", "tv", "anime"],
                "description": "媒体类型（必填）",
            },
            "year": {
                "type": "integer",
                "description": "年份（可选，提高识别准确度）",
            },
            "season": {
                "type": "integer",
                "description": "季号（剧集类可选，默认全部季）",
            },
            "tmdbid": {
                "type": "string",
                "description": "TMDB ID（可选，有则直接订阅，无则自动识别）",
            },
        },
        "required": ["title", "media_type"],
    }

    def execute(self, **kwargs):
        raise NotImplementedError("media_subscribe 应由 ToolExecutor 执行")


ToolRegistry.register(MediaSubscribeTool())
