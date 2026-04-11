import inspect
import os.path
import re
import shutil
import sqlite3
import time
import subprocess
from pathlib import Path


from werkzeug.security import generate_password_hash

from app.helper.drissionpage_helper import DrissionPageHelper
import log
from app.brushtask import BrushTask
from app.conf import ModuleConf
from app.downloader import Downloader
from app.helper import ThreadHelper, IndexerHelper
from app.media.meta import MetaInfo
from app.mediaserver import MediaServer
from app.message import Message, MessageCenter
from app.plugins import PluginManager, EventManager
from app.rss import Rss
from app.rsschecker import RssChecker
from app.scheduler import Scheduler
from app.sites import SiteUserInfo, SiteConf
from app.subscribe import Subscribe
from app.sync import Sync
from app.torrentremover import TorrentRemover
from app.utils import PathUtils, SystemUtils, ExceptionUtils
from app.utils.types import SearchType, MediaType, MovieTypes, EventType
from config import RMT_MEDIAEXT, Config
from web.backend.search_torrents import search_media_by_message
from web.cache import cache


class WebActionBase:
    def __init__(self):
        # WEB请求响应
        self._actions = {
            "sch": self._sch,
            "search": self._search,
            "download": self._download,
            "download_link": self._download_link,
            "download_torrent": self._download_torrent,
            "pt_start": self._pt_start,
            "pt_stop": self._pt_stop,
            "pt_remove": self._pt_remove,
            "pt_info": self._pt_info,
            "del_unknown_path": self._del_unknown_path,
            "rename": self._rename,
            "rename_udf": self._rename_udf,
            "delete_history": self.delete_history,
            "clear_history": self.clear_history,
            "version": self._version,
            "update_site": self._update_site,
            "get_site": self._get_site,
            "del_site": self._del_site,
            "get_site_favicon": self._get_site_favicon,
            "restart": self._restart,
            "update_system": self.update_system,
            "reset_db_version": self._reset_db_version,
            "logout": self._logout,
            "update_config": self._update_config,
            "save_indexer_config": self._save_indexer_config,
            "save_mediaserver_config": self._save_mediaserver_config,
            "update_directory": self._update_directory,
            "add_or_edit_sync_path": self._add_or_edit_sync_path,
            "get_sync_path": self.get_sync_path,
            "delete_sync_path": self._delete_sync_path,
            "check_sync_path": self._check_sync_path,
            "remove_rss_media": self._remove_rss_media,
            "add_rss_media": self._add_rss_media,
            "re_identification": self.re_identification,
            "media_info": self._media_info,
            "test_connection": self._test_connection,
            "user_manager": self._user_manager,
            "refresh_rss": self._refresh_rss,
            "movie_calendar_data": self._movie_calendar_data,
            "tv_calendar_data": self._tv_calendar_data,
            "rss_detail": self._rss_detail,
            "truncate_blacklist": self.truncate_blacklist,
            "truncate_rsshistory": self.truncate_rsshistory,
            "add_brushtask": self._add_brushtask,
            "del_brushtask": self._del_brushtask,
            "brushtask_detail": self._brushtask_detail,
            "update_brushtask_state": self._update_brushtask_state,
            "name_test": self._name_test,
            "rule_test": self._rule_test,
            "net_test": self._net_test,
            "add_filtergroup": self._add_filtergroup,
            "restore_filtergroup": self._restore_filtergroup,
            "set_default_filtergroup": self._set_default_filtergroup,
            "del_filtergroup": self._del_filtergroup,
            "add_filterrule": self._add_filterrule,
            "del_filterrule": self._del_filterrule,
            "filterrule_detail": self._filterrule_detail,
            "get_site_activity": self._get_site_activity,
            "get_site_history": self._get_site_history,
            "get_recommend": self.get_recommend,
            "get_downloaded": self.get_downloaded,
            "get_site_seeding_info": self._get_site_seeding_info,
            "check_site_attr": self._check_site_attr,
            "refresh_process": self.refresh_process,
            "restory_backup": self._restory_backup,
            "start_mediasync": self._start_mediasync,
            "mediasync_state": self._mediasync_state,
            "get_tvseason_list": self._get_tvseason_list,
            "get_userrss_task": self._get_userrss_task,
            "delete_userrss_task": self._delete_userrss_task,
            "update_userrss_task": self._update_userrss_task,
            "check_userrss_task": self._check_userrss_task,
            "get_rssparser": self._get_rssparser,
            "delete_rssparser": self._delete_rssparser,
            "update_rssparser": self._update_rssparser,
            "run_userrss": self._run_userrss,
            "run_brushtask": self._run_brushtask,
            "list_site_resources": self.list_site_resources,
            "list_rss_articles": self._list_rss_articles,
            "rss_article_test": self._rss_article_test,
            "list_rss_history": self._list_rss_history,
            "rss_articles_check": self._rss_articles_check,
            "rss_articles_download": self._rss_articles_download,
            "add_custom_word_group": self._add_custom_word_group,
            "delete_custom_word_group": self._delete_custom_word_group,
            "add_or_edit_custom_word": self._add_or_edit_custom_word,
            "get_custom_word": self._get_custom_word,
            "delete_custom_words": self._delete_custom_words,
            "check_custom_words": self._check_custom_words,
            "export_custom_words": self._export_custom_words,
            "analyse_import_custom_words_code": self._analyse_import_custom_words_code,
            "import_custom_words": self._import_custom_words,
            "get_categories": self.get_categories,
            "re_rss_history": self._re_rss_history,
            "delete_rss_history": self._delete_rss_history,
            "share_filtergroup": self._share_filtergroup,
            "import_filtergroup": self._import_filtergroup,
            "get_transfer_statistics": self.get_transfer_statistics,
            "get_library_spacesize": self.get_library_spacesize,
            "get_library_mediacount": self.get_library_mediacount,
            "get_library_playhistory": self.get_library_playhistory,
            "get_search_result": self.get_search_result,
            "search_media_infos": self.search_media_infos,
            "get_movie_rss_list": self.get_movie_rss_list,
            "get_tv_rss_list": self.get_tv_rss_list,
            "get_rss_history": self.get_rss_history,
            "get_transfer_history": self.get_transfer_history,
            "get_unknown_list": self.get_unknown_list,
            "get_unknown_list_by_page": self.get_unknown_list_by_page,
            "get_customwords": self.get_customwords,
            "get_users": self.get_users,
            "get_filterrules": self.get_filterrules,
            "get_downloading": self.get_downloading,
            "test_site": self._test_site,
            "get_sub_path": self._get_sub_path,
            "rename_file": self._rename_file,
            "delete_files": self._delete_files,
            "download_subtitle": self._download_subtitle,
            "get_download_setting": self._get_download_setting,
            "update_download_setting": self._update_download_setting,
            "delete_download_setting": self._delete_download_setting,
            "update_message_client": self._update_message_client,
            "delete_message_client": self._delete_message_client,
            "check_message_client": self._check_message_client,
            "get_message_client": self._get_message_client,
            "test_message_client": self._test_message_client,
            "get_sites": self._get_sites,
            "get_indexers": self._get_indexers,
            "get_download_dirs": self._get_download_dirs,
            "find_hardlinks": self._find_hardlinks,
            "update_site_cookie_ua": self._update_site_cookie_ua,
            "set_site_captcha_code": self._set_site_captcha_code,
            "update_torrent_remove_task": self._update_torrent_remove_task,
            "get_torrent_remove_task": self._get_torrent_remove_task,
            "delete_torrent_remove_task": self._delete_torrent_remove_task,
            "get_remove_torrents": self._get_remove_torrents,
            "auto_remove_torrents": self._auto_remove_torrents,
            "list_brushtask_torrents": self._list_brushtask_torrents,
            "set_system_config": self._set_system_config,
            "get_site_user_statistics": self.get_site_user_statistics,
            "send_plugin_message": self.send_plugin_message,
            "send_custom_message": self.send_custom_message,
            "media_detail": self.media_detail,
            "media_similar": self._media_similar,
            "media_recommendations": self._media_recommendations,
            "media_person": self._media_person,
            "person_medias": self._person_medias,
            "save_user_script": self._save_user_script,
            "run_directory_sync": self._run_directory_sync,
            "update_plugin_config": self._update_plugin_config,
            "get_season_episodes": self._get_season_episodes,
            "get_user_menus": self.get_user_menus,
            "get_top_menus": self.get_top_menus,
            "update_downloader": self._update_downloader,
            "del_downloader": self._del_downloader,
            "check_downloader": self._check_downloader,
            "get_downloaders": self._get_downloaders,
            "test_downloader": self._test_downloader,
            "get_indexer_statistics": self._get_indexer_statistics,
            "media_path_scrap": self._media_path_scrap,
            "get_default_rss_setting": self.get_default_rss_setting,
            "get_movie_rss_items": self.get_movie_rss_items,
            "get_tv_rss_items": self.get_tv_rss_items,
            "get_ical_events": self.get_ical_events,
            "install_plugin": self.install_plugin,
            "uninstall_plugin": self.uninstall_plugin,
            "get_plugin_apps": self.get_plugin_apps,
            "get_plugin_page": self.get_plugin_page,
            "get_plugin_state": self.get_plugin_state,
            "get_plugins_conf": self.get_plugins_conf,
            "update_category_config": self.update_category_config,
            "get_category_config": self.get_category_config,
            "get_system_processes": self.get_system_processes,
            "run_plugin_method": self.run_plugin_method,
            "update_all_config": self._update_all_config,
            "add_tmdb_blacklist": self._add_tmdb_blacklist,
            "delete_tmdb_blacklist": self._delete_tmdb_blacklist,
            "clear_tmdb_blacklist": self._clear_tmdb_blacklist,
            # RBAC 用户管理
            "create_user": self._create_user,
            "update_user": self._update_user,
            "delete_user": self._delete_user,
            "get_user": self._get_user,
            "reset_password": self._reset_password,
            # RBAC 角色管理
            "create_role": self._create_role,
            "update_role": self._update_role,
            "delete_role": self._delete_role,
            "get_role": self._get_role,
            # RBAC 菜单管理
            "create_menu": self._create_menu,
            "update_menu": self._update_menu,
            "delete_menu": self._delete_menu,
            "get_menu": self._get_menu,
            "update_menu_sort": self._update_menu_sort
        }
        # 远程命令响应
        self._commands = {
            "/ptr": {"func": TorrentRemover().auto_remove_torrents, "desc": "自动删种"},
            "/ptt": {"func": Downloader().transfer, "desc": "下载文件转移"},
            "/rst": {"func": Sync().transfer_sync, "desc": "目录同步"},
            "/rss": {"func": Rss().rssdownload, "desc": "电影/电视剧订阅"},
            "/ssa": {"func": Subscribe().subscribe_search_all, "desc": "订阅搜索"},
            "/tbl": {"func": self.truncate_blacklist, "desc": "清理转移缓存"},
            "/trh": {"func": self.truncate_rsshistory, "desc": "清理RSS缓存"},
            "/utf": {"func": self.unidentification, "desc": "重新识别"},
            "/udt": {"func": self.update_system, "desc": "系统更新"},
            "/sta": {"func": self.user_statistics, "desc": "站点数据统计"}
        }
        # 远程命令响应
        self._commands = {
            "/ptr": {"func": TorrentRemover().auto_remove_torrents, "desc": "自动删种"},
            "/ptt": {"func": Downloader().transfer, "desc": "下载文件转移"},
            "/rst": {"func": Sync().transfer_sync, "desc": "目录同步"},
            "/rss": {"func": Rss().rssdownload, "desc": "电影/电视剧订阅"},
            "/ssa": {"func": Subscribe().subscribe_search_all, "desc": "订阅搜索"},
            "/tbl": {"func": self.truncate_blacklist, "desc": "清理转移缓存"},
            "/trh": {"func": self.truncate_rsshistory, "desc": "清理RSS缓存"},
            "/utf": {"func": self.unidentification, "desc": "重新识别"},
            "/udt": {"func": self.update_system, "desc": "系统更新"},
            "/sta": {"func": self.user_statistics, "desc": "站点数据统计"}
        }

    def action(self, cmd, data):
        """
        执行WEB请求
        """
        func = self._actions.get(cmd)
        if not func:
            return self._fail(code=-1, msg="非授权访问！")
        elif inspect.signature(func).parameters:
            return func(data)
        else:
            return func(**{})

    def api_action(self, cmd, data=None):
        """
        执行API请求
        """
        result = self.action(cmd, data)
        if not result:
            return self._fail(code=-1, success=False, message="服务异常，未获取到返回结果")
        code = result.get("code", result.get("retcode", 0))
        if not code or str(code) == "0":
            success = True
        else:
            success = False
        message = result.get("msg", result.get("retmsg", ""))
        for key in ['code', 'retcode', 'msg', 'retmsg']:
            if key in result:
                result.pop(key)
        return self._fail(code=code, success=success, message=message, data=result)

    @staticmethod
    def stop_service():
        """
        关闭服务
        """
        # 停止定时服务
        Scheduler().stop_service()
        # 停止监控
        Sync().stop_service()
        # 关闭刷流
        BrushTask().stop_service()
        # 关闭自定义订阅
        RssChecker().stop_service()
        # 关闭自动删种
        TorrentRemover().stop_service()
        # 关闭下载器监控
        Downloader().stop_service()
        # 关闭插件
        PluginManager().stop_service()
        # 关闭浏览器标签页
        DrissionPageHelper().close_all_tabs()

    @staticmethod
    def start_service():
        # 加载索引器配置
        IndexerHelper()
        # 加载站点配置
        SiteConf()
        # 启动定时服务
        Scheduler()
        # 启动监控服务
        Sync()
        # 启动刷流服务
        BrushTask()
        # 启动自定义订阅服务
        RssChecker()
        # 启动自动删种服务
        TorrentRemover()
        # 加载插件
        PluginManager()

    def restart_service(self):
        """
        重启服务
        """
        self.stop_service()
        self.start_service()

    def restart_server(self):
        """
        停止进程
        """
        # 关闭服务
        self.stop_service()
        # 重启进程
        script_path = os.path.join(os.getcwd(), 'restart-server.sh')
        os.chmod(script_path, 0o755)
        res = subprocess.run(['bash', script_path], cwd=os.getcwd())
        if res.returncode == 0:
            log.info("Nastool 重启成功...")
        else:
            log.info(f"Nastool 重启失败: {res.stderr.decode()}")

    def handle_message_job(self, msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """
        处理消息事件
        """
        if not msg:
            return

        # 触发MessageIncoming事件
        EventManager().send_event(EventType.MessageIncoming, {
            "channel": in_from.value,
            "user_id": user_id,
            "user_name": user_name,
            "message": msg

        })

        # 系统内置命令
        command = self._commands.get(msg)
        if command:
            # 启动服务
            ThreadHelper().start_thread(command.get("func"), ())
            # 消息回应
            Message().send_channel_msg(
                channel=in_from, title="正在运行 %s ..." % command.get("desc"), user_id=user_id)
            return

        # 插件命令
        plugin_commands = PluginManager().get_plugin_commands()
        msg_list = msg.split(" ")
        for command in plugin_commands:
            if command.get("cmd") == msg_list[0]:
                # 发送事件
                event_data = command.get("data") or {
                    "msg": msg_list[0] if len(msg_list) == 1 else msg_list[1]}
                EventManager().send_event(command.get("event"), event_data)
                # 消息回应
                Message().send_channel_msg(
                    channel=in_from, title="正在运行 %s ..." % command.get("desc"), user_id=user_id)
                return

        cache.delete("search")
        # 站点搜索或者添加订阅
        ThreadHelper().start_thread(search_media_by_message,
                                    (msg, in_from, user_id, user_name))

    @staticmethod
    def set_config_value(cfg, cfg_key, cfg_value):
        """
        根据Key设置配置值
        """
        # 密码
        if cfg_key == "app.login_password":
            if cfg_value and not cfg_value.startswith("[hash]"):
                cfg['app']['login_password'] = "[hash]%s" % generate_password_hash(
                    cfg_value)
            else:
                cfg['app']['login_password'] = cfg_value or "password"
            return cfg
        # 代理
        if cfg_key == "app.proxies":
            if cfg_value:
                if not cfg_value.startswith("http") and not cfg_value.startswith("sock"):
                    cfg['app']['proxies'] = {
                        "https": "http://%s" % cfg_value, "http": "http://%s" % cfg_value}
                else:
                    cfg['app']['proxies'] = {"https": "%s" %
                                                      cfg_value, "http": "%s" % cfg_value}
            else:
                cfg['app']['proxies'] = {"https": None, "http": None}
            return cfg
        # 最大支持三层赋值
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if not cfg.get(keys[0]):
                    cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = cfg_value
            elif len(keys) == 3:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]) or isinstance(cfg[keys[0]][keys[1]], str):
                        cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value

        return cfg

    @staticmethod
    def _success(data=None, **kwargs):
        """统一成功返回格式"""
        result = {"code": 0}
        if data is not None:
            result["data"] = data
        result.update(kwargs)
        return result

    @staticmethod
    def _fail(code=1, msg="", **kwargs):
        """统一失败返回格式"""
        result = {"code": code, "msg": msg}
        result.update(kwargs)
        return result

    @staticmethod
    def set_config_directory(cfg, oper, cfg_key, cfg_value, update_value=None):
        """
        更新目录数据
        """

        def remove_sync_path(obj, key):
            if not isinstance(obj, list):
                return []
            ret_obj = []
            for item in obj:
                if item.split("@")[0].replace("\\", "/") != key.split("@")[0].replace("\\", "/"):
                    ret_obj.append(item)
            return ret_obj

        # 最大支持二层赋值
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                if cfg.get(keys[0]):
                    if not isinstance(cfg[keys[0]], list):
                        cfg[keys[0]] = [cfg[keys[0]]]
                    if oper == "add":
                        cfg[keys[0]].append(cfg_value)
                    elif oper == "sub":
                        cfg[keys[0]].remove(cfg_value)
                        if not cfg[keys[0]]:
                            cfg[keys[0]] = None
                    elif oper == "set":
                        cfg[keys[0]].remove(cfg_value)
                        if update_value:
                            cfg[keys[0]].append(update_value)
                else:
                    cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]):
                        cfg[keys[0]][keys[1]] = []
                    if not isinstance(cfg[keys[0]][keys[1]], list):
                        cfg[keys[0]][keys[1]] = [cfg[keys[0]][keys[1]]]
                    if oper == "add":
                        cfg[keys[0]][keys[1]].append(
                            cfg_value.replace("\\", "/"))
                    elif oper == "sub":
                        cfg[keys[0]][keys[1]] = remove_sync_path(
                            cfg[keys[0]][keys[1]], cfg_value)
                        if not cfg[keys[0]][keys[1]]:
                            cfg[keys[0]][keys[1]] = None
                    elif oper == "set":
                        cfg[keys[0]][keys[1]] = remove_sync_path(
                            cfg[keys[0]][keys[1]], cfg_value)
                        if update_value:
                            cfg[keys[0]][keys[1]].append(
                                update_value.replace("\\", "/"))
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = cfg_value.replace("\\", "/")
        return cfg

    @staticmethod
    def delete_media_file(filedir, filename):
        """
        删除媒体文件，空目录也会被删除
        """
        filedir = os.path.normpath(filedir).replace("\\", "/")
        file = os.path.join(filedir, filename)
        try:
            if not os.path.exists(file):
                return False, f"{file} 不存在"
            os.remove(file)
            nfoname = f"{os.path.splitext(filename)[0]}.nfo"
            nfofile = os.path.join(filedir, nfoname)
            if os.path.exists(nfofile):
                os.remove(nfofile)
            # 检查空目录并删除
            if re.findall(r"^S\d{2}|^Season", os.path.basename(filedir), re.I):
                # 当前是季文件夹，判断并删除
                seaon_dir = filedir
                if seaon_dir.count('/') > 1 and not PathUtils.get_dir_files(seaon_dir, exts=RMT_MEDIAEXT):
                    shutil.rmtree(seaon_dir)
                # 媒体文件夹
                media_dir = os.path.dirname(seaon_dir)
            else:
                media_dir = filedir
            # 检查并删除媒体文件夹，非根目录且目录大于二级，且没有媒体文件时才会删除
            if media_dir != '/' \
                    and media_dir.count('/') > 1 \
                    and not re.search(r'[a-zA-Z]:/$', media_dir) \
                    and not PathUtils.get_dir_files(media_dir, exts=RMT_MEDIAEXT):
                shutil.rmtree(media_dir)
            return True, f"{file} 删除成功"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return True, f"{file} 删除失败"

    @staticmethod
    def mediainfo_dict(media_info):
        if not media_info:
            return {}
        tmdb_id = media_info.tmdb_id
        tmdb_link = media_info.get_detail_url()
        tmdb_S_E_link = ""
        if tmdb_id:
            if media_info.get_season_string():
                tmdb_S_E_link = "%s/season/%s" % (tmdb_link,
                                                  media_info.get_season_seq())
                if media_info.get_episode_string():
                    tmdb_S_E_link = "%s/episode/%s" % (
                        tmdb_S_E_link, media_info.get_episode_seq())
        return {
            "type": media_info.type.value if media_info.type else "",
            "name": media_info.get_name(),
            "title": media_info.title,
            "year": media_info.year,
            "season_episode": media_info.get_season_episode_string(),
            "part": media_info.part,
            "tmdbid": tmdb_id,
            "tmdblink": tmdb_link,
            "tmdb_S_E_link": tmdb_S_E_link,
            "category": media_info.category,
            "restype": media_info.resource_type,
            "effect": media_info.resource_effect,
            "pix": media_info.resource_pix,
            "team": media_info.resource_team,
            "customization": media_info.customization,
            "video_codec": media_info.video_encode,
            "audio_codec": media_info.audio_encode,
            "org_string": media_info.org_string,
            "rev_string": media_info.rev_string,
            "ignored_words": media_info.ignored_words,
            "replaced_words": media_info.replaced_words,
            "offset_words": media_info.offset_words
        }

    @staticmethod
    def get_media_exists_info(mtype, title, year, mediaid):
        """
        获取媒体存在标记：是否存在、是否订阅
        :param: mtype 媒体类型
        :param: title 媒体标题
        :param: year 媒体年份
        :param: mediaid TMDBID/DB:豆瓣ID/BG:Bangumi的ID
        :return: 1-已订阅/2-已下载/0-不存在未订阅, RSSID, 如果已下载,还会有对应的媒体库的播放地址链接
        """
        if str(mediaid).isdigit():
            tmdbid = mediaid
        else:
            tmdbid = None
        if mtype in MovieTypes:
            rssid = Subscribe().get_subscribe_id(mtype=MediaType.MOVIE,
                                                 title=title,
                                                 year=year,
                                                 tmdbid=tmdbid)
        else:
            if not tmdbid:
                meta_info = MetaInfo(title=title)
                title = meta_info.get_name()
                season = meta_info.get_season_string()
                if season:
                    year = None
            else:
                season = None
            rssid = Subscribe().get_subscribe_id(mtype=MediaType.TV,
                                                 title=title,
                                                 year=year,
                                                 season=season,
                                                 tmdbid=tmdbid)
        item_url = None
        if rssid:
            # 已订阅
            fav = "1"
        else:
            # 检查媒体服务器是否存在
            item_id = MediaServer().check_item_exists(
                mtype=mtype, title=title, year=year, tmdbid=tmdbid)
            if item_id:
                # 已下载
                fav = "2"
                item_url = MediaServer().get_play_url(item_id=item_id)
            else:
                # 未订阅、未下载
                fav = "0"
        return fav, rssid, item_url

    @staticmethod
    def backup(full_backup=False, bk_path=None):
        """
        @param full_backup  是否完整备份
        @param bk_path     自定义备份路径
        """
        try:
            # 创建备份文件夹
            config_path = Path(Config().get_config_path())
            backup_file = f"bk_{time.strftime('%Y%m%d%H%M%S')}"
            if bk_path:
                backup_path = Path(bk_path) / backup_file
            else:
                backup_path = config_path / "backup_file" / backup_file
            backup_path.mkdir(parents=True)
            # 把现有的相关文件进行copy备份
            shutil.copy(f'{config_path}/config.yaml', backup_path)
            shutil.copy(f'{config_path}/default-category.yaml', backup_path)
            shutil.copy(f'{config_path}/user.db', backup_path)

            # 完整备份不删除表
            if not full_backup:
                conn = sqlite3.connect(f'{backup_path}/user.db')
                cursor = conn.cursor()
                # 执行操作删除不需要备份的表
                table_list = [
                    'SEARCH_RESULT_INFO',
                    'RSS_TORRENTS',
                    'DOUBAN_MEDIAS',
                    'TRANSFER_HISTORY',
                    'TRANSFER_UNKNOWN',
                    'TRANSFER_BLACKLIST',
                    'SYNC_HISTORY',
                    'DOWNLOAD_HISTORY',
                    'alembic_version'
                ]
                for table in table_list:
                    cursor.execute(f"""DROP TABLE IF EXISTS {table};""")
                conn.commit()
                cursor.close()
                conn.close()
            zip_file = str(backup_path) + '.zip'
            if os.path.exists(zip_file):
                zip_file = str(backup_path) + '.zip'
            shutil.make_archive(str(backup_path), 'zip', str(backup_path))
            shutil.rmtree(str(backup_path))
            return zip_file
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return None

    def get_commands(self):
        """
        获取命令列表
        """
        return [{
            "id": cid,
            "name": cmd.get("desc")
        } for cid, cmd in self._commands.items()] + [{
            "id": item.get("cmd"),
            "name": item.get("desc")
        } for item in PluginManager().get_plugin_commands()]

    @staticmethod
    def get_system_processes():
        """
        获取系统进程
        """
        return WebActionBase._success(data=SystemUtils.get_all_processes())

    @staticmethod
    def get_system_message(lst_time):
        messages = MessageCenter().get_system_messages(lst_time=lst_time)
        if messages:
            lst_time = messages[0].get("time")
        return WebActionBase._success(message=messages, lst_time=lst_time)

    @staticmethod
    def user_statistics():
        """
        强制刷新站点数据,并发送站点统计的消息
        """
        cache.delete("statistics")
        # 强制刷新站点数据,并发送站点统计的消息
        SiteUserInfo().refresh_site_data_now()

    @staticmethod
    def get_rmt_modes():
        RmtModes = ModuleConf.RMT_MODES_LITE if SystemUtils.is_lite_version(
        ) else ModuleConf.RMT_MODES
        return [{
            "value": value,
            "name": name.value
        } for value, name in RmtModes.items()]
