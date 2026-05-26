import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import log
from app.core.system_config import SystemConfig
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.download_repo_adapter import IndexerStatisticsRepositoryAdapter
from app.helper import PluginHelper
from app.infrastructure.cache_system import CategoryLoadCache, ConfigLoadCache
from app.media import Category
from app.services.apikey_service import APIKeyService
from app.services.rbac_init import init_admin_user
from app.services.rbac_init import init_rbac_system as rbac_init
from app.utils import ExceptionUtils
from app.utils.path_utils import get_category_path
from app.utils.types import SystemConfigKey
from app.core.settings import settings

_observer = Observer(timeout=10)


def check_config():
    """
    检查配置文件，如有错误进行日志输出
    """
    # 检查日志输出
    _log_cfg = settings.get("log")
    if _log_cfg:
        logtype = _log_cfg.get("type")
        if logtype:
            log.info(f"日志输出类型为：{logtype}")
        if logtype == "server":
            logserver = _log_cfg.get("server")
            if not logserver:
                log.warn("【Config】日志中心地址未配置，无法正常输出日志")
            else:
                log.info(f"日志将上送到服务器：{logserver}")
        elif logtype == "file":
            logpath = _log_cfg.get("path")
            if not logpath:
                log.warn("【Config】日志文件路径未配置，无法正常输出日志")
            else:
                log.info(f"日志将写入文件：{logpath}")
    else:
        log.error("【Config】配置文件格式错误，找不到log配置项！")

    # 检测系统设置
    _app_cfg = settings.get("app")
    if _app_cfg:
        # 检查WEB端口
        web_port = _app_cfg.get("web_port")
        if not web_port:
            log.warn("【Config】WEB服务端口未设置，将使用默认3000端口")

        # 检查登录用户和密码
        login_user = _app_cfg.get("login_user")
        login_password = _app_cfg.get("login_password")
        if not login_user or not login_password:
            log.warn("【Config】WEB管理用户或密码未设置，将使用默认用户：admin，密码：password")
        else:
            log.info(f"WEB管理页面用户：{login_user!s}")

        # 检查HTTPS
        ssl_cert = _app_cfg.get("ssl_cert")
        ssl_key = _app_cfg.get("ssl_key")
        if os.environ.get("NEXUS_PORT"):
            web_port = os.environ.get("NEXUS_PORT")
        if not ssl_cert or not ssl_key:
            log.info(f"未启用https，请使用 http://IP:{web_port!s} 访问管理页面")
        else:
            if not os.path.exists(ssl_cert):
                log.warn(f"【Config】ssl_cert文件不存在：{ssl_cert}")
            if not os.path.exists(ssl_key):
                log.warn(f"【Config】ssl_key文件不存在：{ssl_key}")
            log.info(f"已启用https，请使用 https://IP:{web_port!s} 访问管理页面")
    else:
        log.error("【Config】配置文件格式错误，找不到app配置项！")


def update_config():
    """
    升级配置文件
    """
    _config = settings.get()
    _dbhelper = IndexerStatisticsRepositoryAdapter()
    overwrite_config = False

    # security.api_key 已废弃：
    # - JWT 签名改用 get_secret_key()（从 security.jwt_secret 或 app.web_secret_key 获取）
    # - Webhook 验证改用数据库管理的 API Key（APIKeyService）
    # 保留此段代码用于清理旧配置项（可选）
    _security_cfg = _config.get("security", {})
    if _security_cfg.get("api_key"):
        _config["security"].pop("api_key", None)
        overwrite_config = True

    # 日志配置迁移：从 app.xxx 迁移到 log.xxx
    try:
        app_config = _config.get("app", {})
        # 定义：{旧键: 新键}
        log_mapping = {"logtype": "type", "loglevel": "level", "logserver": "server", "logpath": "path"}

        # 初始化 log 节点（如果不存在）
        if "log" not in _config:
            _config["log"] = {}

        migrated = False
        for old_key, new_key in log_mapping.items():
            if old_key in app_config:
                # 1. 迁移数据到新位置
                _config["log"][new_key] = app_config.get(old_key)
                # 2. 删除旧位置的数据
                app_config.pop(old_key)
                migrated = True
                log.info(f"【Config】日志配置已迁移：app.{old_key} -> log.{new_key}，并已移除旧配置。")

        if migrated:
            overwrite_config = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 站点数据刷新时间默认配置
    try:
        if "ptrefresh_date_cron" not in _config.get("pt", {}):
            _config.setdefault("pt", {})
            _config["pt"]["ptrefresh_date_cron"] = "6"
            overwrite_config = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 存量插件安装情况统计
    try:
        plugin_report_state = SystemConfig().get(SystemConfigKey.UserInstalledPluginsReport)
        installed_plugins = SystemConfig().get(SystemConfigKey.UserInstalledPlugins)
        if not plugin_report_state and installed_plugins:
            ret = PluginHelper().report(installed_plugins)
            if ret:
                SystemConfig().set(SystemConfigKey.UserInstalledPluginsReport, "1")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # TMDB代理服务开关迁移
    try:
        _lab_cfg = _config.get("laboratory", {})
        tmdb_proxy = _lab_cfg.get("tmdb_proxy")
        if tmdb_proxy:
            _config.setdefault("app", {})
            _config["app"]["tmdb_domain"] = "tmdb.nexus-media.cn"
            _config["laboratory"].pop("tmdb_proxy")
            overwrite_config = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 重写配置文件
    if overwrite_config:
        settings.save(_config)

    # 清空索引器统计
    _dbhelper.delete_all()


class ConfigMonitor(FileSystemEventHandler):
    """
    配置文件变化响应
    """

    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_modified(self, event):
        if event.is_directory:
            return
        src_path = event.src_path
        file_name = os.path.basename(src_path)
        file_head, file_ext = os.path.splitext(os.path.basename(file_name))
        if file_ext != ".yaml":
            return
        # 配置文件10秒内只能加载一次
        if file_name == "config.yaml" and not ConfigLoadCache.get(str(src_path)):
            ConfigLoadCache.set(str(src_path), True)
            CategoryLoadCache.set("ConfigLoadBlock", True)
            log.warn(f"【System】进程 {os.getpid()} 检测到系统配置文件已修改，正在重新加载...")
            time.sleep(1)
            # 重新加载配置
            settings.reload()
        # 正在使用的二级分类策略文件3秒内只能加载一次，配置文件加载时，二级分类策略文件不加载
        elif (
            (category_path := get_category_path())
            and file_name == os.path.basename(category_path)
            and not CategoryLoadCache.get(str(src_path))
            and not CategoryLoadCache.get("ConfigLoadBlock")
        ):
            CategoryLoadCache.set(str(src_path), True)
            log.warn(f"【System】进程 {os.getpid()} 检测到二级分类策略 {file_head} 配置文件已修改，正在重新加载...")
            time.sleep(1)
            # 重新加载二级分类策略
            Category().init_config()


def start_config_monitor():
    """
    启动服务
    """
    global _observer
    # 配置文件监听
    _observer.schedule(ConfigMonitor(), path=settings.config_path, recursive=False)
    _observer.daemon = True
    _observer.start()


def stop_config_monitor():
    """
    停止服务
    """
    global _observer
    try:
        if _observer:
            _observer.stop()
            _observer.join()
    except Exception as err:
        print(str(err))


def check_redis():
    """检查 Redis 状态，仅记录日志，不阻塞启动"""
    from app.utils.redis_store import RedisStore

    try:
        redis_store = RedisStore()
        if redis_store.is_available():
            log.info("Redis 正在运行...")
        else:
            log.info("Redis 未启用，使用内存缓存...")
    except Exception as e:
        log.info(f"Redis 未启用，使用内存缓存: {e}")


def init_message_webhook_apikey():
    """
    初始化消息通知 Webhook 的系统级 API Key
    在 API_KEYS 表中创建/获取名为 MessageWebhook 的系统 key
    """
    try:
        service = APIKeyService()
        service.get_or_create_system_key("MessageWebhook")
        log.info("【Initialize】消息 Webhook API Key 已就绪")
    except Exception as e:
        log.error(f"【Initialize】消息 Webhook API Key 初始化失败：{e!s}")
        ExceptionUtils.exception_traceback(e)


def update_rss_state():
    """
    初始化时更新所有RSS订阅状态为R
    """
    try:
        # 执行SQL脚本更新RSS状态
        sql_file = os.path.join(os.path.dirname(__file__), "scripts", "sqls", "update_rss_state.sql")
        if os.path.exists(sql_file):
            with open(sql_file, encoding="utf-8") as f:
                sql_content = f.read()
                # 分割SQL语句并分别执行
                sql_statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
                for sql in sql_statements:
                    if sql:
                        BaseRepository._db.execute(sql)
                log.info("【Initialize】RSS订阅状态已更新为正在订阅")
        else:
            log.warn("【Initialize】RSS状态更新SQL文件不存在")
    except Exception as e:
        log.error(f"【Initialize】更新RSS状态失败：{e!s}")
        ExceptionUtils.exception_traceback(e)


def init_rbac_system():
    """
    初始化 RBAC 权限管理系统
    - 初始化默认权限、菜单、角色
    - 创建管理员用户
    """
    try:
        # 初始化 RBAC 基础数据
        rbac_init()

        # 获取配置中的管理员账号
        _app_cfg = settings.get("app")
        login_user = _app_cfg.get("login_user") or "admin"
        login_password = _app_cfg.get("login_password") or "password"

        # 如果是哈希密码，使用原始密码
        if login_password.startswith("[hash]"):
            login_password = "password"

        # 创建管理员用户
        init_admin_user(login_user, login_password)
        log.info(f"【Initialize】RBAC 系统初始化完成，管理员: {login_user}")

    except Exception as e:
        log.error(f"【Initialize】RBAC 系统初始化失败: {e!s}")
        ExceptionUtils.exception_traceback(e)
