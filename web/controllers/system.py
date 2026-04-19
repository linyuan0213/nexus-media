from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from web.core.action_utils import restart_server
import json
from flask_login import logout_user
from werkzeug.security import generate_password_hash

from app.helper import tmdb_blacklist_helper
from app.helper.tmdb_blacklist_helper import TmdbBlacklistHelper
from app.conf import SystemConfig
from app.downloader import Downloader
from app.db.repositories import ConfigRepository
from app.helper import ProgressHelper
from app.mediaserver import MediaServer
from app.message import Message
from app.rss import Rss
from app.subscribe import Subscribe
from app.sync import Sync
from app.utils import ExceptionUtils
from app.utils.types import MediaType, MovieTypes
from config import Config
from web.backend.search_torrents import search_medias_for_web
from web.backend.user import User
from web.backend.web_utils import WebUtils
from web.cache import cache
from app.services.system_service import (
    MessageClientService,
    BackupRestoreService,
    IndexerConfigService,
    MediaServerConfigService,
    NetTestService,
    SchedulerService,
    WebSearchService,
    SystemConfigService,
    VersionService,
)

system_bp = Blueprint("system", __name__, url_prefix="/api/web/system")


@system_bp.route('/add_tmdb_blacklist', methods=['POST'])
@any_auth
@parse_json_data
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
    return success()


@system_bp.route('/check_message_client', methods=['POST'])
@any_auth
@parse_json_data
def _check_message_client(data):
    """
    维护消息设置
    """
    flag = data.get("flag")
    cid = data.get("cid")
    ctype = data.get("type")
    checked = data.get("checked")
    svc = MessageClientService()
    if flag == "interactive":
        svc.toggle_interactive(cid=cid, ctype=ctype, checked=checked)
        return success()
    elif flag == "enable":
        svc.toggle_enable(cid=cid, checked=checked)
        return success()
    else:
        return fail()


@system_bp.route('/clear_tmdb_blacklist', methods=['POST'])
@any_auth
@parse_json_data
def _clear_tmdb_blacklist(data):
    tmdb_blacklist_helper = TmdbBlacklistHelper()
    if tmdb_blacklist_helper.get_blacklist():
        tmdb_blacklist_helper.clear_blacklist()
    return success()


@system_bp.route('/delete_message_client', methods=['POST'])
@any_auth
@parse_json_data
def _delete_message_client(data):
    """
    删除消息设置
    """
    if MessageClientService().delete_client(cid=data.get("cid")):
        return success()
    else:
        return fail()


@system_bp.route('/delete_tmdb_blacklist', methods=['POST'])
@any_auth
@parse_json_data
def _delete_tmdb_blacklist(data):
    tmdb_blacklist_helper = TmdbBlacklistHelper()
    tmdb_id = data.get("tmdb_id")
    media_type = data.get("media_type")
    if tmdb_blacklist_helper.is_blacklisted(tmdb_id, media_type):
        tmdb_blacklist_helper.remove_from_blacklist(
            tmdb_id=tmdb_id, media_type=media_type)
    return success()


@system_bp.route('/get_message_client', methods=['POST'])
@any_auth
@parse_json_data
def _get_message_client(data):
    """
    获取消息设置
    """
    cid = data.get("cid")
    return success(detail=MessageClientService().get_client(cid=cid))


@system_bp.route('/logout', methods=['POST'])
@any_auth
@parse_json_data
def _logout(data):
    """
    注销
    """
    logout_user()
    return success()


@system_bp.route('/net_test', methods=['POST'])
@any_auth
@parse_json_data
def _net_test(data):
    result = NetTestService().test(target=data)
    return {"res": result.success, "time": "%s 毫秒" % result.time_ms}


@system_bp.route('/reset_db_version', methods=['POST'])
@any_auth
@parse_json_data
def _reset_db_version(data):
    """
    重置数据库版本
    """
    try:
        ConfigRepository().drop_table("alembic_version")
        return success()
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@system_bp.route('/restart', methods=['POST'])
@any_auth
@parse_json_data
def _restart(data):
    """
    重启
    """
    restart_server()
    return success()


@system_bp.route('/restory_backup', methods=['POST'])
@any_auth
@parse_json_data
def _restory_backup(data):
    """
    解压恢复备份文件，并支持跨数据库类型恢复
    """
    filename = data.get("file_name")
    result = BackupRestoreService().restore_from_backup(filename)
    if result.success:
        return success(msg=result.message)
    return fail(msg=result.message)


@system_bp.route('/save_indexer_config', methods=['POST'])
@any_auth
@parse_json_data
def _save_indexer_config(data):
    """
    保存索引器配置到数据库
    """
    result = IndexerConfigService().save_config(data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@system_bp.route('/save_mediaserver_config', methods=['POST'])
@any_auth
@parse_json_data
def _save_mediaserver_config(data):
    """
    保存媒体服务器配置到数据库
    """
    result = MediaServerConfigService().save_config(data)
    if result.success and result.code == 0:
        return success()
    return fail(code=result.code, msg=result.msg)


@system_bp.route('/sch', methods=['POST'])
@any_auth
@parse_json_data
def _sch(data):
    """
    启动服务
    """
    ok, msg = SchedulerService().start_service(item=data.get("item"))
    if ok:
        return success(msg=msg, item=data.get("item"))
    return success(msg=msg, item=data.get("item"))


@system_bp.route('/search', methods=['POST'])
@any_auth
@parse_json_data
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
            return fail(code=ret, msg=ret_msg)
    return success()


@system_bp.route('/set_system_config', methods=['POST'])
@any_auth
@parse_json_data
def _set_system_config(data):
    """
    设置系统设置（数据库）
    """
    key = data.get("key")
    value = data.get("value")
    if SystemConfigService().set_config(key, value):
        return success()
    return fail()


@system_bp.route('/test_message_client', methods=['POST'])
@any_auth
@parse_json_data
def _test_message_client(data):
    """
    测试消息设置
    """
    ctype = data.get("type")
    config = json.loads(data.get("config"))
    if MessageClientService().test_connection(ctype=ctype, config=config):
        return success()
    else:
        return fail()


@system_bp.route('/update_all_config', methods=['POST'])
@any_auth
@parse_json_data
def _update_all_config(data):
    """
    设置系统设置（数据库）
    """
    conf = data.get("conf")
    db = data.get("db")
    if data.get('test'):
        conf = data
    if conf:
        ret = _update_config(conf)
        if ret.get('code') == 1:
            return ret
    if db:
        ret = _set_system_config(db)
        if ret.get('code') == 1:
            return ret

    return success()


@system_bp.route('/update_config', methods=['POST'])
@any_auth
@parse_json_data
def _update_config(data):
    """
    更新配置信息
    """
    cfg = Config().get_config()
    cfgs = dict(data).items()
    config_test = False
    for key, value in cfgs:
        if key == "test" and value:
            config_test = True
            continue
        from web.core.action_utils import set_config_value
        cfg = set_config_value(cfg, key, value)

    if not config_test:
        cfg.pop("test", None)
        Config().save_config(cfg)

    return success()


@system_bp.route('/update_message_client', methods=['POST'])
@any_auth
@parse_json_data
def _update_message_client(data):
    """
    更新消息设置
    """
    MessageClientService().upsert_client(
        name=data.get("name"),
        cid=data.get("cid"),
        ctype=data.get("type"),
        config=data.get("config"),
        switchs=data.get("switchs"),
        interactive=data.get("interactive"),
        enabled=data.get("enabled"),
        templates=data.get("templates"),
    )
    return success()


@system_bp.route('/user_manager', methods=['POST'])
@any_auth
@parse_json_data
def _user_manager(data):
    """
    用户管理
    """
    from app.services.rbac_service import rbac_service
    oper = data.get("oper")
    name = data.get("name")
    if oper == "add":
        password = generate_password_hash(str(data.get("password")))
        pris = data.get("pris")
        if isinstance(pris, list):
            pris = ",".join(pris)
        ok, _ = rbac_service.create_user(username=name, password=password)
        ret = ok
    else:
        user = rbac_service.get_user_by_username(name)
        if user:
            ok, _ = rbac_service.delete_user(user.ID)  # type: ignore[arg-type]
            ret = ok
        else:
            ret = False

    if ret == 1 or ret:
        return success(success=False)
    return fail(code=-1, success=False, message='操作失败')


@system_bp.route('/version', methods=['POST'])
@any_auth
@parse_json_data
def _version(data):
    """
    检查新版本
    """
    info = VersionService().get_latest_version()
    if info.has_update:
        return success(version=info.version, url=info.url)
    return fail(code=-1, version="", url="")


@system_bp.route('/refresh_process', methods=['POST'])
@any_auth
@parse_json_data
def refresh_process(data):
    """
    刷新进度条
    """
    detail = ProgressHelper().get_process(data.get("type"))
    if detail:
        return success(value=detail.get("value"), text=detail.get("text"))
    else:
        return fail(value=0, text="正在处理...")


@system_bp.route('/send_custom_message', methods=['POST'])
@any_auth
@parse_json_data
def send_custom_message(data):
    """
    发送自定义消息
    """
    title = data.get("title")
    text = data.get("text") or ""
    image = data.get("image") or ""
    message_clients = data.get("message_clients")
    if not message_clients:
        return fail(msg="未选择消息服务")
    Message().send_custom_message(clients=message_clients,
                                  title=title, text=text, image=image)
    return success()


@system_bp.route('/send_plugin_message', methods=['POST'])
@any_auth
@parse_json_data
def send_plugin_message(data):
    """
    发送插件消息
    """
    title = data.get("title")
    text = data.get("text") or ""
    image = data.get("image") or ""
    Message().send_plugin_message(title=title, text=text, image=image)
    return success()


@system_bp.route('/update_system', methods=['POST'])
@any_auth
@parse_json_data
def update_system(data):
    """
    更新
    """
    restart_server()
    return success()


@system_bp.route('/processes', methods=['POST'])
@any_auth
@parse_json_data
def _processes(data):
    """
    获取系统进程列表
    """
    from app.utils.system_utils import SystemUtils
    return success(data=SystemUtils.get_all_processes())
