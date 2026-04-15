from app.brushtask import BrushTask
from app.brushtask_rule import BrushRuleEngine
from app.utils import ExceptionUtils
from web.actions._base import WebActionBase


class WebActionBrushMixin:
    # 前端字段 -> 规则字段映射
    _RSS_RULE_FIELDS = {
        "free": "brushtask_free",
        "hr": "brushtask_hr",
        "size": "brushtask_torrent_size",
        "include": "brushtask_include",
        "exclude": "brushtask_exclude",
        "dlcount": "brushtask_dlcount",
        "peercount": "brushtask_peercount",
        "pubdate": "brushtask_pubdate",
        "upspeed": "brushtask_upspeed",
        "downspeed": "brushtask_downspeed",
        "exclude_subscribe": "brushtask_exclude_subscribe",
    }
    _REMOVE_RULE_FIELDS = {
        "mode": "brushtask_mode",
        "time": "brushtask_seedtime",
        "hr_time": "brushtask_hr_seedtime",
        "ratio": "brushtask_seedratio",
        "uploadsize": "brushtask_seedsize",
        "dltime": "brushtask_dltime",
        "avg_upspeed": "brushtask_avg_upspeed",
        "iatime": "brushtask_iatime",
        "pending_time": "brushtask_pending_time",
        "freespace": "brushtask_freespace",
        "freestatus": "brushtask_freestatus",
    }
    _STOP_RULE_FIELDS = {
        "stopfree": "brushtask_stopfree",
    }

    @staticmethod
    def _add_brushtask(data):
        """
        新增刷流任务
        """
        rss_rule = {k: data.get(v) for k, v in WebActionBrushMixin._RSS_RULE_FIELDS.items()}
        remove_rule = {k: data.get(v) for k, v in WebActionBrushMixin._REMOVE_RULE_FIELDS.items()}
        stop_rule = {k: ('Y' if data.get(v) else 'N') for k, v in WebActionBrushMixin._STOP_RULE_FIELDS.items()}

        brushtask_totalsize = data.get("brushtask_totalsize")
        try:
            seed_size_bytes = int(float(brushtask_totalsize) * 1024 ** 3) if brushtask_totalsize else 0
        except (ValueError, TypeError):
            seed_size_bytes = 0

        item = {
            "name": data.get("brushtask_name"),
            "site": data.get("brushtask_site"),
            "free": data.get("brushtask_free"),
            "rssurl": data.get("brushtask_rssurl"),
            "interval": data.get("brushtask_interval"),
            "downloader": data.get("brushtask_downloader"),
            "seed_size": seed_size_bytes,
            "time_range": data.get("brushtask_time_range"),
            "label": data.get("brushtask_label"),
            "savepath": data.get("brushtask_savepath"),
            "transfer": 'Y' if data.get("brushtask_transfer") else 'N',
            "state": data.get("brushtask_state"),
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "stop_rule": stop_rule,
            "sendmessage": 'Y' if data.get("brushtask_sendmessage") else 'N',
        }
        BrushTask().update_brushtask(data.get("brushtask_id"), item)
        return WebActionBase._success()

    @staticmethod
    def _del_brushtask(data):
        """
        删除刷流任务
        """
        brush_id = data.get("id")
        if brush_id:
            BrushTask().delete_brushtask(brush_id)
            return WebActionBase._success()
        return WebActionBase._fail()

    @staticmethod
    def _brushtask_detail(data):
        """
        查询刷流任务详情
        """
        brush_id = data.get("id")
        brushtask = BrushTask().get_brushtask_info(brush_id)
        if not brushtask:
            return WebActionBase._fail(task={})

        return WebActionBase._success(task=brushtask)

    @staticmethod
    def _update_brushtask_state(data):
        """
        批量暂停/开始刷流任务
        """
        try:
            state = data.get("state")
            task_ids = data.get("ids")
            _brushtask = BrushTask()
            if state is not None:
                if task_ids:
                    for tid in task_ids:
                        _brushtask.update_brushtask_state(
                            state=state, brushtask_id=tid)
                else:
                    _brushtask.update_brushtask_state(state=state)
            return WebActionBase._success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return WebActionBase._fail(msg="刷流任务设置失败")

    @staticmethod
    def parse_brush_rule_string(rules: dict):
        return BrushRuleEngine.format_rule_html(rules)

    @staticmethod
    def _run_brushtask(data):
        BrushTask().check_task_rss(data.get("id"))
        return WebActionBase._success()

    @staticmethod
    def _list_brushtask_torrents(data):
        """
        获取刷流任务的种子明细
        """
        results = BrushTask().get_brushtask_torrents(brush_id=data.get("id"),
                                                     active=False)
        if not results:
            return WebActionBase._fail(msg="未下载种子或未获取到种子明细")
        return WebActionBase._success(data=[item.as_dict() for item in results])
