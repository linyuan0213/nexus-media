import datetime
import json
import os.path
import shutil


from flask_login import logout_user
from werkzeug.security import generate_password_hash

from app.helper import tmdb_blacklist_helper
from app.helper.tmdb_blacklist_helper import TmdbBlacklistHelper
from app.conf import SystemConfig
from app.downloader import Downloader
from app.helper import DbHelper, ProgressHelper, ThreadHelper
from app.mediaserver import MediaServer
from app.message import Message
from app.rss import Rss
from app.subscribe import Subscribe
from app.sync import Sync
from app.utils import RequestUtils, ExceptionUtils
from app.utils.types import MediaType, MovieTypes
from config import Config
from web.backend.search_torrents import search_medias_for_web
from web.backend.user import User
from web.backend.web_utils import WebUtils
from web.cache import cache
from app.utils.temp_manager import temp_manager
from web.actions._base import WebActionBase


class WebActionSystemMixin:
    def _restart(self):
        """
        重启
        """
        # 退出主进程
        self.restart_server()
        return self._success()

    def update_system(self):
        """
        更新
        """
        # 重启
        self.restart_server()
        return self._success()

    @staticmethod
    def _reset_db_version():
        """
        重置数据库版本
        """
        try:
            DbHelper().drop_table("alembic_version")
            return WebActionBase._success()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return WebActionBase._fail(msg=str(e))

    @staticmethod
    def _logout():
        """
        注销
        """
        logout_user()
        return WebActionBase._success()

    def _update_config(self, data):
        """
        更新配置信息
        """
        cfg = Config().get_config()
        cfgs = dict(data).items()
        # 仅测试不保存
        config_test = False
        # 修改配置
        for key, value in cfgs:
            if key == "test" and value:
                config_test = True
                continue
            # 生效配置
            cfg = self.set_config_value(cfg, key, value)

        # 保存配置
        if not config_test:
            cfg.pop("test", None)
            Config().save_config(cfg)

        return self._success()

    def _update_all_config(self, data):
        """
        设置系统设置（数据库）
        """
        conf = data.get("conf")
        db = data.get("db")
        if data.get('test'):
            conf = data
        if conf:
            ret = self._update_config(conf)
            if ret.get('code') == 1:
                return ret
        if db:
            ret = self._set_system_config(db)
            if ret.get('code') == 1:
                return ret

        return self._success()

    @staticmethod
    def _save_indexer_config(data):
        """
        保存索引器配置到数据库
        """
        from app.conf import SystemConfig
        from app.utils.types import SystemConfigKey
        name = data.get("type")
        test = data.get("test") in [True, "true", "on", "1", 1]
        # 兼容旧配置：首次保存时从配置文件迁移
        existing = SystemConfig().get(SystemConfigKey.IndexerConfig) or {}
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
            SystemConfig().set(SystemConfigKey.IndexerConfig, existing)
        # 保存当前使用的索引器
        SystemConfig().set(SystemConfigKey.SearchIndexer, name)
        # 保存builtin站点的选中状态
        if name == "builtin":
            sites = data.get("indexer_sites")
            if sites is not None:
                SystemConfig().set(SystemConfigKey.UserIndexerSites, sites)
        # 刷新 Indexer 单例配置
        from app.indexer import Indexer
        Indexer().init_config()
        # 测试连接
        if test and name != "builtin":
            try:
                from app.helper import SubmoduleHelper
                schemas = SubmoduleHelper.import_submodules(
                    'app.indexer.client',
                    filter_func=lambda _, obj: hasattr(obj, 'client_id')
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return WebActionBase._fail(code=0 if status else 1, msg="测试成功" if status else "测试失败")
                return WebActionBase._fail(msg="未找到对应客户端")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return WebActionBase._fail(msg=str(e))
        return WebActionBase._success()

    @staticmethod
    def _set_system_config(data):
        """
        设置系统设置（数据库）
        """
        key = data.get("key")
        value = data.get("value")
        if not key or not value:
            return WebActionBase._fail()
        try:
            SystemConfig().set(key=key, value=value)
            return WebActionBase._success()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return WebActionBase._fail()

    @staticmethod
    def _save_mediaserver_config(data):
        """
        保存媒体服务器配置到数据库
        """
        from app.db.repositories import ConfigRepository
        from app.mediaserver import MediaServer
        repo = ConfigRepository()
        name = data.get("type")
        test = data.get("test") in [True, "true", "on", "1", 1]
        config = {}
        for key, value in data.items():
            if key.startswith(name + "."):
                config[key.split(".", 1)[1]] = value
        if not config:
            return WebActionBase._fail(msg="配置为空")
        enabled = 1 if config.get("enabled") else 0
        is_default = 1 if config.get("is_default") else 0
        item = repo.get_media_server_by_name(name)
        sid = item.ID if item else None
        repo.update_media_server(
            sid=sid,
            name=name,
            enabled=enabled,
            config=json.dumps(config),
            is_default=is_default
        )
        # 如果有设置默认，需要清理其他默认并同步 ENABLED
        if is_default:
            repo.set_default_media_server(name)
        # 刷新 MediaServer 单例配置
        MediaServer().init_config()
        cache.delete("index")
        # 测试连接
        if test:
            try:
                from app.helper import SubmoduleHelper
                schemas = SubmoduleHelper.import_submodules(
                    'app.mediaserver.client',
                    filter_func=lambda _, obj: hasattr(obj, 'client_id')
                )
                for schema in schemas:
                    if schema.match(name):
                        client = schema(config)
                        status = client.get_status()
                        return WebActionBase._fail(code=0 if status else 1, msg="测试成功" if status else "测试失败")
                return WebActionBase._fail(msg="未找到对应客户端")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return WebActionBase._fail(msg=str(e))
        return WebActionBase._success()

    @staticmethod
    def _version():
        """
        检查新版本
        """
        version, url, flag = WebUtils.get_latest_version()
        if flag:
            return WebActionBase._success(version=version, url=url)
        return WebActionBase._fail(code=-1, version="", url="")

    @staticmethod
    def _restory_backup(data):
        """
        解压恢复备份文件
        """
        filename = data.get("file_name")
        if filename:
            config_path = Config().get_config_path()
            file_path = temp_manager.get_temp_path(filename)
            try:
                shutil.unpack_archive(file_path, config_path, format='zip')
                return WebActionBase._success(msg="")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return WebActionBase._fail(msg=str(e))
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        return WebActionBase._fail(msg="文件不存在")

    @staticmethod
    def refresh_process(data):
        """
        刷新进度条
        """
        detail = ProgressHelper().get_process(data.get("type"))
        if detail:
            return WebActionBase._success(value=detail.get("value"), text=detail.get("text"))
        else:
            return WebActionBase._fail(value=0, text="正在处理...")

    @staticmethod
    def _sch(data):
        """
        启动服务
        """
        commands = {
            "pttransfer": Downloader().transfer,
            "sync": Sync().transfer_sync,
            "rssdownload": Rss().rssdownload,
            "subscribe_search_all": Subscribe().subscribe_search_all,
        }
        sch_item = data.get("item")
        if sch_item and commands.get(sch_item):
            ThreadHelper().start_thread(commands.get(sch_item), ())
        return WebActionBase._success(msg="服务已启动", item=sch_item)

    @staticmethod
    def _search(data):
        """
        WEB搜索资源
        """
        cache.delete("search")
        search_word = data.get("search_word")
        ident_flag = False if data.get("unident") else True
        filters = data.get("filters")
        tmdbid = data.get("tmdbid")
        media_type = data.get("media_type")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        if search_word:
            ret, ret_msg = search_medias_for_web(content=search_word,
                                                 ident_flag=ident_flag,
                                                 filters=filters,
                                                 tmdbid=tmdbid,
                                                 media_type=media_type)
            if ret != 0:
                return WebActionBase._fail(code=ret, msg=ret_msg)
        return WebActionBase._success()

    @staticmethod
    def _net_test(data):
        target = data
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
            res = RequestUtils(proxies=Config().get_proxies(),
                               timeout=5).get_res(target)
        else:
            res = RequestUtils(timeout=5).get_res(target)
        seconds = int((datetime.datetime.now() -
                       start_time).microseconds / 1000)
        if not res:
            return {"res": False, "time": "%s 毫秒" % seconds}
        elif res.ok:
            return {"res": True, "time": "%s 毫秒" % seconds}
        else:
            return {"res": False, "time": "%s 毫秒" % seconds}

    @staticmethod
    def _add_tmdb_blacklist(data):
        """
        删除tmdb缓存
        """
        tmdb_blacklist_helper = TmdbBlacklistHelper()
        tmdb_id = data.get("tmdb_id")
        media_type = data.get("media_type")
        if not tmdb_blacklist_helper.is_blacklisted(tmdb_id, media_type):
            tmdb_blacklist_helper.add_to_blacklist(
                tmdb_id=tmdb_id, media_type=media_type)
        return WebActionBase._success()

    @staticmethod
    def _delete_tmdb_blacklist(data):
        tmdb_blacklist_helper = TmdbBlacklistHelper()
        tmdb_id = data.get("tmdb_id")
        media_type = data.get("media_type")
        if tmdb_blacklist_helper.is_blacklisted(tmdb_id, media_type):
            tmdb_blacklist_helper.remove_from_blacklist(
                tmdb_id=tmdb_id, media_type=media_type)
        return WebActionBase._success()

    @staticmethod
    def _clear_tmdb_blacklist(data):
        tmdb_blacklist_helper = TmdbBlacklistHelper()
        if tmdb_blacklist_helper.get_blacklist():
            tmdb_blacklist_helper.clear_blacklist()
        return WebActionBase._success()

    @staticmethod
    def _update_message_client(data):
        """
        更新消息设置
        """
        _message = Message()
        name = data.get("name")
        cid = data.get("cid")
        ctype = data.get("type")
        config = data.get("config")
        switchs = data.get("switchs")
        interactive = data.get("interactive")
        enabled = data.get("enabled")
        templates = data.get("templates")
        if cid:
            _message.delete_message_client(cid=cid)
        if int(interactive) == 1:
            _message.check_message_client(interactive=0, ctype=ctype)
        _message.insert_message_client(name=name,
                                       ctype=ctype,
                                       config=config,
                                       switchs=switchs,
                                       interactive=interactive,
                                       enabled=enabled,
                                       templates=templates)
        return WebActionBase._success()

    @staticmethod
    def _delete_message_client(data):
        """
        删除消息设置
        """
        if Message().delete_message_client(cid=data.get("cid")):
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def _check_message_client(data):
        """
        维护消息设置
        """
        flag = data.get("flag")
        cid = data.get("cid")
        ctype = data.get("type")
        checked = data.get("checked")
        _message = Message()
        if flag == "interactive":
            # TG/WX只能开启一个交互
            if checked:
                _message.check_message_client(interactive=0, ctype=ctype)
            _message.check_message_client(cid=cid,
                                          interactive=1 if checked else 0)
            return WebActionBase._success()
        elif flag == "enable":
            _message.check_message_client(cid=cid,
                                          enabled=1 if checked else 0)
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def _get_message_client(data):
        """
        获取消息设置
        """
        cid = data.get("cid")
        return WebActionBase._success(detail=Message().get_message_client_info(cid=cid))

    @staticmethod
    def _test_message_client(data):
        """
        测试消息设置
        """
        ctype = data.get("type")
        config = json.loads(data.get("config"))
        res = Message().get_status(ctype=ctype, config=config)
        if res:
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def send_plugin_message(data):
        """
        发送插件消息
        """
        title = data.get("title")
        text = data.get("text") or ""
        image = data.get("image") or ""
        Message().send_plugin_message(title=title, text=text, image=image)
        return WebActionBase._success()

    @staticmethod
    def send_custom_message(data):
        """
        发送自定义消息
        """
        title = data.get("title")
        text = data.get("text") or ""
        image = data.get("image") or ""
        message_clients = data.get("message_clients")
        if not message_clients:
            return WebActionBase._fail(msg="未选择消息服务")
        Message().send_custom_message(clients=message_clients,
                                      title=title, text=text, image=image)
        return WebActionBase._success()

    @staticmethod
    def _user_manager(data):
        """
        用户管理
        """
        oper = data.get("oper")
        name = data.get("name")
        if oper == "add":
            password = generate_password_hash(str(data.get("password")))
            pris = data.get("pris")
            if isinstance(pris, list):
                pris = ",".join(pris)
            ret = User().add_user(name, password, pris)
        else:
            ret = User().delete_user(name)

        if ret == 1 or ret:
            return WebActionBase._success(success=False)
        return WebActionBase._fail(code=-1, success=False, message='操作失败')
