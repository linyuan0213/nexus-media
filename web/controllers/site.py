from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail

from app.services.site_service import SiteService

site_bp = Blueprint("site", __name__, url_prefix="/api/web/site")


@site_bp.route('/check_site_attr', methods=['POST'])
@any_auth
@parse_json_data
def _check_site_attr(data):
    """
    检查站点标识
    """
    dto = SiteService().check_site_attr(data.get("url"))
    return success(
        site_free=dto.site_free,
        site_2xfree=dto.site_2xfree,
        site_hr=dto.site_hr
    )


@site_bp.route('/del_site', methods=['POST'])
@any_auth
@parse_json_data
def _del_site(data):
    """
    删除单个站点信息
    """
    tid = data.get("id")
    if tid:
        ret = SiteService().delete_site(tid)
        return fail(code=ret or 0)
    return success()


@site_bp.route('/get_site', methods=['POST'])
@any_auth
@parse_json_data
def _get_site(data):
    """
    查询单个站点信息
    """
    dto = SiteService().get_site(data.get("id"))
    return success(
        site=dto.site,
        site_free=dto.site_free,
        site_2xfree=dto.site_2xfree,
        site_hr=dto.site_hr
    )


@site_bp.route('/get_site_activity', methods=['POST'])
@any_auth
@parse_json_data
def _get_site_activity(data):
    """
    查询site活动[上传，下载，魔力值]
    """
    if not data or "name" not in data:
        return fail(msg="查询参数错误")
    dto = SiteService().get_site_activity(data["name"])
    return {"code": 0, "dataset": dto.dataset}


@site_bp.route('/get_site_favicon', methods=['POST'])
@any_auth
@parse_json_data
def _get_site_favicon(data):
    """
    获取站点图标
    """
    return success(icon=SiteService().get_site_favicon(data.get("name")))


@site_bp.route('/get_site_history', methods=['POST'])
@any_auth
@parse_json_data
def _get_site_history(data):
    """
    查询site 历史[上传，下载]
    """
    if not data or "days" not in data or not isinstance(data["days"], int):
        return fail(msg="查询参数错误")
    dto = SiteService().get_site_history(
        days=data["days"],
        end_day=data.get("end_day")
    )
    return {"code": 0, "dataset": dto.dataset}


@site_bp.route('/get_site_seeding_info', methods=['POST'])
@any_auth
@parse_json_data
def _get_site_seeding_info(data):
    """
    查询site 做种分布信息 大小，做种数
    """
    if not data or "name" not in data:
        return fail(msg="查询参数错误")
    dto = SiteService().get_site_seeding_info(data["name"])
    return {"code": 0, "dataset": dto.dataset}


@site_bp.route('/get_sites', methods=['POST'])
@any_auth
@parse_json_data
def _get_sites(data):
    """
    查询多个站点信息
    """
    sites = SiteService().get_sites(
        rss=bool(data.get("rss")),
        brush=bool(data.get("brush")),
        statistic=bool(data.get("statistic")),
        basic=bool(data.get("basic"))
    )
    return success(sites=sites)


@site_bp.route('/set_site_captcha_code', methods=['POST'])
@any_auth
@parse_json_data
def _set_site_captcha_code(data):
    """
    设置站点验证码
    """
    SiteService().set_captcha_code(
        code=data.get("code"), value=data.get("value"))
    return success()


@site_bp.route('/test_site', methods=['POST'])
@any_auth
@parse_json_data
def _test_site(data):
    """
    测试站点连通性
    """
    dto = SiteService().test_site(data.get("id"))
    return fail(code=dto.code, msg=dto.msg, time=dto.times)


@site_bp.route('/update_site', methods=['POST'])
@any_auth
@parse_json_data
def _update_site(data):
    """
    维护站点信息
    """
    dto = SiteService().update_site(data)
    return fail(code=dto.code or 0, msg=dto.msg or "")


@site_bp.route('/update_site_cookie_ua', methods=['POST'])
@any_auth
@parse_json_data
def _update_site_cookie_ua(data):
    """
    更新单个站点的Cookie和UA
    """
    SiteService().update_site_cookie_ua(
        siteid=data.get("site_id"),
        cookie=data.get("site_cookie"),
        ua=data.get("site_ua")
    )
    return success(messages="请求发送成功")


@site_bp.route('/get_site_user_statistics', methods=['POST'])
@any_auth
@parse_json_data
def get_site_user_statistics(data):
    """
    获取站点用户统计信息
    """
    statistics = SiteService().get_site_user_statistics(
        sites=data.get("sites"),
        encoding=data.get("encoding") or "RAW",
        sort_by=data.get("sort_by"),
        sort_on=data.get("sort_on"),
        site_hash=data.get("site_hash")
    )
    return success(data=statistics)


@site_bp.route('/list_site_resources', methods=['POST'])
@any_auth
@parse_json_data
def list_site_resources(data):
    resources = SiteService().list_site_resources(
        index_id=data.get("id"),
        page=data.get("page"),
        keyword=data.get("keyword")
    )
    if not resources.success:
        return fail(msg=resources.msg)
    return success(data=resources.data)
