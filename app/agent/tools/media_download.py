"""
媒体下载工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._media_download 处理

支持两种模式：
1. 直接下载：传入 enclosure（种子链接）
2. 搜索后下载：传入标题和类型，自动搜索并下载最佳资源
"""
from app.agent.tools.base import BaseTool, ToolRegistry


class MediaDownloadTool(BaseTool):
    """媒体下载工具"""

    name = "media_download"
    description = (
        "下载媒体资源（电影/电视剧/动漫）。"
        "模式1-直接下载：提供 enclosure 种子链接；"
        "模式2-搜索下载：提供标题和类型，自动搜索并下载最佳资源。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "媒体标题（模式2必填）",
            },
            "media_type": {
                "type": "string",
                "enum": ["movie", "tv", "anime"],
                "description": "媒体类型（模式2必填）",
            },
            "year": {
                "type": "integer",
                "description": "年份（模式2可选，提高识别准确度）",
            },
            "enclosure": {
                "type": "string",
                "description": "种子/磁力链接（模式1直接下载时使用）",
            },
            "site": {
                "type": "string",
                "description": "资源来源站点（模式1时提供）",
            },
            "size": {
                "type": "string",
                "description": "资源大小描述（模式1时提供）",
            },
            "season": {
                "type": "integer",
                "description": "季号（剧集类可选）",
            },
            "episode": {
                "type": "integer",
                "description": "集号（剧集类可选）",
            },
        },
    }

    def execute(self, **kwargs):
        raise NotImplementedError("media_download 应由 ToolExecutor 执行")


ToolRegistry.register(MediaDownloadTool())
