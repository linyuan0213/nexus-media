from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.services.userrss_service import UserRssService

userrss_bp = Blueprint("userrss", __name__, url_prefix="/api/web/userrss")


@userrss_bp.route('/check_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _check_userrss_task(data):
    """
    检测自定义订阅
    """
    try:
        UserRssService().check_tasks(
            taskids=data.get("ids"),
            flag=data.get("flag")
        )
        return success(msg="")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return fail(msg="自定义订阅状态设置失败")


@userrss_bp.route('/delete_rssparser', methods=['POST'])
@any_auth
@parse_json_data
def _delete_rssparser(data):
    """
    删除订阅解析器
    """
    if UserRssService().delete_parser(data.get("id")):
        return success()
    return fail()


@userrss_bp.route('/delete_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _delete_userrss_task(data):
    """
    删除自定义订阅
    """
    if UserRssService().delete_task(data.get("id")):
        return success()
    return fail()


@userrss_bp.route('/list_rss_parsers', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_parsers(data):
    """
    查询所有解析器
    """
    return success(parsers=UserRssService().get_parsers())


@userrss_bp.route('/get_rssparser', methods=['POST'])
@any_auth
@parse_json_data
def _get_rssparser(data):
    """
    获取订阅解析器详情
    """
    return success(detail=UserRssService().get_parser(data.get("id")))


@userrss_bp.route('/get_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _get_userrss_task(data):
    """
    获取自定义订阅详情
    """
    return success(detail=UserRssService().get_task(data.get("id")))


@userrss_bp.route('/list_rss_tasks', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_tasks(data):
    """
    查询所有自定义订阅任务
    """
    svc = UserRssService()
    return success(tasks=svc.get_tasks(), parsers=svc.get_parsers())


@userrss_bp.route('/list_rss_articles', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_articles(data):
    dto = UserRssService().get_articles(data.get("id"))
    if dto.articles:
        return success(
            data=dto.articles,
            count=dto.count,
            uses=dto.uses,
            address_count=dto.address_count
        )
    return fail(msg="未获取到报文")


@userrss_bp.route('/list_rss_history', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_history(data):
    dto = UserRssService().get_history(data.get("id"))
    if dto.downloads:
        return success(data=dto.downloads, count=dto.count)
    return fail(msg="无下载记录")


@userrss_bp.route('/rss_article_test', methods=['POST'])
@any_auth
@parse_json_data
def _rss_article_test(data):
    taskid = data.get("taskid")
    title = data.get("title")
    if not taskid or not title:
        return fail(code=-1)
    dto = UserRssService().test_article(taskid, title)
    if dto.name == "无法识别":
        return success(data={"name": "无法识别"})
    return success(data=dto.media_dict)


@userrss_bp.route('/rss_articles_check', methods=['POST'])
@any_auth
@parse_json_data
def _rss_articles_check(data):
    if not data.get("articles"):
        return fail(code=2)
    res = UserRssService().check_articles(
        taskid=data.get("taskid"),
        flag=data.get("flag"),
        articles=data.get("articles")
    )
    return success() if res else fail()


@userrss_bp.route('/rss_articles_download', methods=['POST'])
@any_auth
@parse_json_data
def _rss_articles_download(data):
    if not data.get("articles"):
        return fail(code=2)
    res = UserRssService().download_articles(
        taskid=data.get("taskid"),
        articles=data.get("articles")
    )
    return success() if res else fail()


@userrss_bp.route('/run_userrss', methods=['POST'])
@any_auth
@parse_json_data
def _run_userrss(data):
    UserRssService().run_task(data.get("id"))
    return success()


@userrss_bp.route('/update_rssparser', methods=['POST'])
@any_auth
@parse_json_data
def _update_rssparser(data):
    """
    新增或更新订阅解析器
    """
    params = {
        "id": data.get("id"),
        "name": data.get("name"),
        "type": data.get("type"),
        "format": data.get("format"),
        "params": data.get("params")
    }
    if UserRssService().update_parser(params):
        return success()
    return fail()


@userrss_bp.route('/update_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _update_userrss_task(data):
    """
    新增或修改自定义订阅
    """
    dto = UserRssService().update_task(data)
    return success() if dto.success else fail()
