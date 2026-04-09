# coding: utf-8
"""
数据库模型模块

此模块包含所有数据库模型定义，按业务域拆分为多个子模块。
"""

# 基础定义
from app.db.models.base import Base, BaseMedia

# 配置相关模型
from app.db.models.config import (
    CONFIGFILTERGROUP,
    CONFIGFILTERRULES,
    CONFIGRSSPARSER,
    CONFIGSITE,
    CONFIGSYNCPATHS,
    CONFIGUSERS,
    CONFIGUSERRSS,
)

# 自定义识别词模型
from app.db.models.word import (
    CUSTOMWORDS,
    CUSTOMWORDGROUPS,
)

# 下载相关模型
from app.db.models.download import (
    DOWNLOADER,
    DOWNLOADHISTORY,
    DOWNLOADSETTING,
)

# 消息相关模型
from app.db.models.message import (
    MESSAGECLIENT,
)

# RSS相关模型
from app.db.models.rss import (
    RSSHISTORY,
    RSSMOVIES,
    RSSTORRENTS,
    RSSTVS,
    RSSTVEPISODES,
)

# 刷流相关模型
from app.db.models.brush import (
    SITEBRUSHTASK,
    SITEBRUSHTORRENTS,
)

# 站点统计模型
from app.db.models.site import (
    SITESTATISTICSHISTORY,
    SITEUSERINFOSTATS,
    SITEFAVICON,
    SITEUSERSEEDINGINFO,
)

# 转移相关模型
from app.db.models.transfer import (
    TRANSFERBLACKLIST,
    TRANSFERHISTORY,
    TRANSFERUNKNOWN,
)

# 索引器统计模型
from app.db.models.indexer import (
    INDEXERSTATISTICS,
)

# 插件历史和TMDB黑名单模型
from app.db.models.plugin import (
    PLUGINHISTORY,
    TMDBBLACKLIST,
    TORRENTREMOVETASK,
    USERRSSTASKHISTORY,
)

# 媒体同步模型
from app.db.models.media_sync import (
    MEDIASYNCITEMS,
    MEDIASYNCSTATISTIC,
)

# 搜索结果模型
from app.db.models.search import (
    SEARCHRESULTINFO,
)

# 同步历史模型
from app.db.models.sync import (
    SYNCHISTORY,
)

# 系统字典模型
from app.db.models.system import (
    SYSTEMDICT,
)

# RBAC权限管理模型
from app.db.models.rbac import (
    RBACUser,
    RBACRole,
    RBACPermission,
    RBACMenu,
    RBACUserLoginLog,
    RBACOperationLog,
)

__all__ = [
    # 基础
    'Base',
    'BaseMedia',
    # 配置
    'CONFIGFILTERGROUP',
    'CONFIGFILTERRULES',
    'CONFIGRSSPARSER',
    'CONFIGSITE',
    'CONFIGSYNCPATHS',
    'CONFIGUSERS',
    'CONFIGUSERRSS',
    # 识别词
    'CUSTOMWORDS',
    'CUSTOMWORDGROUPS',
    # 下载
    'DOWNLOADER',
    'DOWNLOADHISTORY',
    'DOWNLOADSETTING',
    # 消息
    'MESSAGECLIENT',
    # RSS
    'RSSHISTORY',
    'RSSMOVIES',
    'RSSTORRENTS',
    'RSSTVS',
    'RSSTVEPISODES',
    # 刷流
    'SITEBRUSHTASK',
    'SITEBRUSHTORRENTS',
    # 站点统计
    'SITESTATISTICSHISTORY',
    'SITEUSERINFOSTATS',
    'SITEFAVICON',
    'SITEUSERSEEDINGINFO',
    # 转移
    'TRANSFERBLACKLIST',
    'TRANSFERHISTORY',
    'TRANSFERUNKNOWN',
    # 索引器
    'INDEXERSTATISTICS',
    # 插件
    'PLUGINHISTORY',
    'TMDBBLACKLIST',
    'TORRENTREMOVETASK',
    'USERRSSTASKHISTORY',
    # 媒体同步
    'MEDIASYNCITEMS',
    'MEDIASYNCSTATISTIC',
    # 搜索
    'SEARCHRESULTINFO',
    # 同步
    'SYNCHISTORY',
    # 系统
    'SYSTEMDICT',
    # RBAC权限管理
    'RBACUser',
    'RBACRole',
    'RBACPermission',
    'RBACMenu',
    'RBACUserLoginLog',
    'RBACOperationLog',
]
