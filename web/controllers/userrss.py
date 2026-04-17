from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from web.core.action_utils import mediainfo_dict
from app.services.rss_service import RssTaskService as RssChecker
from app.utils import ExceptionUtils

userrss_bp = Blueprint("userrss", __name__, url_prefix="/api/web/userrss")

@userrss_bp.route('/check_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _check_userrss_task(data):
        """
        检测自定义订阅
        """
        try:
            flag_dict = {"enable": True, "disable": False}
            taskids = data.get("ids")
            state = flag_dict.get(data.get("flag"))
            _rsschecker = RssChecker()
            if state is not None:
                if taskids:
                    for taskid in taskids:
                        _rsschecker.check_userrss_task(tid=taskid, state=state)
                else:
                    _rsschecker.check_userrss_task(state=state)
            return success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg="自定义订阅状态设置失败")

@userrss_bp.route('/delete_rssparser', methods=['POST'])
@any_auth
@parse_json_data
def _delete_rssparser(data):
        """
        删除订阅解析器
        """
        if RssChecker().delete_userrss_parser(data.get("id")):
            return success()
        else:
            return fail()

@userrss_bp.route('/delete_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _delete_userrss_task(data):
        """
        删除自定义订阅
        """
        if RssChecker().delete_userrss_task(data.get("id")):
            return success()
        else:
            return fail()


@userrss_bp.route('/list_rss_parsers', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_parsers(data):
        """
        查询所有解析器
        """
        return success(parsers=RssChecker().get_userrss_parser())


@userrss_bp.route('/get_rssparser', methods=['POST'])
@any_auth
@parse_json_data
def _get_rssparser(data):
        """
        获取订阅解析器详情
        """
        pid = data.get("id")
        return success(detail=RssChecker().get_userrss_parser(pid=pid))

@userrss_bp.route('/get_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _get_userrss_task(data):
        """
        获取自定义订阅详情
        """
        taskid = data.get("id")
        return success(detail=RssChecker().get_rsstask_info(taskid=taskid))


@userrss_bp.route('/list_rss_tasks', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_tasks(data):
        """
        查询所有自定义订阅任务
        """
        return success(
            tasks=RssChecker().get_rsstask_info(),
            parsers=RssChecker().get_userrss_parser()
        )

@userrss_bp.route('/list_rss_articles', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_articles(data):
        task_info = RssChecker().get_rsstask_info(taskid=data.get("id"))
        uses = task_info.get("uses")
        address_count = len(task_info.get("address"))
        articles = RssChecker().get_rss_articles(data.get("id"))
        count = len(articles)
        if articles:
            return success(data=articles, count=count, uses=uses, address_count=address_count)
        else:
            return fail(msg="未获取到报文")

@userrss_bp.route('/list_rss_history', methods=['POST'])
@any_auth
@parse_json_data
def _list_rss_history(data):
        downloads = []
        historys = RssChecker().get_userrss_task_history(data.get("id"))
        count = len(historys)
        for history in historys:
            params = {
                "title": history.TITLE,
                "downloader": history.DOWNLOADER,
                "date": history.DATE
            }
            downloads.append(params)
        if downloads:
            return success(data=downloads, count=count)
        else:
            return fail(msg="无下载记录")

@userrss_bp.route('/rss_article_test', methods=['POST'])
@any_auth
@parse_json_data
def _rss_article_test(data):
        taskid = data.get("taskid")
        title = data.get("title")
        if not taskid:
            return fail(code=-1)
        if not title:
            return fail(code=-1)
        media_info, match_flag, exist_flag = RssChecker(
        ).test_rss_articles(taskid=taskid, title=title)
        if not media_info:
            return success(data={"name": "无法识别"})
        media_dict = mediainfo_dict(media_info)
        media_dict.update({"match_flag": match_flag, "exist_flag": exist_flag})
        return success(data=media_dict)

@userrss_bp.route('/rss_articles_check', methods=['POST'])
@any_auth
@parse_json_data
def _rss_articles_check(data):
        if not data.get("articles"):
            return fail(code=2)
        res = RssChecker().check_rss_articles(
            taskid=data.get("taskid"),
            flag=data.get("flag"),
            articles=data.get("articles")
        )
        if res:
            return success()
        else:
            return fail()

@userrss_bp.route('/rss_articles_download', methods=['POST'])
@any_auth
@parse_json_data
def _rss_articles_download(data):
        if not data.get("articles"):
            return fail(code=2)
        res = RssChecker().download_rss_articles(
            taskid=data.get("taskid"), articles=data.get("articles"))
        if res:
            return success()
        else:
            return fail()

@userrss_bp.route('/run_userrss', methods=['POST'])
@any_auth
@parse_json_data
def _run_userrss(data):
        RssChecker().check_task_rss(data.get("id"))
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
        if RssChecker().update_userrss_parser(params):
            return success()
        else:
            return fail()

@userrss_bp.route('/update_userrss_task', methods=['POST'])
@any_auth
@parse_json_data
def _update_userrss_task(data):
        """
        新增或修改自定义订阅
        """
        uses = data.get("uses")
        address_parser = data.get("address_parser")
        if not address_parser:
            return fail()
        address = list(dict(sorted(
            {k.replace("address_", ""): y for k, y in address_parser.items(
            ) if k.startswith("address_")}.items(),
            key=lambda x: int(x[0])
        )).values())
        parser = list(dict(sorted(
            {k.replace("parser_", ""): y for k, y in address_parser.items(
            ) if k.startswith("parser_")}.items(),
            key=lambda x: int(x[0])
        )).values())
        params = {
            "id": data.get("id"),
            "name": data.get("name"),
            "address": address,
            "parser": parser,
            "interval": data.get("interval"),
            "uses": uses,
            "include": data.get("include"),
            "exclude": data.get("exclude"),
            "filter_rule": data.get("rule"),
            "state": data.get("state"),
            "save_path": data.get("save_path"),
            "download_setting": data.get("download_setting"),
            "note": {"proxy": data.get("proxy")},
        }
        if uses == "D":
            params.update({
                "recognization": data.get("recognization")
            })
        elif uses == "R":
            params.update({
                "over_edition": data.get("over_edition"),
                "sites": data.get("sites"),
                "filter_args": {
                    "restype": data.get("restype"),
                    "pix": data.get("pix"),
                    "team": data.get("team")
                }
            })
        else:
            return fail()
        if RssChecker().update_userrss_task(params):
            return success()
        else:
            return fail()

