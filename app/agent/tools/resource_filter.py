"""
资源过滤工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._resource_filter 处理
"""
from app.agent.tools.base import BaseTool, ToolRegistry


class ResourceFilterTool(BaseTool):
    """资源过滤工具"""

    name = "resource_filter"
    description = "对搜索结果进行过滤和排序，支持按站点、大小、做种数、质量等条件筛选"
    parameters = {
        "type": "object",
        "properties": {
            "resources": {
                "type": "array",
                "description": "要过滤的资源列表",
            },
            "min_seeders": {"type": "integer", "description": "最小做种数"},
            "max_size_gb": {"type": "number", "description": "最大文件大小（GB）"},
            "sites": {"type": "array", "items": {"type": "string"}, "description": "允许的站点列表"},
            "exclude_sites": {"type": "array", "items": {"type": "string"}, "description": "排除的站点列表"},
            "sort_by": {"type": "string", "enum": ["seeders", "size", "site"], "default": "seeders"},
            "preferred_qualities": {"type": "array", "items": {"type": "string"}, "description": "偏好的质量列表"},
        },
        "required": ["resources"],
    }

    def execute(self, **kwargs):
        raise NotImplementedError("resource_filter 应由 ToolExecutor 执行")


ToolRegistry.register(ResourceFilterTool())
