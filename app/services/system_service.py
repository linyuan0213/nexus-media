# -*- coding: utf-8 -*-
"""
SystemService - 系统管理业务层
将 web/controllers/system.py 中的备份恢复、消息客户端、索引器配置、
媒体服务器配置、网络测试、调度、搜索等业务逻辑下沉到可独立测试的 Service。
"""
import datetime
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple

import log
from app.conf import SystemConfig
from app.db.database_factory import DatabaseFactory
from app.db.migrate import import_from_file, export_database, import_database
from app.db.repositories import ConfigRepository
from app.downloader import Downloader
from app.helper import SubmoduleHelper
from app.helper.thread_helper import ThreadHelper
from app.indexer import Indexer
from app.mediaserver import MediaServer
from app.message import Message
from app.rss import Rss
from app.subscribe import Subscribe
from app.sync import Sync
from app.utils import ExceptionUtils, RequestUtils
from app.utils.types import MediaType, MovieTypes
from app.utils.temp_manager import temp_manager
from config import Config
from sqlalchemy import create_engine
from web.backend.search_torrents import search_medias_for_web
from web.backend.user import User
from web.backend.web_utils import WebUtils
from web.cache import cache


@dataclass
class BackupRestoreResultDTO:
    """备份恢复结果"""
    success: bool = False
    message: str = ""


@dataclass
class NetTestResultDTO:
    """网络测试结果"""
    success: bool = False
    time_ms: int = 0


@dataclass
class IndexerConfigResultDTO:
    """索引器配置保存结果"""
    success: bool = True
    code: int = 0
    msg: str = ""


@dataclass
class MediaServerConfigResultDTO:
    """媒体服务器配置保存结果"""
    success: bool = True
    code: int = 0
    msg: str = ""


@dataclass
class SearchResultDTO:
    """WEB搜索结果"""
    code: int = 0
    msg: str = ""


@dataclass
class VersionInfoDTO:
    """版本信息"""
    version: str = ""
    url: str = ""
    has_update: bool = False


class MessageClientService:
    """
    消息客户端业务服务
    负责消息客户端的增删改查、交互状态管理、连接测试
    """

    def __init__(self, message: Optional[Message] = None):
        self._message = message or Message()

    def delete_client(self, cid: int) -> bool:
        """删除消息客户端"""
        return bool(self._message.delete_message_client(cid=cid))

    def get_client(self, cid: Optional[int] = None):
        """获取消息客户端信息"""
        return self._message.get_message_client_info(cid=cid)

    def toggle_interactive(self, cid: int, ctype: str, checked: bool) -> bool:
        """切换交互状态"""
        if checked:
            # TG/WX只能开启一个交互
            self._message.check_message_client(interactive=0, ctype=ctype)
        self._message.check_message_client(cid=cid, interactive=1 if checked else 0)
        return True

    def toggle_enable(self, cid: int, checked: bool) -> bool:
        """切换启用状态"""
        self._message.check_message_client(cid=cid, enabled=1 if checked else 0)
        return True

    def test_connection(self, ctype: str, config: dict) -> bool:
        """测试消息客户端连接"""
        return self._message.get_status(ctype=ctype, config=config)

    def upsert_client(self, name: str, cid: int, ctype: str, config: str,
                      switchs, interactive: int, enabled: int,
                      templates: str) -> None:
        """添加或更新消息客户端"""
        if cid:
            self._message.delete_message_client(cid=cid)
        if int(interactive) == 1:
            self._message.check_message_client(interactive=0, ctype=ctype)
        self._message.insert_message_client(
            name=name, ctype=ctype, config=config,
            switchs=switchs, interactive=interactive,
            enabled=enabled, templates=templates
        )


class BackupRestoreService:
    """
    备份恢复业务服务
    负责解压备份文件、恢复配置、跨数据库类型导入数据
    """

    def restore_from_backup(self, filename: str) -> BackupRestoreResultDTO:
        """
        从备份文件恢复
        :param filename: 上传的备份文件名
        """
        if not filename:
            return BackupRestoreResultDTO(success=False, message="文件不存在")

        config_path = Config().get_config_path()
        file_path = temp_manager.get_temp_path(filename)
        temp_dir = None

        try:
            # 1. 解压到临时目录
            temp_dir = tempfile.mkdtemp(prefix="restore_")
            shutil.unpack_archive(file_path, temp_dir, format='zip')

            # 2. 恢复配置文件
            for cfg_name in ['config.yaml', 'default-category.yaml']:
                src = os.path.join(temp_dir, cfg_name)
                if os.path.exists(src):
                    shutil.copy(src, config_path)

            # 3. 判断备份中的数据库格式与当前数据库类型
            json_backup = os.path.join(temp_dir, 'user_db_export.json')
            sqlite_backup = os.path.join(temp_dir, 'user.db')

            target_engine = DatabaseFactory.create_engine()

            if os.path.exists(json_backup):
                import_from_file(target_engine, json_backup)
            elif os.path.exists(sqlite_backup):
                source_engine = create_engine(
                    f"sqlite:///{sqlite_backup}?check_same_thread=False"
                )
                migrate_data = export_database(source_engine)
                import_database(target_engine, migrate_data)
                source_engine.dispose()
            else:
                return BackupRestoreResultDTO(success=False, message="备份文件中未找到数据库文件")

            target_engine.dispose()
            return BackupRestoreResultDTO(success=True, message="恢复成功")

        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return BackupRestoreResultDTO(success=False, message=str(e))

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


class IndexerConfigService:
    """
    索引器配置业务服务
    负责保存索引器配置、兼容旧配置迁移、测试连接
    """

    def __init__(self,
                 system_config: Optional[SystemConfig] = None,
                 indexer: Optional[Indexer] = None):
        self._system_config = system_config or SystemConfig()
        self._indexer = indexer or Indexer()

    def save_config(self, data: dict) -> IndexerConfigResultDTO:
        """保存索引器配置"""
        from app.utils.types import SystemConfigKey
        name = data.get("type") or ""
        test = data.get("test") in [True, "true", "on", "1", 1]
        # 兼容旧配置：首次保存时从配置文件迁移
        existing = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
        if name != "builtin" and (not existing or name not in existing):
            old_cfg = Config().get_config(name)
            if old_cfg:
                existing[name] = dict(old_cfg)
        # 提取并保存索引器详细配置
        config = {}
        for key, value in data.items():
            if key.startswith(name + "."):
                config[key.split(".", 1)[1]] = value
        if config:
            existing[name] = config
        if existing:
            self._system_config.set(SystemConfigKey.IndexerConfig, existing)
        # 保存当前使用的索引器
        self._system_config.set(SystemConfigKey.SearchIndexer, name)
        # 保存builtin站点的选中状态
        if name == "builtin":
            sites = data.get("indexer_sites")
            if sites is not None:
                self._system_config.set(SystemConfigKey.UserIndexerSites, sites)
        # 刷新 Indexer 单例配置
        self._indexer.init_config()
        # 测试连接
        if test and name != "builtin":
            try:
                schemas = SubmoduleHelper.import_submodules(
                    'app.indexer.client',
                    filter_func=lambda _, obj: hasattr(obj, 'client_id')
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return IndexerConfigResultDTO(
                            success=True, code=0 if status else 1,
                            msg="测试成功" if status else "测试失败"
                        )
                return IndexerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return IndexerConfigResultDTO(success=False, code=-1, msg=str(e))
        return IndexerConfigResultDTO(success=True)


class MediaServerConfigService:
    """
    媒体服务器配置业务服务
    负责保存媒体服务器配置、测试连接
    """

    def __init__(self,
                 config_repo: Optional[ConfigRepository] = None,
                 media_server: Optional[MediaServer] = None):
        self._config_repo = config_repo or ConfigRepository()
        self._media_server = media_server or MediaServer()

    def save_config(self, data: dict) -> MediaServerConfigResultDTO:
        """保存媒体服务器配置"""
        name = data.get("type") or ""
        test = data.get("test") in [True, "true", "on", "1", 1]
        config = {}
        for key, value in data.items():
            if key.startswith(name + "."):
                config[key.split(".", 1)[1]] = value
        if not config:
            return MediaServerConfigResultDTO(success=False, code=-1, msg="配置为空")
        enabled = 1 if config.get("enabled") else 0
        is_default = 1 if config.get("is_default") else 0
        item = self._config_repo.get_media_server_by_name(name)
        sid = item.ID if item else None
        self._config_repo.update_media_server(
            sid=sid, name=name, enabled=enabled,
            config=json.dumps(config), is_default=is_default
        )
        # 如果有设置默认，需要清理其他默认并同步 ENABLED
        if is_default:
            self._config_repo.set_default_media_server(name)
        # 刷新 MediaServer 单例配置
        self._media_server.init_config()
        cache.delete("index")
        # 测试连接
        if test:
            try:
                schemas = SubmoduleHelper.import_submodules(
                    'app.mediaserver.client',
                    filter_func=lambda _, obj: hasattr(obj, 'client_id')
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return MediaServerConfigResultDTO(
                            success=True, code=0 if status else 1,
                            msg="测试成功" if status else "测试失败"
                        )
                return MediaServerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return MediaServerConfigResultDTO(success=False, code=-1, msg=str(e))
        return MediaServerConfigResultDTO(success=True)


class NetTestService:
    """
    网络连通性测试业务服务
    """

    def test(self, target: str) -> NetTestResultDTO:
        """测试指定目标的网络连通性"""
        if target == "image.tmdb.org":
            target = target + "/t/p/w500/wwemzKWzjKYJFfCeiB57q3r4Bcm.png"
        if target == "qyapi.weixin.qq.com":
            target = target + "/cgi-bin/message/send"
        target = "https://" + target
        start_time = datetime.datetime.now()
        if target.find("themoviedb") != -1 \
                or target.find("telegram") != -1 \
                or target.find("fanart") != -1 \
                or target.find("tmdb") != -1:
            res = RequestUtils(proxies=Config().get_proxies(), timeout=5).get_res(target)
        else:
            res = RequestUtils(timeout=5).get_res(target)
        seconds = int((datetime.datetime.now() - start_time).microseconds / 1000)
        if res and res.ok:
            return NetTestResultDTO(success=True, time_ms=seconds)
        return NetTestResultDTO(success=False, time_ms=seconds)


class SchedulerService:
    """
    系统调度业务服务
    负责启动各种后台服务（下载转移、目录同步、RSS下载、订阅搜索）
    """

    def __init__(self,
                 downloader: Optional[Downloader] = None,
                 sync: Optional[Sync] = None,
                 rss: Optional[Rss] = None,
                 subscribe: Optional[Subscribe] = None,
                 thread_helper: Optional[ThreadHelper] = None):
        self._commands = {
            "pttransfer": (downloader or Downloader()).transfer,
            "sync": (sync or Sync()).transfer_sync,
            "rssdownload": (rss or Rss()).rssdownload,
            "subscribe_search_all": (subscribe or Subscribe()).subscribe_search_all,
        }
        self._thread_helper = thread_helper or ThreadHelper()

    def start_service(self, item: str) -> Tuple[bool, str]:
        """启动指定服务"""
        command = self._commands.get(item)
        if command:
            self._thread_helper.start_thread(command, ())
            return True, "服务已启动"
        return False, "未知服务"


class WebSearchService:
    """
    WEB资源搜索业务服务
    """

    def search(self, search_word: str, ident_flag: bool = True,
               filters=None, tmdbid=None, media_type=None) -> SearchResultDTO:
        """执行WEB搜索"""
        if not search_word:
            return SearchResultDTO(code=0, msg="")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        ret, ret_msg = search_medias_for_web(
            content=search_word, ident_flag=ident_flag,
            filters=filters, tmdbid=tmdbid, media_type=media_type
        )
        return SearchResultDTO(code=ret, msg=ret_msg or "")


class SystemConfigService:
    """
    系统配置业务服务
    """

    def __init__(self, system_config: Optional[SystemConfig] = None):
        self._system_config = system_config or SystemConfig()

    def set_config(self, key: str, value) -> bool:
        """设置系统配置项"""
        if not key or not value:
            return False
        self._system_config.set(key=key, value=value)
        return True


class VersionService:
    """
    版本检查业务服务
    """

    @staticmethod
    def get_latest_version() -> VersionInfoDTO:
        """获取最新版本信息"""
        version, url, flag = WebUtils.get_latest_version()
        if flag:
            return VersionInfoDTO(
                version=version or "", url=url or "", has_update=True
            )
        return VersionInfoDTO(version="", url="", has_update=False)
