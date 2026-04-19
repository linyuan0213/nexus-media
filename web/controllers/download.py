from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
import json
import os.path
from flask_login import current_user
from app.downloader import Downloader
from app.filetransfer import FileTransfer
from app.indexer import Indexer
from app.media import Media
from app.searcher import Searcher
from app.services.download_service import DownloadService
from app.sites import Sites
from app.utils import SystemUtils, ExceptionUtils


download_bp = Blueprint("download", __name__, url_prefix="/api/web/download")


@download_bp.route('/auto_remove_torrents', methods=['POST'])
@any_auth
@parse_json_data
def _auto_remove_torrents(data):
    DownloadService().auto_remove_torrents(taskids=data.get("tid"))
    return success()


@download_bp.route('/check_downloader', methods=['POST'])
@any_auth
@parse_json_data
def _check_downloader(data):
    did = data.get("did")
    if not did:
        return fail()
    checked = data.get("checked")
    flag = data.get("flag")
    enabled = transfer = only_nastool = match_path = None
    if flag == "enabled":
        enabled = 1 if checked else 0
    elif flag == "transfer":
        transfer = 1 if checked else 0
    elif flag == "only_nastool":
        only_nastool = 1 if checked else 0
    elif flag == "match_path":
        match_path = 1 if checked else 0
    Downloader().check_downloader(did=did,
                                  enabled=enabled,
                                  transfer=transfer,
                                  only_nastool=only_nastool,
                                  match_path=match_path)
    return success()


@download_bp.route('/del_downloader', methods=['POST'])
@any_auth
@parse_json_data
def _del_downloader(data):
    did = data.get("did")
    Downloader().delete_downloader(did=did)
    return success()


@download_bp.route('/delete_download_setting', methods=['POST'])
@any_auth
@parse_json_data
def _delete_download_setting(data):
    sid = data.get("sid")
    Downloader().delete_download_setting(sid=sid)
    return success()


@download_bp.route('/delete_torrent_remove_task', methods=['POST'])
@any_auth
@parse_json_data
def _delete_torrent_remove_task(data):
    tid = data.get("tid")
    flag = DownloadService().delete_torrent_remove_task(taskid=tid)
    if flag:
        return success()
    return fail()


@download_bp.route('/download', methods=['POST'])
@any_auth
@parse_json_data
def _download(data):
    dl_id = data.get("id")
    dl_dir = data.get("dir")
    dl_setting = data.get("setting")
    result = DownloadService().download_from_search_results(
        dl_id=dl_id,
        dl_dir=dl_dir,
        dl_setting=dl_setting,
        user_name=current_user.username
    )
    if not result.success:
        return fail(code=-1, msg=result.message)
    return success(msg=result.message)


@download_bp.route('/download_link', methods=['POST'])
@any_auth
@parse_json_data
def _download_link(data):
    result = DownloadService().download_from_link(
        site=data.get("site"),
        enclosure=data.get("enclosure"),
        title=data.get("title"),
        description=data.get("description"),
        page_url=data.get("page_url"),
        size=data.get("size"),
        seeders=data.get("seeders"),
        uploadvolumefactor=data.get("uploadvolumefactor"),
        downloadvolumefactor=data.get("downloadvolumefactor"),
        dl_dir=data.get("dl_dir"),
        dl_setting=data.get("dl_setting"),
        user_name=current_user.username
    )
    if not result.success:
        return fail(msg=result.message)
    return success(msg=result.message)


@download_bp.route('/download_torrent', methods=['POST'])
@any_auth
@parse_json_data
def _download_torrent(data):
    result = DownloadService().download_from_torrent_files_or_urls(
        files=data.get("files") or [],
        urls=data.get("urls") or [],
        dl_dir=data.get("dl_dir"),
        dl_setting=data.get("dl_setting"),
        user_name=current_user.username
    )
    if not result.success:
        return fail(code=-1, msg=result.message)
    return success(msg=result.message)


@download_bp.route('/find_hardlinks', methods=['POST'])
@any_auth
@parse_json_data
def _find_hardlinks(data):
    files = data.get("files")
    file_dir = data.get("dir")
    if not files:
        return []
    if not file_dir and os.name != "nt":
        file_dir = os.path.commonpath(files).replace("\\", "/")
        if file_dir != "/":
            file_dir = "/" + str(file_dir).split("/")[1]
        else:
            return []
    hardlinks = {}
    if files:
        try:
            for file in files:
                hardlinks[os.path.basename(file)] = SystemUtils(
                ).find_hardlinks(file=file, fdir=file_dir)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail()
    return success(data=hardlinks)


@download_bp.route('/get_download_dirs', methods=['POST'])
@any_auth
@parse_json_data
def _get_download_dirs(data):
    sid = data.get("sid")
    site = data.get("site")
    if not sid and site:
        sid = Sites().get_site_download_setting(site_name=site)
    dirs = Downloader().get_download_dirs(setting=sid)
    return success(paths=dirs)


@download_bp.route('/get_download_setting', methods=['POST'])
@any_auth
@parse_json_data
def _get_download_setting(data):
    sid = data.get("sid")
    if sid:
        download_setting = Downloader().get_download_setting(sid=sid)
    else:
        download_setting = list(
            Downloader().get_download_setting().values())
    return success(data=download_setting)


@download_bp.route('/get_downloaders', methods=['POST'])
@any_auth
@parse_json_data
def _get_downloaders(data):
    did = data.get("did")
    return success(detail=Downloader().get_downloader_conf(did=did))


@download_bp.route('/get_indexer_statistics', methods=['POST'])
@any_auth
@parse_json_data
def _get_indexer_statistics(data):
    stats, dataset = DownloadService().get_indexer_statistics()
    return success(
        data=[{"name": s.name, "total": s.total, "fail": s.fail,
               "success": s.success, "avg": s.avg} for s in stats],
        dataset=dataset
    )


@download_bp.route('/get_indexers', methods=['POST'])
@any_auth
@parse_json_data
def _get_indexers(data):
    return success(indexers=Indexer().get_user_indexer_dict())


@download_bp.route('/get_remove_torrents', methods=['POST'])
@any_auth
@parse_json_data
def _get_remove_torrents(data):
    tid = data.get("tid")
    flag, torrents = DownloadService().get_remove_torrents(taskid=tid)
    if not flag or not torrents:
        return fail(msg="未获取到符合处理条件种子")
    return success(data=torrents)


@download_bp.route('/get_torrent_remove_task', methods=['POST'])
@any_auth
@parse_json_data
def _get_torrent_remove_task(data):
    tid = data.get("tid") if data else None
    return success(detail=DownloadService().get_torrent_remove_tasks(taskid=tid))


@download_bp.route('/pt_info', methods=['POST'])
@any_auth
@parse_json_data
def _pt_info(data):
    ids = data.get("ids")
    torrents = Downloader().get_downloading_progress(ids=ids)
    return success(torrents=torrents)


@download_bp.route('/pt_remove', methods=['POST'])
@any_auth
@parse_json_data
def _pt_remove(data):
    tid = data.get("id")
    if tid:
        Downloader().delete_torrents(ids=tid, delete_file=True)
    return success(id=tid)


@download_bp.route('/pt_start', methods=['POST'])
@any_auth
@parse_json_data
def _pt_start(data):
    tid = data.get("id")
    if tid:
        Downloader().start_torrents(ids=tid)
    return success(id=tid)


@download_bp.route('/pt_stop', methods=['POST'])
@any_auth
@parse_json_data
def _pt_stop(data):
    tid = data.get("id")
    if tid:
        Downloader().stop_torrents(ids=tid)
    return success(id=tid)


@download_bp.route('/test_downloader', methods=['POST'])
@any_auth
@parse_json_data
def _test_downloader(data):
    dtype = data.get("type")
    config = json.loads(data.get("config"))
    res = Downloader().get_status(dtype=dtype, config=config)
    if res:
        return success()
    return fail()


@download_bp.route('/update_download_setting', methods=['POST'])
@any_auth
@parse_json_data
def _update_download_setting(data):
    Downloader().update_download_setting(
        sid=data.get("sid"),
        name=data.get("name"),
        category=data.get("category"),
        tags=data.get("tags"),
        is_paused=data.get("is_paused"),
        upload_limit=data.get("upload_limit") or 0,
        download_limit=data.get("download_limit") or 0,
        ratio_limit=data.get("ratio_limit") or 0,
        seeding_time_limit=data.get("seeding_time_limit") or 0,
        downloader=data.get("downloader")
    )
    return success()


@download_bp.route('/update_downloader', methods=['POST'])
@any_auth
@parse_json_data
def _update_downloader(data):
    did = data.get("did")
    name = data.get("name")
    dtype = data.get("type")
    enabled = data.get("enabled")
    transfer = data.get("transfer")
    only_nastool = data.get("only_nastool")
    match_path = data.get("match_path")
    rmt_mode = data.get("rmt_mode")
    config = data.get("config")
    if not isinstance(config, str):
        config = json.dumps(config)
    download_dir = data.get("download_dir")
    if not isinstance(download_dir, str):
        download_dir = json.dumps(download_dir)
    Downloader().update_downloader(did=did,
                                   name=name,
                                   dtype=dtype,
                                   enabled=enabled,
                                   transfer=transfer,
                                   only_nastool=only_nastool,
                                   match_path=match_path,
                                   rmt_mode=rmt_mode,
                                   config=config,
                                   download_dir=download_dir)
    return success()


@download_bp.route('/update_torrent_remove_task', methods=['POST'])
@any_auth
@parse_json_data
def _update_torrent_remove_task(data):
    flag, msg = DownloadService().update_torrent_remove_task(data=data)
    if not flag:
        return fail(msg=msg)
    return success()


@download_bp.route('/get_downloading', methods=['POST'])
@any_auth
@parse_json_data
def get_downloading(data):
    torrents = DownloadService().get_downloading_with_media_info()
    return success(result=torrents)


@download_bp.route('/truncate_blacklist', methods=['POST'])
@any_auth
@parse_json_data
def truncate_blacklist(data):
    FileTransfer().truncate_transfer_blacklist()
    return success()
