import os
import re
import shutil
import subprocess

import log
from app.conf import ModuleConf
from app.helper.drissionpage_helper import DrissionPageHelper
from app.media.meta import MetaInfo
from app.mediaserver import MediaServer
from app.services.subscribe_service import SubscribeService as Subscribe
from app.utils import PathUtils, ExceptionUtils
from app.utils.types import SearchType, MediaType, MovieTypes
from config import RMT_MEDIAEXT, Config
from web.backend.search_torrents import search_media_by_message
from web.cache import cache
from werkzeug.security import generate_password_hash


def stop_service():
    """停止服务（统一收口到 system_service）"""
    from app.services.system_service import SystemLifecycleService
    SystemLifecycleService().stop_service()
    DrissionPageHelper().close_all_tabs()


def start_service():
    """启动服务（统一收口到 system_service）"""
    from app.services.system_service import SystemLifecycleService
    SystemLifecycleService().start_service()


def restart_service():
    """重启服务"""
    stop_service()
    start_service()


def restart_server():
    """停止进程"""
    stop_service()
    script_path = os.path.join(os.getcwd(), 'restart-server.sh')
    os.chmod(script_path, 0o755)
    res = subprocess.run(['bash', script_path], cwd=os.getcwd())
    if res.returncode == 0:
        log.info("Nastool 重启成功...")
    else:
        log.info(f"Nastool 重启失败: {res.stderr.decode()}")


def set_config_value(cfg, cfg_key, cfg_value):
    """
    根据Key设置配置值
    """
    if cfg_key == "app.login_password":
        if cfg_value and not cfg_value.startswith("[hash]"):
            cfg['app']['login_password'] = "[hash]%s" % generate_password_hash(
                cfg_value)
        else:
            cfg['app']['login_password'] = cfg_value or "password"
        return cfg
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
        if re.findall(r"^S\d{2}|^Season", os.path.basename(filedir), re.I):
            seaon_dir = filedir
            if seaon_dir.count('/') > 1 and not PathUtils.get_dir_files(seaon_dir, exts=RMT_MEDIAEXT):
                shutil.rmtree(seaon_dir)
            media_dir = os.path.dirname(seaon_dir)
        else:
            media_dir = filedir
        if media_dir != '/' \
                and media_dir.count('/') > 1 \
                and not re.search(r'[a-zA-Z]:/$', media_dir) \
                and not PathUtils.get_dir_files(media_dir, exts=RMT_MEDIAEXT):
            shutil.rmtree(media_dir)
        return True, f"{file} 删除成功"
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return True, f"{file} 删除失败"


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


def get_media_exists_info(mtype, title, year, mediaid):
    """
    获取媒体存在标记：是否存在、是否订阅
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
        fav = "1"
    else:
        item_id = MediaServer().check_item_exists(
            mtype=mtype, title=title, year=year, tmdbid=tmdbid)
        if item_id:
            fav = "2"
            item_url = MediaServer().get_play_url(item_id=item_id)
        else:
            fav = "0"
    return fav, rssid, item_url
