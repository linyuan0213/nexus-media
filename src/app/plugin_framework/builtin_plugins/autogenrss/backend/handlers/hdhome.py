"""HDHome 特殊 RSS 生成处理器。"""

from app.plugin_framework.context import PluginContext

from ._form import FormRssGenHandler


class HDHome(FormRssGenHandler):
    """HDHome RSS 生成处理器。"""

    site_id = "HDHome"

    def __init__(self, plugin_ctx: PluginContext, rate_limiter, site_repo, config: dict | None = None):
        merged_config = {
            "path": "getrss.php",
            "method": "post",
            "data": {
                "inclbookmarked": "0",
                "itemcategory": "1",
                "itemsmalldescr": "1",
                "itemsize": "1",
                "showrows": "50",
                "search": "",
                "search_mode": "1",
                "exp": "180",
            },
        }
        if config:
            merged_config.update(config)
        super().__init__(plugin_ctx, rate_limiter, site_repo, merged_config)
