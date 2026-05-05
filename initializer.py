import json
import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from app.utils.security import generate_password_hash

from app.utils.path_utils import  get_category_path
import log
from app.core.system_config import SystemConfig
from app.db.repositories import ConfigRepository, DownloadRepository
from app.helper import PluginHelper
from app.helper.site_data_updater import SiteDataUpdater
from app.media import Category
from app.utils import ConfigLoadCache, CategoryLoadCache, ExceptionUtils, StringUtils
from app.utils.types import SystemConfigKey
from config import Config

_observer = Observer(timeout=10)


def check_config():
    """
    检查配置文件，如有错误进行日志输出
    """
    # 检查日志输出
    if Config().get_config('log'):
        logtype = Config().get_config('log').get('type')
        if logtype:
            log.info(f"日志输出类型为：{logtype}")
        if logtype == "server":
            logserver = Config().get_config('log').get('server')
            if not logserver:
                log.warn("【Config】日志中心地址未配置，无法正常输出日志")
            else:
                log.info(f"日志将上送到服务器：{logserver}")
        elif logtype == "file":
            logpath = Config().get_config('log').get('path')
            if not logpath:
                log.warn("【Config】日志文件路径未配置，无法正常输出日志")
            else:
                log.info(f"日志将写入文件：{logpath}")
    else:
        log.error("【Config】配置文件格式错误，找不到log配置项！")

    # 检测系统设置
    if Config().get_config('app'):
        # 检查WEB端口
        web_port = Config().get_config('app').get('web_port')
        if not web_port:
            log.warn("【Config】WEB服务端口未设置，将使用默认3000端口")

        # 检查登录用户和密码
        login_user = Config().get_config('app').get('login_user')
        login_password = Config().get_config('app').get('login_password')
        if not login_user or not login_password:
            log.warn("【Config】WEB管理用户或密码未设置，将使用默认用户：admin，密码：password")
        else:
            log.info(f"WEB管理页面用户：{str(login_user)}")

        # 检查HTTPS
        ssl_cert = Config().get_config('app').get('ssl_cert')
        ssl_key = Config().get_config('app').get('ssl_key')
        if os.environ.get('NT_PORT'):
            web_port = os.environ.get('NT_PORT')
        if not ssl_cert or not ssl_key:
            log.info(f"未启用https，请使用 http://IP:{str(web_port)} 访问管理页面")
        else:
            if not os.path.exists(ssl_cert):
                log.warn(f"【Config】ssl_cert文件不存在：{ssl_cert}")
            if not os.path.exists(ssl_key):
                log.warn(f"【Config】ssl_key文件不存在：{ssl_key}")
            log.info(f"已启用https，请使用 https://IP:{str(web_port)} 访问管理页面")
    else:
        log.error("【Config】配置文件格式错误，找不到app配置项！")


def update_config():
    """
    升级配置文件
    """
    _config = Config().get_config()
    _dbhelper = DownloadRepository()
    overwrite_cofig = False

    # API密钥初始化
    if not _config.get("security", {}).get("api_key"):
        _config['security']['api_key'] = StringUtils.generate_random_str(32)
        overwrite_cofig = True

    # 日志配置迁移：从 app.xxx 迁移到 log.xxx
    try:
        app_config = _config.get("app", {})
        # 定义：{旧键: 新键}
        log_mapping = {
            "logtype": "type",
            "loglevel": "level",
            "logserver": "server",
            "logpath": "path"
        }
        
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
            overwrite_cofig = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 站点数据刷新时间默认配置
    try:
        if "ptrefresh_date_cron" not in _config['pt']:
            _config['pt']['ptrefresh_date_cron'] = '6'
            overwrite_cofig = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 存量插件安装情况统计
    try:
        plugin_report_state = SystemConfig().get(SystemConfigKey.UserInstalledPluginsReport)
        installed_plugins = SystemConfig().get(SystemConfigKey.UserInstalledPlugins)
        if not plugin_report_state and installed_plugins:
            ret = PluginHelper().report(installed_plugins)
            if ret:
                SystemConfig().set(SystemConfigKey.UserInstalledPluginsReport, '1')
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # TMDB代理服务开关迁移
    try:
        tmdb_proxy = Config().get_config('laboratory').get("tmdb_proxy")
        if tmdb_proxy:
            _config['app']['tmdb_domain'] = 'tmdb.nastool.cn'
            _config['laboratory'].pop("tmdb_proxy")
            overwrite_cofig = True
    except Exception as e:
        ExceptionUtils.exception_traceback(e)

    # 重写配置文件
    if overwrite_cofig:
        Config().save_config(_config)

    # 清空索引器统计
    _dbhelper.delete_all_indexer_statistics()
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
        if file_name == "config.yaml" and not ConfigLoadCache.get(src_path):
            ConfigLoadCache.set(src_path, True)
            CategoryLoadCache.set("ConfigLoadBlock", True, ConfigLoadCache.ttl)
            log.warn(f"【System】进程 {os.getpid()} 检测到系统配置文件已修改，正在重新加载...")
            time.sleep(1)
            # 重新加载配置
            Config().init_config()
        # 正在使用的二级分类策略文件3秒内只能加载一次，配置文件加载时，二级分类策略文件不加载
        elif file_name == os.path.basename(get_category_path()) \
                and not CategoryLoadCache.get(src_path) \
                and not CategoryLoadCache.get("ConfigLoadBlock"):
            CategoryLoadCache.set(src_path, True)
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
    _observer.schedule(ConfigMonitor(), path=Config().config_path, recursive=False)
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

def update_sites_data():
    try:
        cfg = Config()
        from app.utils.path_utils import get_temp_path, get_inner_config_path
        from app.utils.config_tools import get_proxies
        SiteDataUpdater.update_sites_data(
            cfg._config_path, get_temp_path(), get_inner_config_path(),
            proxies=get_proxies()
        )
        log.info("站点资源数据已更新...")
    except Exception as e:
        log.error(f"站点资源更新失败 .. {str(e)}")

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


def update_rss_state():
    """
    初始化时更新所有RSS订阅状态为R
    """
    try:
        dbhelper = ConfigRepository()
        # 执行SQL脚本更新RSS状态
        sql_file = os.path.join(os.path.dirname(__file__), "scripts", "sqls", "update_rss_state.sql")
        if os.path.exists(sql_file):
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
                # 分割SQL语句并分别执行
                sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
                for sql in sql_statements:
                    if sql:
                        dbhelper.excute(sql)
                log.info("【Initialize】RSS订阅状态已更新为正在订阅")
        else:
            log.warn("【Initialize】RSS状态更新SQL文件不存在")
    except Exception as e:
        log.error(f"【Initialize】更新RSS状态失败：{str(e)}")
        ExceptionUtils.exception_traceback(e)


def init_rbac_system():
    """
    初始化 RBAC 权限管理系统
    - 初始化默认权限、菜单、角色
    - 创建管理员用户
    """
    try:
        from app.services.rbac_init import init_rbac_system as rbac_init, init_admin_user
        from config import Config
        
        # 初始化 RBAC 基础数据
        rbac_init()
        
        # 获取配置中的管理员账号
        login_user = Config().get_config('app').get('login_user') or 'admin'
        login_password = Config().get_config('app').get('login_password') or 'password'
        
        # 如果是哈希密码，使用原始密码
        if login_password.startswith('[hash]'):
            login_password = 'password'
        
        # 创建管理员用户
        init_admin_user(login_user, login_password)
        log.info(f"【Initialize】RBAC 系统初始化完成，管理员: {login_user}")
        
    except Exception as e:
        log.error(f"【Initialize】RBAC 系统初始化失败: {str(e)}")
        ExceptionUtils.exception_traceback(e)
