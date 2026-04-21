from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from web.core.action_utils import set_config_directory, delete_media_file
import os.path
import shutil
import log
from app.conf import ModuleConf
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.helper import ThreadHelper
from app.services.sync_service import SyncService
from app.services.sync_core import SyncCore as Sync
from app.utils import ExceptionUtils
from app.utils.types import RmtMode, SyncType
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




@sync_bp.route('/get_sub_path', methods=['POST'])
@any_auth
@parse_json_data
def _get_sub_path(data):
    try:
        ft = data.get("filter") or "ALL"
        d = data.get("dir")
        r = SyncService().get_sub_path(directory=d, ft=ft)
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
    result = SyncService().rename_file(
        path=data.get("path"), name=data.get("name"))
    if result.success:
        return success()
    return fail(code=-1, msg=result.message)


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
    result = SyncService().test_connection(command=data.get("command"))
    if result.success:
        return success()
    return fail(code=1)


@sync_bp.route('/update_directory', methods=['POST'])
@any_auth
@parse_json_data
def _update_directory(data):
    result = SyncService().update_directory(
        oper=data.get("oper"),
        key=data.get("key"),
        value=data.get("value"),
        replace_value=data.get("replace_value")
    )
    if result.success:
        return success()
    return fail()


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
