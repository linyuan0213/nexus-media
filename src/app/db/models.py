"""
数据库模型兼容层

此文件作为兼容层保留，从新的 models 子模块导入所有模型。
所有现有导入 `from app.db.models import XXX` 将继续正常工作。

模型文件已按业务域拆分为多个子模块，位于 app/db/models/ 目录下：
- base.py: Base 和 BaseMedia 基类
- config.py: 配置相关模型
- word.py: 自定义识别词模型
- download.py: 下载相关模型
- message.py: 消息相关模型
- rss.py: RSS相关模型
- brush.py: 刷流相关模型
- site.py: 站点统计模型
- transfer.py: 转移相关模型
- indexer.py: 索引器统计模型
- plugin.py: 插件历史和识别黑名单
- media_sync.py: 媒体同步模型
- search.py: 搜索结果模型
- sync.py: 同步历史模型
- system.py: 系统字典模型
"""

# 从新的子模块导入所有模型，保持向后兼容
from app.db.models import (
    AGENTPENDINGACTION,
    AGENTTURN,
    # 配置
    CONFIGFILTERGROUP,
    CONFIGFILTERRULES,
    CONFIGRSSPARSER,
    CONFIGSITE,
    CONFIGSYNCPATHS,
    CONFIGUSERRSS,
    CONFIGUSERS,
    CUSTOMWORDGROUPS,
    # 识别词
    CUSTOMWORDS,
    # 下载
    DOWNLOADER,
    DOWNLOADHISTORY,
    DOWNLOADSETTING,
    # 索引器
    INDEXERSTATISTICS,
    MEDIASYNCITEMS,
    MEDIASYNCSTATISTIC,
    # 消息
    MESSAGECLIENT,
    METADATABLACKLIST,
    # 插件
    PLUGINHISTORY,
    # 搜索
    SEARCHRESULTINFO,
    # 刷流
    SITEBRUSHTASK,
    SITEBRUSHTORRENTS,
    SITEFAVICON,
    # 站点统计
    SITESTATISTICSHISTORY,
    SITEUSERINFOSTATS,
    SITEUSERSEEDINGINFO,
    # 同步
    SYNCHISTORY,
    # 系统
    SYSTEMDICT,
    TORRENTREMOVETASK,
    # 转移
    TRANSFERBLACKLIST,
    TRANSFERHISTORY,
    TRANSFERUNKNOWN,
    USERRSSTASKHISTORY,
    # 基础
    Base,
    BaseMedia,
    # RSS
    CustomRssSource,
    # 媒体同步
    MediaLibraryRoute,
    SubscribeHistory,
    SubscribeMovies,
    SubscribeTorrents,
    SubscribeTvEpisodes,
    SubscribeTvs,
)

# 保持向后兼容的 __all__ 定义
__all__ = [
    # 基础
    "Base",
    "BaseMedia",
    "AGENTPENDINGACTION",
    "AGENTTURN",
    # 配置
    "CONFIGFILTERGROUP",
    "CONFIGFILTERRULES",
    "CONFIGRSSPARSER",
    "CONFIGSITE",
    "CONFIGSYNCPATHS",
    "CONFIGUSERS",
    "CONFIGUSERRSS",
    # 识别词
    "CUSTOMWORDS",
    "CUSTOMWORDGROUPS",
    # 下载
    "DOWNLOADER",
    "DOWNLOADHISTORY",
    "DOWNLOADSETTING",
    # 消息
    "MESSAGECLIENT",
    # RSS
    "CustomRssSource",
    "SubscribeHistory",
    "SubscribeMovies",
    "SubscribeTorrents",
    "SubscribeTvs",
    "SubscribeTvEpisodes",
    # 刷流
    "SITEBRUSHTASK",
    "SITEBRUSHTORRENTS",
    # 站点统计
    "SITESTATISTICSHISTORY",
    "SITEUSERINFOSTATS",
    "SITEFAVICON",
    "SITEUSERSEEDINGINFO",
    # 转移
    "TRANSFERBLACKLIST",
    "TRANSFERHISTORY",
    "TRANSFERUNKNOWN",
    # 索引器
    "INDEXERSTATISTICS",
    # 插件
    "PLUGINHISTORY",
    "METADATABLACKLIST",
    "TORRENTREMOVETASK",
    "USERRSSTASKHISTORY",
    # 媒体同步
    "MediaLibraryRoute",
    "MEDIASYNCITEMS",
    "MEDIASYNCSTATISTIC",
    # 搜索
    "SEARCHRESULTINFO",
    # 同步
    "SYNCHISTORY",
    # 系统
    "SYSTEMDICT",
]
