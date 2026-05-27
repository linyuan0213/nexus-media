"""
SystemService - 系统管理业务层
将 web/controllers/system.py 与 app/system_service.py 中的系统逻辑下沉到可独立测试的 Service。
"""

import datetime
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import cast

import psutil
from sqlalchemy import create_engine

import log
from app.core.system_config import SystemConfig
from app.db.database_factory import DatabaseFactory
from app.db.migrate import export_database, import_database, import_from_file
from app.db.repositories.config_repo_adapter import MediaServerRepositoryAdapter
from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.helper import ProgressHelper, SubmoduleHelper
from app.helper.thread_helper import ThreadHelper
from app.infrastructure.cache_system import TokenCache
from app.mediaserver import MediaServer
from app.message import Message, MessageCenter
from app.message.commands import COMMANDS
from app.plugin_framework.event_compat import EventManager
from app.schemas.system import (
    BackupRestoreResultDTO,
    ConfigUpdateResultDTO,
    IndexerConfigResultDTO,
    MediaServerConfigResultDTO,
    NetTestResultDTO,
    ProgressResultDTO,
    SendMessageResultDTO,
    SystemInfoDTO,
    UserManageResultDTO,
    VersionInfoDTO,
    WebSearchResultDTO,
)
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.indexer_service import IndexerService
from app.services.rss_core import Rss
from app.services.search_web_service import search_medias_for_web
from app.services.subscribe_service import SubscribeService as Subscribe
from app.services.sync_engine import SyncEngine as Sync
from app.services.torrentremover_core import TorrentRemoverService as TorrentRemover
from app.sites.site_userinfo import SiteUserInfo
from app.utils import ExceptionUtils, RequestUtils
from app.utils.config_tools import get_proxies
from app.utils.temp_manager import temp_manager
from app.utils.types import EventType, MediaType, MovieTypes, ProgressKey, SearchType
from app.utils.web_utils import WebUtils
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from version import APP_VERSION


class MessageClientService:
    """
    消息客户端业务服务
    负责消息客户端的增删改查、交互状态管理、连接测试
    """

    def __init__(self, message: Message | None = None):
        self._message = message or Message()

    def delete_client(self, cid: int) -> bool:
        """删除消息客户端"""
        return bool(self._message.delete_message_client(cid=cid))

    def get_client(self, cid: int | None = None):
        """获取消息客户端信息"""
        return self._message.get_message_client_info(cid=cid)

    def toggle_interactive(self, cid: int, ctype: str, checked: bool) -> bool:
        """切换交互状态"""
        if checked:
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

    def upsert_client(
        self, name: str, cid: int, ctype: str, config: str, switchs, interactive: int, enabled: int, templates: str
    ) -> None:
        """添加或更新消息客户端"""
        # 统一 switchs 为 list
        parsed_switchs = switchs
        if isinstance(switchs, str):
            try:
                parsed_switchs = json.loads(switchs)
                if not isinstance(parsed_switchs, list):
                    parsed_switchs = []
            except json.JSONDecodeError:
                parsed_switchs = [s.strip() for s in switchs.split(",") if s.strip()]
        if not isinstance(parsed_switchs, list):
            parsed_switchs = []
        if cid:
            self._message.delete_message_client(cid=cid)
        if int(interactive) == 1:
            self._message.check_message_client(interactive=0, ctype=ctype)
        self._message.insert_message_client(
            name=name,
            ctype=ctype,
            config=config,
            switchs=parsed_switchs,
            interactive=interactive,
            enabled=enabled,
            templates=templates,
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

        config_path = settings.config_path
        file_path = temp_manager.get_temp_path(filename)
        temp_dir = None

        try:
            # 1. 解压到临时目录
            temp_dir = tempfile.mkdtemp(prefix="restore_")
            shutil.unpack_archive(file_path, temp_dir, format="zip")

            # 2. 恢复配置文件
            for cfg_name in ["config.yaml", "default-category.yaml"]:
                src = os.path.join(temp_dir, cfg_name)
                if os.path.exists(src):
                    shutil.copy(src, config_path)

            # 3. 判断备份中的数据库格式与当前数据库类型
            json_backup = os.path.join(temp_dir, "user_db_export.json")
            sqlite_backup = os.path.join(temp_dir, "user.db")

            target_engine = DatabaseFactory.create_engine()

            if os.path.exists(json_backup):
                import_from_file(target_engine, json_backup)
            elif os.path.exists(sqlite_backup):
                source_engine = create_engine(f"sqlite:///{sqlite_backup}?check_same_thread=False")
                migrate_data = export_database(source_engine)
                import_database(target_engine, migrate_data)
                source_engine.dispose()
            else:
                return BackupRestoreResultDTO(success=False, message="备份文件中未找到数据库文件")

            target_engine.dispose()
            return BackupRestoreResultDTO(success=True, message="恢复成功")

        except (ServiceError, RepositoryError, DomainError):
            raise
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

    def __init__(self, system_config: SystemConfig | None = None, indexer_service: IndexerService | None = None):
        self._system_config = system_config or SystemConfig()
        self._indexer_service = indexer_service or IndexerService()

    def save_config(self, data: dict) -> IndexerConfigResultDTO:
        """保存索引器配置"""
        from app.utils.types import SystemConfigKey

        name = data.get("type") or ""
        test = data.get("test") in [True, "true", "on", "1", 1]
        # 兼容旧配置：首次保存时从配置文件迁移
        existing = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
        if name != "builtin" and (not existing or name not in existing):
            old_cfg = settings.get(name)
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
        self._indexer_service.init_config()
        # 测试连接
        if test and name != "builtin":
            try:
                schemas = SubmoduleHelper.import_submodules(
                    "app.indexer.client", filter_func=lambda _, obj: hasattr(obj, "client_id")
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return IndexerConfigResultDTO(
                            success=True, code=0 if status else 1, msg="测试成功" if status else "测试失败"
                        )
                return IndexerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return IndexerConfigResultDTO(success=False, code=-1, msg=str(e))
        return IndexerConfigResultDTO(success=True)


class MediaServerConfigService:
    """
    媒体服务器配置业务服务
    负责保存媒体服务器配置、测试连接
    """

    def __init__(self, config_repo=None, media_server: MediaServer | None = None):
        self._config_repo = config_repo or MediaServerRepositoryAdapter()
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
        sid = cast(int, item.ID) if item else None
        self._config_repo.update_media_server(
            sid=int(sid) if sid else None, name=name, enabled=enabled, config=json.dumps(config), is_default=is_default
        )
        # 如果有设置默认，需要清理其他默认并同步 ENABLED
        if is_default:
            self._config_repo.set_default_media_server(name)
        # 刷新 MediaServer 单例配置
        self._media_server.init_config()
        TokenCache.delete("index")
        # 测试连接
        if test:
            try:
                schemas = SubmoduleHelper.import_submodules(
                    "app.mediaserver.client", filter_func=lambda _, obj: hasattr(obj, "client_id")
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return MediaServerConfigResultDTO(
                            success=True, code=0 if status else 1, msg="测试成功" if status else "测试失败"
                        )
                return MediaServerConfigResultDTO(success=False, code=-1, msg="未找到对应客户端")
            except (ServiceError, RepositoryError, DomainError):
                raise
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
        if (
            target.find("themoviedb") != -1
            or target.find("telegram") != -1
            or target.find("fanart") != -1
            or target.find("tmdb") != -1
        ):
            res = RequestUtils(proxies=get_proxies(), timeout=5).get_res(target)
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

    def __init__(
        self,
        downloader: Downloader | None = None,
        sync: Sync | None = None,
        rss: Rss | None = None,
        subscribe: Subscribe | None = None,
        thread_helper: ThreadHelper | None = None,
    ):
        self._commands = {
            "pttransfer": (downloader or Downloader()).transfer,
            "sync": (sync or Sync()).transfer_sync,
            "rssdownload": (rss or Rss()).rssdownload,
            "subscribe_search_all": (subscribe or Subscribe()).subscribe_search_all,
            # 消息命令兼容映射
            "/ptt": (downloader or Downloader()).transfer,
            "/ptr": (TorrentRemover()).auto_remove_torrents,
            "/rst": (sync or Sync()).transfer_sync,
            "/rss": (rss or Rss()).rssdownload,
            "/ssa": (subscribe or Subscribe()).subscribe_search_all,
        }
        self._thread_helper = thread_helper or ThreadHelper()

    def start_service(self, item: str) -> tuple[bool, str]:
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

    def __init__(self, search_fn=None):
        self._search_fn = search_fn or search_medias_for_web

    def search(
        self, search_word: str, ident_flag: bool = True, filters=None, tmdbid=None, media_type=None
    ) -> WebSearchResultDTO:
        """执行WEB搜索"""
        if not search_word:
            return WebSearchResultDTO(code=0, msg="")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        ret, ret_msg = self._search_fn(
            content=search_word, ident_flag=ident_flag, filters=filters, tmdbid=tmdbid, media_type=media_type
        )
        return WebSearchResultDTO(code=ret, msg=ret_msg or "")


class SystemConfigService:
    """
    系统配置业务服务
    """

    def __init__(self, system_config: SystemConfig | None = None):
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
            return VersionInfoDTO(version=version or "", url=url or "", has_update=True)
        return VersionInfoDTO(version="", url="", has_update=False)


# ---------- 以下从原 app/system_service.py 迁移 ----------


class SystemInfoService:
    """
    系统信息服务
    获取系统版本、运行时长、Python版本等基本信息
    """

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时长"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)

    @staticmethod
    def get_system_info() -> SystemInfoDTO:
        """获取系统基本信息"""
        process = psutil.Process()
        try:
            start_time = datetime.datetime.fromtimestamp(process.create_time())
            uptime_seconds = (datetime.datetime.now() - start_time).total_seconds()
            uptime = SystemInfoService._format_uptime(uptime_seconds)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            start_time = None
            uptime = "-"
            uptime_seconds = 0

        try:
            mem = process.memory_info()
            memory_mb = round(mem.rss / 1024 / 1024, 1)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception:
            memory_mb = 0

        return SystemInfoDTO(
            version=APP_VERSION,
            python_version=platform.python_version(),
            platform=platform.platform(),
            uptime=uptime,
            uptime_seconds=int(uptime_seconds),
            start_time=start_time.isoformat() if start_time else None,
            memory_mb=memory_mb,
        )


class SystemLifecycleService:
    """
    系统生命周期管理服务（原 app/system_service.py 顶层函数提取）
    职责：统一管理系统各服务的启动、停止、重启。
    """

    def __init__(
        self,
        scheduler_core=None,
        sync=None,
        brush_task_service=None,
        rss_checker=None,
        torrent_remover=None,
        downloader=None,
        plugin_manager=None,
        file_index_service=None,
    ):
        from app.services.scheduler_core import SchedulerCore

        self._scheduler = scheduler_core or SchedulerCore()
        # 保存外部注入的依赖（测试时传入 mock），不在 __init__ 中实例化
        self._sync = sync
        self._brush = brush_task_service
        self._rss_checker = rss_checker
        self._torrent_remover = torrent_remover
        self._downloader = downloader
        self._file_index = file_index_service

    def start_service(self) -> None:
        """启动所有后台服务（调度器优先启动，确保后续模块注册任务时调度器已就绪）"""
        from app.services.brush_core import BrushTaskService
        from app.services.rss_service import RssTaskService
        from app.sites import SiteConf
        from initializer import (
            check_config,
            check_redis,
            init_message_webhook_apikey,
            init_rbac_system,
            update_config,
            update_rss_state,
        )

        # 0. 执行初始化（配置检查、RBAC、消息 webhook key 等）
        check_config()
        update_config()
        check_redis()
        update_rss_state()
        init_rbac_system()
        init_message_webhook_apikey()
        # 1. 先启动调度器，确保所有后台服务的定时任务可以正常注册
        self._scheduler.start_service(load_defaults=True)
        # 2. 加载基础组件
        SiteConf()
        # 3. 启动各业务服务（此时调度器已运行，init_config 里的 stop/start_job 可正常执行）
        if self._sync is None:
            self._sync = Sync()
        if self._brush is None:
            self._brush = BrushTaskService()
        if self._rss_checker is None:
            self._rss_checker = RssTaskService()
        if self._torrent_remover is None:
            self._torrent_remover = TorrentRemover()
        if self._downloader is None:
            self._downloader = Downloader()
        if self._file_index is None:
            from app.services.file_index_service import FileIndexService

            self._file_index = FileIndexService()
        self._file_index.start()
        self._sync.init()
        self._brush.init_config()
        self._rss_checker.init_config()
        self._torrent_remover.init_config()

    def stop_service(self) -> None:
        """停止所有后台服务"""
        self._scheduler.stop_service()
        if self._sync:
            self._sync.stop()
        if self._brush:
            self._brush.stop_service()
        if self._rss_checker:
            self._rss_checker.stop_service()
        if self._torrent_remover:
            self._torrent_remover.stop_service()
        if self._downloader:
            self._downloader.stop_service()
        if self._file_index:
            self._file_index.stop()

    def restart_service(self) -> None:
        """重启所有后台服务"""
        self.stop_service()
        self.start_service()

    @staticmethod
    def restart_server() -> None:
        """停止进程并重启服务器"""
        SystemLifecycleService().stop_service()
        script_path = os.path.join(os.getcwd(), "restart-server.sh")
        os.chmod(script_path, 0o755)
        res = subprocess.run(["bash", script_path], cwd=os.getcwd())
        if res.returncode == 0:
            log.info("Nexus Media 重启成功...")
        else:
            log.info(f"Nexus Media 重启失败: {res.stderr.decode()}")


class MessageCommandHandler:
    """
    消息命令处理器（原 app/system_service.py 中的类）
    """

    def __init__(self, search_handler=None):
        self._commands = {
            "/ptr": {"func": TorrentRemover().auto_remove_torrents, "desc": COMMANDS["/ptr"]},
            "/ptt": {"func": Downloader().transfer, "desc": COMMANDS["/ptt"]},
            "/rst": {"func": Sync().transfer_sync, "desc": COMMANDS["/rst"]},
            "/rss": {"func": Rss().rssdownload, "desc": COMMANDS["/rss"]},
            "/ssa": {"func": Subscribe().subscribe_search_all, "desc": COMMANDS["/ssa"]},
            "/tbl": {"func": FileTransfer().truncate_transfer_blacklist, "desc": COMMANDS["/tbl"]},
            "/trh": {"func": self._truncate_rsshistory, "desc": COMMANDS["/trh"]},
            "/utf": {"func": self._unidentification, "desc": COMMANDS["/utf"]},
            "/udt": {"func": SystemLifecycleService.restart_server, "desc": COMMANDS["/udt"]},
            "/sta": {"func": self._user_statistics, "desc": COMMANDS["/sta"]},
        }
        self._search_handler = search_handler

    def handle_message_job(self, msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """处理消息事件"""
        if not msg:
            return

        EventManager().send_event(
            EventType.MessageIncoming,
            {"channel": in_from.value, "user_id": user_id, "user_name": user_name, "message": msg},
        )

        command = self._commands.get(msg)
        if command:
            ThreadHelper().start_thread(command.get("func"), ())
            Message().send_channel_msg(
                channel=in_from, title="正在运行 {} ...".format(command.get("desc")), user_id=user_id or ""
            )
            return

        # 插件命令
        plugin_commands = Message().get_plugin_commands()
        msg_list = msg.split(" ")
        cmd_key = msg_list[0]
        plugin_cmd = plugin_commands.get(cmd_key)
        if plugin_cmd:
            func = plugin_cmd.get("func")
            if func:
                ThreadHelper().start_thread(func, (msg, in_from, user_id, user_name))
            Message().send_channel_msg(
                channel=in_from, title="正在运行 {} ...".format(plugin_cmd.get("desc")), user_id=user_id or ""
            )
            return

        TokenCache.delete("search")
        if self._search_handler:
            ThreadHelper().start_thread(self._search_handler.handle, (msg, in_from, user_id, user_name))

    @staticmethod
    def _truncate_rsshistory():
        from app.helper import RssHelper

        RssHelper().truncate_rss_history()
        Subscribe().truncate_rss_episodes()

    @staticmethod
    def _user_statistics():
        TokenCache.delete("statistics")
        SiteUserInfo().refresh_site_data_now()

    @staticmethod
    def _unidentification():
        from app.services.sync_service import SyncService

        item_ids = []
        records = FileTransfer().get_transfer_unknown_paths()
        if not records:
            return
        for rec in records:
            if not cast(str, rec.PATH):
                continue
            item_ids.append(rec.ID)
        if len(item_ids) > 0:
            SyncService().re_identify_items(flag="unidentification", ids=item_ids)


def get_commands():
    return [{"id": cid, "name": name} for cid, name in COMMANDS.items()]


def get_rmt_modes():
    return [
        {"value": "copy", "name": "复制"},
        {"value": "move", "name": "移动"},
        {"value": "link", "name": "硬链接"},
        {"value": "softlink", "name": "软链接"},
    ]


def get_system_message(lst_time):
    messages = MessageCenter().get_system_messages(lst_time=lst_time)
    if messages:
        lst_time = messages[0].get("time")
    return {"code": 0, "message": messages, "lst_time": lst_time}


def parse_brush_rule_string(rules):
    return BrushRuleEngine.format_rule_html(rules)


def backup(full_backup=False, bk_path=None):
    """
    @param full_backup  是否完整备份（保留参数兼容性，当前始终完整备份）
    @param bk_path     自定义备份路径
    """
    try:
        config_path = Path(settings.config_path)
        backup_file = f"bk_{time.strftime('%Y%m%d%H%M%S')}"
        if bk_path:
            backup_path = Path(bk_path) / backup_file
        else:
            backup_path = config_path / "backup_file" / backup_file
        backup_path.mkdir(parents=True)
        shutil.copy(f"{config_path}/config.yaml", backup_path)
        shutil.copy(f"{config_path}/default-category.yaml", backup_path)

        db_type = DatabaseFactory._get_config_db_type()
        engine = DatabaseFactory.create_engine()
        if db_type == DatabaseFactory.SQLITE:
            shutil.copy(f"{config_path}/user.db", backup_path)
        from app.db.migrate import export_to_file

        export_to_file(engine, str(backup_path / "user_db_export.json"))
        engine.dispose()

        zip_file = str(backup_path) + ".zip"
        if os.path.exists(zip_file):
            zip_file = str(backup_path) + ".zip"
        shutil.make_archive(str(backup_path), "zip", str(backup_path))
        shutil.rmtree(str(backup_path))
        return zip_file
    except (ServiceError, RepositoryError, DomainError):
        raise
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return None


def start_service():
    """启动所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().start_service()


def stop_service():
    """停止所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().stop_service()


def restart_service():
    """重启所有后台服务（顶层兼容函数）"""
    SystemLifecycleService().restart_service()


def restart_server():
    """重启服务器（顶层兼容函数）"""
    SystemLifecycleService.restart_server()


class MessageSenderService:
    """
    消息发送业务服务
    """

    def __init__(self, message: Message | None = None):
        self._message = message or Message()

    def send_custom_message(self, clients: list, title: str, text: str, image: str = "") -> SendMessageResultDTO:
        if not clients:
            return SendMessageResultDTO(success=False, message="未选择消息服务")
        self._message.send_custom_message(clients=clients, title=title, text=text, image=image)
        return SendMessageResultDTO(success=True)

    def send_plugin_message(self, title: str, text: str, image: str = "") -> SendMessageResultDTO:
        self._message.send_plugin_message(title=title, text=text, image=image)
        return SendMessageResultDTO(success=True)


class ProgressService:
    """
    进度查询业务服务
    """

    def __init__(self, progress_helper=None):
        self._progress = progress_helper or ProgressHelper()

    def get_progress(self, ptype: str) -> ProgressResultDTO:
        detail = self._progress.get_process(ProgressKey(ptype))
        if detail:
            return ProgressResultDTO(value=detail.get("value", 0), text=detail.get("text", ""), exists=True)
        return ProgressResultDTO(exists=False, text="正在处理...")


class UserManageService:
    """
    用户管理业务服务
    """

    def __init__(self, rbac_svc=None):
        self._rbac = rbac_svc

    def _get_rbac(self):
        if self._rbac is None:
            from app.services.rbac_service import rbac_service

            self._rbac = rbac_service
        return self._rbac

    def add_user(self, name: str, password: str, pris=None) -> UserManageResultDTO:
        rbac = self._get_rbac()
        ok, _ = rbac.create_user(username=name, password=password)
        return UserManageResultDTO(success=bool(ok))

    def delete_user(self, name: str) -> UserManageResultDTO:
        rbac = self._get_rbac()
        user = rbac.get_user_by_username(name)
        if user:
            ok, _ = rbac.delete_user(user.ID)  # type: ignore[arg-type]
            return UserManageResultDTO(success=bool(ok))
        return UserManageResultDTO(success=False, message="用户不存在")


class ConfigUpdateService:
    """
    配置更新业务服务（文件配置 + 数据库配置合并更新）
    """

    @staticmethod
    def update_config(data: dict) -> ConfigUpdateResultDTO:
        from app.utils.web_utils import set_config_value

        cfg = settings.get()
        config_test = False
        for key, value in dict(data).items():
            if key == "test" and value:
                config_test = True
                continue
            cfg = set_config_value(cfg, key, value)
        if not config_test:
            cfg.pop("test", None)
            settings.save(cfg)
        return ConfigUpdateResultDTO(success=True, test_mode=config_test)
