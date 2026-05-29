"""
媒体搜索工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._media_search 处理
"""

from app.agent.tools.base import BaseTool, ToolRegistry


class MediaSearchTool(BaseTool):
    """媒体搜索工具"""

    name = "media_search"
    description = "搜索媒体资源（电影/电视剧/动漫），支持自然语言查询"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，可以是自然语言或关键词",
            },
            "media_type": {
                "type": "string",
                "enum": ["movie", "tv", "anime", ""],
                "description": "媒体类型过滤",
            },
            "year": {"type": "integer", "description": "年份过滤"},
            "season": {"type": "integer", "description": "季号"},
            "episode": {"type": "integer", "description": "集号"},
            "limit": {"type": "integer", "description": "返回结果数量上限", "default": 10},
        },
        "required": ["query"],
    }

    def execute(self, **kwargs):
        raise NotImplementedError("media_search 应由 ToolExecutor 执行")


ToolRegistry.register(MediaSearchTool())
