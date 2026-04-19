from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from web.core.action_utils import set_config_directory, delete_media_file
import importlib
import os.path
import re
import shutil
from urllib.parse import unquote
import log
from app.conf import ModuleConf
from app.filetransfer import FileTransfer
from app.helper import ThreadHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.plugins import EventManager
from app.services.sync_service import SyncService
from app.sync import Sync
from app.utils import StringUtils, EpisodeFormat, PathUtils, SystemUtils, ExceptionUtils
from app.utils.types import RmtMode, OsType, SyncType, MediaType, MovieTypes, TvTypes
from config import RMT_MEDIAEXT, RMT_SUBEXT, RMT_AUDIO_TRACK_EXT, Config

sync_bp = Blueprint("sync", __name__, url_prefix="/api/web/sync")


@sync_bp.route('/add_or_edit_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _add_or_edit_sync_path(data):
    ok, msg = SyncService().add_or_edit_sync_path(
        sid=data.get("sid"),
        source=data.get("from"),
        dest=data.get("to"),
        unknown=data.get("unknown"),
        mode=data.get("syncmod"),
        compatibility=data.get("compatibility"),
        rename=data.get("rename"),
        enabled=data.get("enabled")
    )
    if ok:
        return success(msg=msg)
    return fail(msg=msg)


@sync_bp.route('/check_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _check_sync_path(data):
    ok, msg = SyncService().check_sync_path(
        sid=data.get("sid"),
        flag=data.get("flag"),
        checked=data.get("checked")
    )
    if ok:
        return success()
    return fail()


@sync_bp.route('/del_unknown_path', methods=['POST'])
@any_auth
@parse_json_data
def _del_unknown_path(data):
    tids = data.get("id")
    if isinstance(tids, list):
        for tid in tids:
            if not tid:
                continue
            FileTransfer().delete_transfer_unknown(tid)
        return success()
    else:
        retcode = FileTransfer().delete_transfer_unknown(tids)
        return fail(code=retcode)


@sync_bp.route('/delete_files', methods=['POST'])
@any_auth
@parse_json_data
def _delete_files(data):
    files = data.get("files")
    if files:
        for file in files:
            del_flag, del_msg = delete_media_file(
                filedir=os.path.dirname(file),
                filename=os.path.basename(file)
            )
            if not del_flag:
                log.error(del_msg)
            else:
                log.info(del_msg)
    return success()


@sync_bp.route('/delete_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _delete_sync_path(data):
    sid = data.get("sid")
    Sync().delete_sync_path(sid)
    return success()


@sync_bp.route('/exec_test_command', methods=['POST'])
@any_auth
@parse_json_data
def _exec_test_command(data):
    cmd = data.get("command", "") if isinstance(data, dict) else str(data)
    m = re.match(r"^(\w+)\(\)\.(\w+)\(\)$", cmd.strip())
    if not m:
        return None
    obj_name, method_name = m.groups()
    safe_mapping = {
        "Config": ("config", "Config"),
        "Message": ("app.message", "Message"),
        "MessageCenter": ("app.message", "MessageCenter"),
        "Downloader": ("app.downloader", "Downloader"),
        "MediaServer": ("app.mediaserver", "MediaServer"),
        "Indexer": ("app.indexer", "Indexer"),
        "Sites": ("app.sites", "Sites"),
        "Sync": ("app.sync", "Sync"),
        "BrushTask": ("app.brushtask", "BrushTask"),
        "RssChecker": ("app.services.rss_service", "RssTaskService"),
        "TorrentRemover": ("app.torrentremover", "TorrentRemover"),
        "Rss": ("app.rss", "Rss"),
        "Subscribe": ("app.subscribe", "Subscribe"),
        "SchedulerCore": ("app.services.scheduler_core", "SchedulerCore"),
        "PluginManager": ("app.plugins", "PluginManager"),
        "Scraper": ("app.media", "Scraper"),
    }
    module_path, class_name = safe_mapping.get(obj_name, (None, None))
    if not module_path:
        return None
    try:
        cls = getattr(importlib.import_module(module_path), class_name)
        obj = cls()
        if hasattr(obj, method_name):
            return getattr(obj, method_name)()
    except Exception:
        pass
    return None


@sync_bp.route('/get_sub_path', methods=['POST'])
@any_auth
@parse_json_data
def _get_sub_path(data):
    r = []
    try:
        ft = data.get("filter") or "ALL"
        d = data.get("dir")
        if not d or d == "/":
            if SystemUtils.get_system() == OsType.WINDOWS:
                partitions = SystemUtils.get_windows_drives()
                if partitions:
                    dirs = [os.path.join(partition, "/")
                            for partition in partitions]
                else:
                    dirs = [os.path.join("C:/", f)
                            for f in os.listdir("C:/")]
            else:
                dirs = [os.path.join("/", f) for f in os.listdir("/")]
        else:
            d = os.path.normpath(unquote(d))
            if not os.path.isdir(d):
                d = os.path.dirname(d)
            dirs = [os.path.join(d, f) for f in os.listdir(d)]
        dirs.sort()
        for ff in dirs:
            if os.path.isdir(ff):
                if 'ONLYDIR' in ft or 'ALL' in ft:
                    r.append({
                        "path": ff.replace("\\", "/"),
                        "name": os.path.basename(ff),
                        "type": "dir",
                        "rel": os.path.dirname(ff).replace("\\", "/")
                    })
            else:
                ext = os.path.splitext(ff)[-1][1:]
                flag = False
                if 'ONLYFILE' in ft or 'ALL' in ft:
                    flag = True
                elif "MEDIAFILE" in ft and f".{str(ext).lower()}" in RMT_MEDIAEXT:
                    flag = True
                elif "SUBFILE" in ft and f".{str(ext).lower()}" in RMT_SUBEXT:
                    flag = True
                elif "AUDIOTRACKFILE" in ft and f".{str(ext).lower()}" in RMT_AUDIO_TRACK_EXT:
                    flag = True
                if flag:
                    r.append({
                        "path": ff.replace("\\", "/"),
                        "name": os.path.basename(ff),
                        "type": "file",
                        "rel": os.path.dirname(ff).replace("\\", "/"),
                        "ext": ext,
                        "size": StringUtils.str_filesize(os.path.getsize(ff))
                    })
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(code=-1, message='加载路径失败: %s' % str(e))
    return success(count=len(r), data=r)


@sync_bp.route('/rename', methods=['POST'])
@any_auth
@parse_json_data
def _rename(data):
    path = dest_dir = None
    syncmod = SyncService.resolve_rmt_mode(data.get("syncmod"))
    logid = data.get("logid")
    svc = SyncService()
    if logid:
        transinfo = svc.get_transfer_info_by_id(logid)
        if transinfo:
            path = os.path.join(transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
            dest_dir = transinfo.DEST
        else:
            return fail(code=-1, msg="未查询到转移日志记录")
    else:
        unknown_id = data.get("unknown_id")
        if unknown_id:
            inknowninfo = svc.get_unknown_info_by_id(unknown_id)
            if inknowninfo:
                path = inknowninfo.PATH
                dest_dir = inknowninfo.DEST
            else:
                return fail(code=-1, msg="未查询到未识别记录")
    if not dest_dir:
        dest_dir = ""
    if not path:
        return fail(code=-1, msg="输入路径有误")

    tmdbid = data.get("tmdb")
    mtype = data.get("type")
    season = data.get("season")
    episode_format = data.get("episode_format")
    episode_details = data.get("episode_details")
    episode_part = data.get("episode_part")
    episode_offset = data.get("episode_offset")
    min_filesize = data.get("min_filesize")
    media_type = SyncService.build_media_type(mtype)
    need_fix_all = False
    if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT and episode_format:
        path = os.path.dirname(path)
        need_fix_all = True

    result = svc.manual_transfer(
        inpath=path, syncmod=syncmod, outpath=dest_dir,
        media_type=media_type, episode_format=episode_format,
        episode_details=episode_details, episode_part=episode_part,
        episode_offset=episode_offset, min_filesize=min_filesize,
        tmdbid=tmdbid, season=season, need_fix_all=need_fix_all
    )
    if result.success:
        if not need_fix_all and not logid:
            FileTransfer().update_transfer_unknown_state(path)
        return success(msg="转移成功")
    return fail(code=2, msg=result.message)


@sync_bp.route('/rename_file', methods=['POST'])
@any_auth
@parse_json_data
def _rename_file(data):
    path = data.get("path")
    name = data.get("name")
    if path and name:
        try:
            shutil.move(path, os.path.join(os.path.dirname(path), name))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(code=-1, msg=str(e))
    return success()


@sync_bp.route('/rename_udf', methods=['POST'])
@any_auth
@parse_json_data
def _rename_udf(data):
    inpath = data.get("inpath")
    if not os.path.exists(inpath):
        return fail(code=-1, msg="输入路径不存在")
    outpath = data.get("outpath")
    syncmod = SyncService.resolve_rmt_mode(data.get("syncmod"))
    tmdbid = data.get("tmdb")
    mtype = data.get("type")
    season = data.get("season")
    episode_format = data.get("episode_format")
    episode_details = data.get("episode_details")
    episode_part = data.get("episode_part")
    episode_offset = data.get("episode_offset")
    min_filesize = data.get("min_filesize")
    media_type = SyncService.build_media_type(mtype)

    result = SyncService().manual_transfer(
        inpath=inpath, syncmod=syncmod, outpath=outpath,
        media_type=media_type, episode_format=episode_format,
        episode_details=episode_details, episode_part=episode_part,
        episode_offset=episode_offset, min_filesize=min_filesize,
        tmdbid=tmdbid, season=season
    )
    if result.success:
        return success(msg="转移成功")
    return fail(code=2, msg=result.message)


@sync_bp.route('/run_directory_sync', methods=['POST'])
@any_auth
@parse_json_data
def _run_directory_sync(data):
    ThreadHelper().start_thread(Sync().transfer_sync, (data.get("sid"),))
    return success(msg="执行成功")


@sync_bp.route('/test_connection', methods=['POST'])
@any_auth
@parse_json_data
def _test_connection(data):
    command = data.get("command")
    ret = None
    module_obj = None
    if command:
        try:
            if isinstance(command, list):
                for cmd_str in command:
                    ret = _exec_test_command(cmd_str)
                    if not ret:
                        break
            else:
                if command.find("|") != -1:
                    module = command.split("|")[0]
                    class_name = command.split("|")[1]
                    module_obj = getattr(
                        importlib.import_module(module), class_name)()
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
                    ret = module_obj.get_status()
                else:
                    ret = _exec_test_command(command)
            Config().init_config()
            if module_obj:
                if hasattr(module_obj, "init_config"):
                    module_obj.init_config()
        except Exception as e:
            ret = None
            ExceptionUtils.exception_traceback(e)
        return fail(code=0 if ret else 1)
    return success()


@sync_bp.route('/update_directory', methods=['POST'])
@any_auth
@parse_json_data
def _update_directory(data):
    cfg = set_config_directory(Config().get_config(),
                               data.get("oper"),
                               data.get("key"),
                               data.get("value"),
                               data.get("replace_value"))
    Config().save_config(cfg)
    return success()


@sync_bp.route('/delete_history', methods=['POST'])
@any_auth
@parse_json_data
def delete_history(data):
    logids = data.get('logids') or []
    flag = data.get('flag')
    FileTransfer().delete_history(logids=logids, flag=flag)
    return success()


@sync_bp.route('/get_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def get_sync_path(data):
    sync_path = SyncService().get_sync_paths(sid=data.get("sid") if data else None)
    return success(result=sync_path)


@sync_bp.route('/re_identification', methods=['POST'])
@any_auth
@parse_json_data
def re_identification(data):
    flag = data.get("flag")
    ids = data.get("ids")
    result = SyncService().re_identify_items(flag=flag, ids=ids)
    if result.success:
        return success(msg=result.message)
    return fail(code=2, msg=result.message)
