from app.utils import RequestUtils
from app.utils.cache_system import cached, MemoryCacheAdapter

# 创建插件统计缓存
_plugin_stats_cache = MemoryCacheAdapter(maxsize=1, name="plugin_stats")


class PluginHelper:

    @staticmethod
    def install(plugin_id):
        """
        插件安装统计计数
        """
        return None

    @staticmethod
    def report(plugins):
        """
        批量上报插件安装统计数据
        """
        return None

    @staticmethod
    @cached(cache_instance=_plugin_stats_cache, ttl=3600)
    def statistic():
        """
        获取插件安装统计数据
        """
        return {}
