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
from app.sync import Sync
from app.utils import StringUtils, EpisodeFormat, PathUtils, SystemUtils, ExceptionUtils
from app.utils.types import RmtMode, OsType, SyncType, MediaType, MovieTypes, TvTypes, EventType
from config import RMT_MEDIAEXT, RMT_SUBEXT, RMT_AUDIO_TRACK_EXT, Config

sync_bp = Blueprint("sync", __name__, url_prefix="/api/web/sync")

@sync_bp.route('/add_or_edit_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _add_or_edit_sync_path(data):
        """
        维护同步目录
        """
        sid = data.get("sid")
        source = data.get("from")
        dest = data.get("to")
        unknown = data.get("unknown")
        mode = data.get("syncmod")
        compatibility = data.get("compatibility")
        rename = data.get("rename")
        enabled = data.get("enabled")

        _sync = Sync()

        # 源目录检查
        if not source:
            return fail(msg=f'源目录不能为空')
        if not os.path.exists(source):
            return fail(msg=f'{source}目录不存在')
        # windows目录用\，linux目录用/
        source = os.path.normpath(source)
        # 目的目录检查，目的目录可为空
        if dest:
            dest = os.path.normpath(dest)
            if PathUtils.is_path_in_path(source, dest):
                return fail(msg="目的目录不可包含在源目录中")
        if unknown:
            unknown = os.path.normpath(unknown)

        # 硬链接不能跨盘
        if mode == "link" and dest:
            common_path = os.path.commonprefix([source, dest])
            if not common_path or common_path == "/":
                return fail(msg="硬链接不能跨盘")

        # 编辑先删再增
        if sid:
            _sync.delete_sync_path(sid)
        # 若启用，则关闭其他相同源目录的同步目录
        if enabled == 1:
            _sync.check_source(source=source)
        # 插入数据库
        _sync.insert_sync_path(source=source,
                               dest=dest,
                               unknown=unknown,
                               mode=mode,
                               compatibility=compatibility,
                               rename=rename,
                               enabled=enabled)
        return success(msg="")

@sync_bp.route('/check_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _check_sync_path(data):
        """
        维护同步目录
        """
        flag = data.get("flag")
        sid = data.get("sid")
        checked = data.get("checked")

        _sync = Sync()

        if flag == "compatibility":
            _sync.check_sync_paths(sid=sid, compatibility=1 if checked else 0)
            return success()
        elif flag == "rename":
            _sync.check_sync_paths(sid=sid, rename=1 if checked else 0)
            return success()
        elif flag == "enable":
            # 若启用，则关闭其他相同源目录的同步目录
            if checked:
                _sync.check_source(sid=sid)
            _sync.check_sync_paths(sid=sid, enabled=1 if checked else 0)
            return success()
        else:
            return fail()

@sync_bp.route('/del_unknown_path', methods=['POST'])
@any_auth
@parse_json_data
def _del_unknown_path(data):
        """
        删除路径
        """
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
        """
        删除文件
        """
        files = data.get("files")
        if files:
            # 删除文件
            for file in files:
                del_flag, del_msg = delete_media_file(filedir=os.path.dirname(file),
                                                           filename=os.path.basename(file))
                if not del_flag:
                    log.error(del_msg)
                else:
                    log.info(del_msg)
        return success()

@sync_bp.route('/delete_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def _delete_sync_path(data):
        """
        移出同步目录
        """
        sid = data.get("sid")
        Sync().delete_sync_path(sid)
        return success()

@sync_bp.route('/exec_test_command', methods=['POST'])
@any_auth
@parse_json_data
def _exec_test_command(data):
        """
        安全执行测试命令（替换 eval）
        仅允许白名单内的无参调用：ClassName().method_name()
        """
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
            "RssChecker": ("app.rsschecker", "RssChecker"),
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
        """
        查询下级子目录
        """
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

def _manual_transfer(inpath,
                     syncmod,
                     outpath=None,
                     media_type=None,
                     episode_format=None,
                     episode_details=None,
                     episode_part=None,
                     episode_offset=None,
                     min_filesize=None,
                     tmdbid=None,
                     season=None,
                     need_fix_all=False
                     ):
        """
        开始手工转移文件
        """
        inpath = os.path.normpath(inpath)
        if outpath:
            outpath = os.path.normpath(outpath)
        if not os.path.exists(inpath):
            return False, "输入路径不存在"
        if tmdbid:
            # 有输入TMDBID
            tmdb_info = Media().get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
            if not tmdb_info:
                return False, "识别失败，无法查询到TMDB信息"
            # 按识别的信息转移
            succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=inpath,
                                                               rmt_mode=syncmod,
                                                               target_dir=outpath,
                                                               tmdb_info=tmdb_info,
                                                               media_type=media_type,
                                                               season=season,
                                                               episode=(
                                                                   EpisodeFormat(episode_format,
                                                                                 episode_details,
                                                                                 episode_part,
                                                                                 episode_offset),
                                                                   need_fix_all),
                                                               min_filesize=min_filesize,
                                                               udf_flag=True)
        else:
            # 按识别的信息转移
            succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=inpath,
                                                               rmt_mode=syncmod,
                                                               target_dir=outpath,
                                                               media_type=media_type,
                                                               episode=(
                                                                   EpisodeFormat(episode_format,
                                                                                 episode_details,
                                                                                 episode_part,
                                                                                 episode_offset),
                                                                   need_fix_all),
                                                               min_filesize=min_filesize,
                                                               udf_flag=True)
        return succ_flag, ret_msg

@sync_bp.route('/rename', methods=['POST'])
@any_auth
@parse_json_data
def _rename(data):
        """
        手工转移
        """
        path = dest_dir = None
        syncmod = ModuleConf.RMT_MODES.get(data.get("syncmod"))
        logid = data.get("logid")
        if logid:
            transinfo = FileTransfer().get_transfer_info_by_id(logid)
            if transinfo:
                path = os.path.join(
                    transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                dest_dir = transinfo.DEST
            else:
                return fail(code=-1, msg="未查询到转移日志记录")
        else:
            unknown_id = data.get("unknown_id")
            if unknown_id:
                inknowninfo = FileTransfer().get_unknown_info_by_id(unknown_id)
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
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        elif mtype in TvTypes:
            media_type = MediaType.TV
        else:
            media_type = MediaType.ANIME
        # 如果改次手动修复时一个单文件，自动修复改目录下同名文件，需要配合episode_format生效
        need_fix_all = False
        if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT and episode_format:
            path = os.path.dirname(path)
            need_fix_all = True
        # 开始转移
        succ_flag, ret_msg = _manual_transfer(inpath=path,
                                                   syncmod=syncmod,
                                                   outpath=dest_dir,
                                                   media_type=media_type,
                                                   episode_format=episode_format,
                                                   episode_details=episode_details,
                                                   episode_part=episode_part,
                                                   episode_offset=episode_offset,
                                                   need_fix_all=need_fix_all,
                                                   min_filesize=min_filesize,
                                                   tmdbid=tmdbid,
                                                   season=season)
        if succ_flag:
            if not need_fix_all and not logid:
                # 更新记录状态
                FileTransfer().update_transfer_unknown_state(path)
            return success(msg="转移成功")
        else:
            return fail(code=2, msg=ret_msg)

@sync_bp.route('/rename_file', methods=['POST'])
@any_auth
@parse_json_data
def _rename_file(data):
        """
        文件重命名
        """
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
        """
        自定义识别
        """
        inpath = data.get("inpath")
        if not os.path.exists(inpath):
            return fail(code=-1, msg="输入路径不存在")
        outpath = data.get("outpath")
        syncmod = ModuleConf.RMT_MODES.get(data.get("syncmod"))
        tmdbid = data.get("tmdb")
        mtype = data.get("type")
        season = data.get("season")
        episode_format = data.get("episode_format")
        episode_details = data.get("episode_details")
        episode_part = data.get("episode_part")
        episode_offset = data.get("episode_offset")
        min_filesize = data.get("min_filesize")
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        elif mtype in TvTypes:
            media_type = MediaType.TV
        else:
            media_type = MediaType.ANIME
        # 开始转移
        succ_flag, ret_msg = _manual_transfer(inpath=inpath,
                                                   syncmod=syncmod,
                                                   outpath=outpath,
                                                   media_type=media_type,
                                                   episode_format=episode_format,
                                                   episode_details=episode_details,
                                                   episode_part=episode_part,
                                                   episode_offset=episode_offset,
                                                   min_filesize=min_filesize,
                                                   tmdbid=tmdbid,
                                                   season=season)
        if succ_flag:
            return success(msg="转移成功")
        else:
            return fail(code=2, msg=ret_msg)

@sync_bp.route('/run_directory_sync', methods=['POST'])
@any_auth
@parse_json_data
def _run_directory_sync(data):
        """
        执行单个目录的目录同步
        """
        ThreadHelper().start_thread(Sync().transfer_sync, (data.get("sid"),))
        return success(msg="执行成功")

@sync_bp.route('/test_connection', methods=['POST'])
@any_auth
@parse_json_data
def _test_connection(data):
        """
        测试连通性（已移除 eval，使用安全反射）
        """
        # 支持两种传入方式：命令数组或单个命令，单个命令时xx|xx模式解析为模块和类，进行动态引入
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
                # 重载配置
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
        """
        维护媒体库目录
        """
        cfg = set_config_directory(Config().get_config(),
                                        data.get("oper"),
                                        data.get("key"),
                                        data.get("value"),
                                        data.get("replace_value"))
        # 保存配置
        Config().save_config(cfg)
        return success()

@sync_bp.route('/delete_history', methods=['POST'])
@any_auth
@parse_json_data
def delete_history(data):
        """
        删除识别记录及文件
        """
        logids = data.get('logids') or []
        flag = data.get('flag')
        FileTransfer().delete_history(logids=logids, flag=flag)
        return success()

@sync_bp.route('/get_sync_path', methods=['POST'])
@any_auth
@parse_json_data
def get_sync_path(data):
        """
        查询同步目录
        """
        if data:
            sync_path = Sync().get_sync_path_conf(sid=data.get("sid"))
        else:
            sync_path = Sync().get_sync_path_conf()
        return success(result=sync_path)

@sync_bp.route('/re_identification', methods=['POST'])
@any_auth
@parse_json_data
def re_identification(data):
        """
        未识别的重新识别
        """
        flag = data.get("flag")
        ids = data.get("ids")
        ret_flag = True
        ret_msg = []
        _filetransfer = FileTransfer()
        if flag == "unidentification":
            for wid in ids:
                unknowninfo = _filetransfer.get_unknown_info_by_id(wid)
                if unknowninfo:
                    path = unknowninfo.PATH
                    dest_dir = unknowninfo.DEST
                    rmt_mode = ModuleConf.get_enum_item(
                        RmtMode, unknowninfo.MODE) if unknowninfo.MODE else None
                else:
                    return fail(code=-1, msg="未查询到未识别记录")
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return fail(code=-1, msg="未识别路径有误")
                succ_flag, msg = _filetransfer.transfer_media(in_from=SyncType.MAN,
                                                              rmt_mode=rmt_mode,
                                                              in_path=path,
                                                              target_dir=dest_dir)
                if succ_flag:
                    _filetransfer.update_transfer_unknown_state(path)
                else:
                    ret_flag = False
                    if msg not in ret_msg:
                        ret_msg.append(msg)
        elif flag == "history":
            for wid in ids:
                transinfo = _filetransfer.get_transfer_info_by_id(wid)
                if transinfo:
                    path = os.path.join(
                        transinfo.SOURCE_PATH, transinfo.SOURCE_FILENAME)
                    dest_dir = transinfo.DEST
                    rmt_mode = ModuleConf.get_enum_item(
                        RmtMode, transinfo.MODE) if transinfo.MODE else None
                else:
                    return fail(code=-1, msg="未查询到转移日志记录")
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return fail(code=-1, msg="未识别路径有误")
                succ_flag, msg = _filetransfer.transfer_media(in_from=SyncType.MAN,
                                                              rmt_mode=rmt_mode,
                                                              in_path=path,
                                                              target_dir=dest_dir)
                if not succ_flag:
                    ret_flag = False
                    if msg not in ret_msg:
                        ret_msg.append(msg)
        if ret_flag:
            return success(msg="转移成功")
        else:
            return fail(code=2, msg="、".join(ret_msg))

