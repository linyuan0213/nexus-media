from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.media.meta import MetaInfo
from app.rss import Rss
from app.services.rss_service import RssTaskService as RssChecker
from app.services.rss_service import RssSubscriptionService
from app.subscribe import Subscribe
from app.utils.types import MediaType, MovieTypes, RssType

rss_bp = Blueprint("rss", __name__, url_prefix="/api/web/rss")


@rss_bp.route('/add_rss_media', methods=['POST'])
@any_auth
@parse_json_data
def _add_rss_media(data):
    """
    添加RSS订阅
    """
    result = RssSubscriptionService().add_rss_media(data)
    return fail(code=result.code, msg=result.msg,
                page=data.get("page"), name=data.get("name"),
                rssid=result.rssid)


@rss_bp.route('/delete_rss_history', methods=['POST'])
@any_auth
@parse_json_data
def _delete_rss_history(data):
    RssSubscriptionService().delete_rss_history(rssid=data.get("rssid"))
    return success()


@rss_bp.route('/re_rss_history', methods=['POST'])
@any_auth
@parse_json_data
def _re_rss_history(data):
    code, msg = RssSubscriptionService().re_rss_history(
        rssid=data.get("rssid"), rtype=data.get("type"))
    if code != 0:
        return fail(code=code, msg=msg)
    return fail(code=code, msg=msg)


@rss_bp.route('/refresh_rss', methods=['POST'])
@any_auth
@parse_json_data
def _refresh_rss(data):
    """
    重新搜索RSS
    """
    RssSubscriptionService().refresh_rss(
        mtype=data.get("type"), rssid=data.get("rssid"))
    return success(page=data.get("page"))


@rss_bp.route('/remove_rss_media', methods=['POST'])
@any_auth
@parse_json_data
def _remove_rss_media(data):
    """
    移除RSS订阅
    """
    RssSubscriptionService().remove_rss_media(
        name=data.get("name"),
        mtype=data.get("type"),
        year=data.get("year"),
        season=data.get("season"),
        rssid=data.get("rssid"),
        tmdbid=data.get("tmdbid"))
    return success(page=data.get("page"), name=data.get("name"))


@rss_bp.route('/rss_detail', methods=['POST'])
@any_auth
@parse_json_data
def _rss_detail(data):
    result = RssSubscriptionService().get_rss_detail(
        rid=data.get("rssid"), rsstype=data.get("rsstype"))
    if not result:
        return fail()
    return success(detail=result.detail)


@rss_bp.route('/get_default_rss_setting', methods=['POST'])
@any_auth
@parse_json_data
def get_default_rss_setting(data):
    """
    获取默认订阅设置
    """
    setting = RssSubscriptionService().get_default_rss_setting(
        mtype=data.get("mtype"))
    if setting:
        return success(data=setting)
    return fail()


@rss_bp.route('/get_ical_events', methods=['POST'])
@any_auth
@parse_json_data
def get_ical_events(data):
    """
    获取ical日历事件
    """
    events = RssSubscriptionService().get_ical_events()
    return success(result=events)


@rss_bp.route('/get_movie_rss_items', methods=['POST'])
@any_auth
@parse_json_data
def get_movie_rss_items(data):
    """
    获取所有电影订阅项目
    """
    return success(result=RssSubscriptionService().get_movie_rss_items())


@rss_bp.route('/get_movie_rss_list', methods=['POST'])
@any_auth
@parse_json_data
def get_movie_rss_list(data):
    """
    查询所有电影订阅
    """
    return success(result=RssSubscriptionService().get_movie_rss_list())


@rss_bp.route('/get_rss_history', methods=['POST'])
@any_auth
@parse_json_data
def get_rss_history(data):
    """
    查询所有订阅历史
    """
    return success(result=RssSubscriptionService().get_rss_history(
        mtype=data.get("type")))


@rss_bp.route('/get_tv_rss_items', methods=['POST'])
@any_auth
@parse_json_data
def get_tv_rss_items(data):
    """
    获取所有电视剧订阅项目
    """
    return success(result=RssSubscriptionService().get_tv_rss_items())


@rss_bp.route('/get_tv_rss_list', methods=['POST'])
@any_auth
@parse_json_data
def get_tv_rss_list(data):
    """
    查询所有电视剧订阅
    """
    return success(result=RssSubscriptionService().get_tv_rss_list())


@rss_bp.route('/truncate_rsshistory', methods=['POST'])
@any_auth
@parse_json_data
def truncate_rsshistory(data):
    """
    清空RSS历史记录
    """
    RssSubscriptionService().truncate_rss_history()
    return success()
