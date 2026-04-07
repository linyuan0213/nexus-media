# coding: utf-8
"""
测试模型拆分后的导入是否正确
"""
import pytest


def test_import_base():
    """测试基础类导入"""
    from app.db.models.base import Base, BaseMedia
    assert Base is not None
    assert BaseMedia is not None
    assert Base is BaseMedia  # 应该指向同一个对象


def test_import_config_models():
    """测试配置相关模型导入"""
    from app.db.models.config import (
        CONFIGFILTERGROUP,
        CONFIGFILTERRULES,
        CONFIGRSSPARSER,
        CONFIGSITE,
        CONFIGSYNCPATHS,
        CONFIGUSERS,
        CONFIGUSERRSS,
    )
    assert CONFIGSITE.__tablename__ == 'CONFIG_SITE'
    assert CONFIGUSERS.__tablename__ == 'CONFIG_USERS'


def test_import_word_models():
    """测试自定义识别词模型导入"""
    from app.db.models.word import CUSTOMWORDS, CUSTOMWORDGROUPS
    assert CUSTOMWORDS.__tablename__ == 'CUSTOM_WORDS'
    assert CUSTOMWORDGROUPS.__tablename__ == 'CUSTOM_WORD_GROUPS'


def test_import_download_models():
    """测试下载相关模型导入"""
    from app.db.models.download import DOWNLOADER, DOWNLOADHISTORY, DOWNLOADSETTING
    assert DOWNLOADER.__tablename__ == 'DOWNLOADER'
    assert DOWNLOADHISTORY.__tablename__ == 'DOWNLOAD_HISTORY'


def test_import_message_models():
    """测试消息相关模型导入"""
    from app.db.models.message import MESSAGECLIENT
    assert MESSAGECLIENT.__tablename__ == 'MESSAGE_CLIENT'


def test_import_rss_models():
    """测试RSS相关模型导入"""
    from app.db.models.rss import RSSHISTORY, RSSMOVIES, RSSTORRENTS, RSSTVS, RSSTVEPISODES
    assert RSSHISTORY.__tablename__ == 'RSS_HISTORY'
    assert RSSMOVIES.__tablename__ == 'RSS_MOVIES'
    assert RSSTORRENTS.__tablename__ == 'RSS_TORRENTS'


def test_import_brush_models():
    """测试刷流相关模型导入"""
    from app.db.models.brush import SITEBRUSHTASK, SITEBRUSHTORRENTS
    assert SITEBRUSHTASK.__tablename__ == 'SITE_BRUSH_TASK'


def test_import_site_models():
    """测试站点统计模型导入"""
    from app.db.models.site import (
        SITESTATISTICSHISTORY,
        SITEUSERINFOSTATS,
        SITEFAVICON,
        SITEUSERSEEDINGINFO,
    )
    assert SITESTATISTICSHISTORY.__tablename__ == 'SITE_STATISTICS_HISTORY'


def test_import_transfer_models():
    """测试转移相关模型导入"""
    from app.db.models.transfer import TRANSFERBLACKLIST, TRANSFERHISTORY, TRANSFERUNKNOWN
    assert TRANSFERHISTORY.__tablename__ == 'TRANSFER_HISTORY'


def test_import_indexer_models():
    """测试索引器统计模型导入"""
    from app.db.models.indexer import INDEXERSTATISTICS
    assert INDEXERSTATISTICS.__tablename__ == 'INDEXER_STATISTICS'


def test_import_plugin_models():
    """测试插件历史模型导入"""
    from app.db.models.plugin import PLUGINHISTORY, TMDBBLACKLIST, TORRENTREMOVETASK, USERRSSTASKHISTORY
    assert PLUGINHISTORY.__tablename__ == 'PLUGIN_HISTORY'
    assert TMDBBLACKLIST.__tablename__ == 'TMDB_BLACKLIST'
    assert TORRENTREMOVETASK.__tablename__ == 'TORRENT_REMOVE_TASK'


def test_import_media_sync_models():
    """测试媒体同步模型导入"""
    from app.db.models.media_sync import MEDIASYNCITEMS, MEDIASYNCSTATISTIC
    from app.db.models.base import BaseMedia
    assert MEDIASYNCITEMS.__tablename__ == 'MEDIASYNC_ITEMS'
    # 验证使用 BaseMedia 基类
    assert MEDIASYNCITEMS.__bases__[0] is BaseMedia


def test_import_search_models():
    """测试搜索结果模型导入"""
    from app.db.models.search import SEARCHRESULTINFO
    assert SEARCHRESULTINFO.__tablename__ == 'SEARCH_RESULT_INFO'


def test_import_sync_models():
    """测试同步历史模型导入"""
    from app.db.models.sync import SYNCHISTORY
    assert SYNCHISTORY.__tablename__ == 'SYNC_HISTORY'


def test_import_system_models():
    """测试系统字典模型导入"""
    from app.db.models.system import SYSTEMDICT
    assert SYSTEMDICT.__tablename__ == 'SYSTEM_DICT'


def test_import_from_models_package():
    """测试从 models 包导入所有模型"""
    from app.db.models import (
        Base, BaseMedia,
        CONFIGFILTERGROUP, CONFIGSITE,
        CUSTOMWORDS,
        DOWNLOADER, DOWNLOADHISTORY,
        MESSAGECLIENT,
        RSSHISTORY, RSSMOVIES,
        SITEBRUSHTASK,
        SITESTATISTICSHISTORY,
        TRANSFERHISTORY,
        INDEXERSTATISTICS,
        PLUGINHISTORY, TMDBBLACKLIST, TORRENTREMOVETASK,
        MEDIASYNCITEMS,
        SEARCHRESULTINFO,
        SYNCHISTORY,
        SYSTEMDICT,
    )
    # 验证所有导入的模型都有正确的表名
    assert CONFIGSITE.__tablename__ == 'CONFIG_SITE'
    assert DOWNLOADHISTORY.__tablename__ == 'DOWNLOAD_HISTORY'
    assert MEDIASYNCITEMS.__tablename__ == 'MEDIASYNC_ITEMS'


def test_import_from_compat_layer():
    """测试从兼容层 app/db/models.py 导入"""
    # 这是向后兼容测试，模拟现有的导入方式
    import sys
    import importlib

    # 先移除已缓存的模块，确保重新导入
    modules_to_remove = [k for k in sys.modules.keys() if 'app.db.models' in k]
    for m in modules_to_remove:
        del sys.modules[m]

    # 重新从兼容层导入
    from app.db.models import (
        Base, BaseMedia,
        CONFIGSITE,
        DOWNLOADHISTORY,
        MEDIASYNCITEMS,
        TMDBBLACKLIST,
        TORRENTREMOVETASK,
    )

    assert CONFIGSITE.__tablename__ == 'CONFIG_SITE'
    assert DOWNLOADHISTORY.__tablename__ == 'DOWNLOAD_HISTORY'
    assert TMDBBLACKLIST.__tablename__ == 'TMDB_BLACKLIST'
    assert TORRENTREMOVETASK.__tablename__ == 'TORRENT_REMOVE_TASK'


def test_as_dict_methods():
    """测试模型的 as_dict 方法存在性"""
    from app.db.models.download import DOWNLOADHISTORY
    from app.db.models.rss import RSSHISTORY, RSSMOVIES, RSSTVS
    from app.db.models.brush import SITEBRUSHTORRENTS
    from app.db.models.transfer import TRANSFERHISTORY
    from app.db.models.indexer import INDEXERSTATISTICS
    from app.db.models.plugin import TMDBBLACKLIST

    # 验证有 as_dict 方法的模型
    assert hasattr(DOWNLOADHISTORY, 'as_dict')
    assert hasattr(RSSHISTORY, 'as_dict')
    assert hasattr(RSSMOVIES, 'as_dict')
    assert hasattr(RSSTVS, 'as_dict')
    assert hasattr(SITEBRUSHTORRENTS, 'as_dict')
    assert hasattr(TRANSFERHISTORY, 'as_dict')
    assert hasattr(INDEXERSTATISTICS, 'as_dict')
    assert hasattr(TMDBBLACKLIST, 'as_dict')


def test_model_columns():
    """测试模型列定义"""
    from app.db.models.download import DOWNLOADHISTORY
    from app.db.models.transfer import TRANSFERHISTORY

    # 验证 DOWNLOADHISTORY 的列
    cols = [c.name for c in DOWNLOADHISTORY.__table__.columns]
    assert 'TITLE' in cols
    assert 'ENCLOSURE' in cols
    assert 'DOWNLOAD_ID' in cols
    assert 'SAVE_PATH' in cols
    assert 'DATE' in cols

    # 验证 TRANSFERHISTORY 的列
    cols = [c.name for c in TRANSFERHISTORY.__table__.columns]
    assert 'TITLE' in cols
    assert 'SOURCE_PATH' in cols
    assert 'DEST_PATH' in cols


def test_model_indexes():
    """测试模型索引定义"""
    from app.db.models.site import SITESTATISTICSHISTORY
    from app.db.models.rss import RSSTORRENTS
    from app.db.models.system import SYSTEMDICT

    # 验证复合索引
    assert len(SITESTATISTICSHISTORY.__table_args__) == 2
    assert len(RSSTORRENTS.__table_args__) == 1
    assert len(SYSTEMDICT.__table_args__) == 1
