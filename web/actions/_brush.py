

from app.brushtask import BrushTask
from app.utils import StringUtils, ExceptionUtils
from web.actions._base import WebActionBase


class WebActionBrushMixin:
    @staticmethod
    def _add_brushtask(data):
        """
        新增刷流任务
        """
        # 输入值
        brushtask_id = data.get("brushtask_id")
        brushtask_name = data.get("brushtask_name")
        brushtask_site = data.get("brushtask_site")
        brushtask_interval = data.get("brushtask_interval")
        brushtask_downloader = data.get("brushtask_downloader")
        brushtask_totalsize = data.get("brushtask_totalsize")
        brushtask_time_range = data.get("brushtask_time_range")
        brushtask_state = data.get("brushtask_state")
        brushtask_rssurl = data.get("brushtask_rssurl")
        brushtask_label = data.get("brushtask_label")
        brushtask_savepath = data.get("brushtask_savepath")
        brushtask_transfer = 'Y' if data.get("brushtask_transfer") else 'N'
        brushtask_sendmessage = 'Y' if data.get(
            "brushtask_sendmessage") else 'N'
        brushtask_free = data.get("brushtask_free")
        brushtask_hr = data.get("brushtask_hr")
        brushtask_torrent_size = data.get("brushtask_torrent_size")
        brushtask_include = data.get("brushtask_include")
        brushtask_exclude = data.get("brushtask_exclude")
        brushtask_dlcount = data.get("brushtask_dlcount")
        brushtask_peercount = data.get("brushtask_peercount")
        brushtask_seedtime = data.get("brushtask_seedtime")
        brushtask_hr_seedtime = data.get("brushtask_hr_seedtime")
        brushtask_seedratio = data.get("brushtask_seedratio")
        brushtask_seedsize = data.get("brushtask_seedsize")
        brushtask_dltime = data.get("brushtask_dltime")
        brushtask_avg_upspeed = data.get("brushtask_avg_upspeed")
        brushtask_iatime = data.get("brushtask_iatime")
        brushtask_pubdate = data.get("brushtask_pubdate")
        brushtask_upspeed = data.get("brushtask_upspeed")
        brushtask_downspeed = data.get("brushtask_downspeed")
        brushtask_pending_time = data.get("brushtask_pending_time")
        brushtask_stopfree = 'Y' if data.get("brushtask_stopfree") else 'N'
        brushtask_freespace = data.get("brushtask_freespace")
        brushtask_mode = data.get("brushtask_mode")
        brushtask_exclude_subscribe = 'Y' if data.get(
            "brushtask_exclude_subscribe") else 'N'
        brushtask_freestatus = 'Y' if data.get("brushtask_freestatus") else 'N'
        # 选种规则
        rss_rule = {
            "free": brushtask_free,
            "hr": brushtask_hr,
            "size": brushtask_torrent_size,
            "include": brushtask_include,
            "exclude": brushtask_exclude,
            "dlcount": brushtask_dlcount,
            "peercount": brushtask_peercount,
            "pubdate": brushtask_pubdate,
            "upspeed": brushtask_upspeed,
            "downspeed": brushtask_downspeed,
            "exclude_subscribe": brushtask_exclude_subscribe
        }
        # 删除规则
        remove_rule = {
            "mode": brushtask_mode,
            "time": brushtask_seedtime,
            "hr_time": brushtask_hr_seedtime,
            "ratio": brushtask_seedratio,
            "uploadsize": brushtask_seedsize,
            "dltime": brushtask_dltime,
            "avg_upspeed": brushtask_avg_upspeed,
            "iatime": brushtask_iatime,
            "pending_time": brushtask_pending_time,
            "freespace": brushtask_freespace,
            "freestatus": brushtask_freestatus
        }
        # 停种规则
        stop_rule = {
            "stopfree": brushtask_stopfree
        }
        # 添加记录
        item = {
            "name": brushtask_name,
            "site": brushtask_site,
            "free": brushtask_free,
            "rssurl": brushtask_rssurl,
            "interval": brushtask_interval,
            "downloader": brushtask_downloader,
            "seed_size": brushtask_totalsize,
            "time_range": brushtask_time_range,
            "label": brushtask_label,
            "savepath": brushtask_savepath,
            "transfer": brushtask_transfer,
            "state": brushtask_state,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "stop_rule": stop_rule,
            "sendmessage": brushtask_sendmessage
        }
        BrushTask().update_brushtask(brushtask_id, item)
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
        if not rules:
            return ""
        rule_filter_string = {"gt": ">", "lt": "<", "bw": ""}
        rule_htmls = []

        if rules.get("exclude_subscribe"):
            exclude_subscribe = rules.get("exclude_subscribe")
            if exclude_subscribe == "Y":
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="排除订阅">排除订阅: 开</span>')
            else:
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="排除订阅">排除订阅: 关</span>')

        if rules.get("size"):
            sizes = rules.get("size").split("#")
            if sizes[0]:
                if sizes[1]:
                    sizes[1] = sizes[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="种子大小">种子大小: %s %sGB</span>'
                    % (rule_filter_string.get(sizes[0]), sizes[1]))
        if rules.get("pubdate"):
            pubdates = rules.get("pubdate").split("#")
            if pubdates[0]:
                if pubdates[1]:
                    pubdates[1] = pubdates[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="发布时间">发布时间: %s %s小时</span>'
                    % (rule_filter_string.get(pubdates[0]), pubdates[1]))
        if rules.get("upspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="上传限速">上传限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("upspeed")) * 1024))
        if rules.get("downspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="下载限速">下载限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("downspeed")) * 1024))
        if rules.get("include"):
            rule_htmls.append(
                '<span class="badge badge-outline text-green me-1 mb-1 text-wrap text-start" title="包含规则">包含: %s</span>'
                % rules.get("include"))
        if rules.get("hr"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1" title="排除HR">排除: HR</span>')
        if rules.get("exclude"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1 text-wrap text-start" title="排除规则">排除: %s</span>'
                % rules.get("exclude"))
        if rules.get("dlcount"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="同时下载数量限制">同时下载: %s</span>'
                              % rules.get("dlcount"))
        if rules.get("peercount"):
            peer_counts = None
            if rules.get("peercount") == "#":
                peer_counts = None
            elif "#" in rules.get("peercount"):
                peer_counts = rules.get("peercount").split("#")
                peer_counts[1] = peer_counts[1].replace(",", "-") if (len(peer_counts) >= 2 and peer_counts[1]) else \
                    peer_counts[1]
            else:
                try:
                    # 兼容性代码
                    peer_counts = ["lt", int(rules.get("peercount"))]
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    pass
            if peer_counts:
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="当前做种人数限制">做种人数: %s %s</span>'
                    % (rule_filter_string.get(peer_counts[0]), peer_counts[1]))

        if rules.get("mode"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1 text-wrap text-start" title="删种模式">删种模式: %s</span>'
                % ("与" if rules.get("mode") == "and" else "或"))
        if rules.get("time"):
            times = rules.get("time").split("#")
            if times[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="做种时间">做种时间: %s %s小时</span>'
                    % (rule_filter_string.get(times[0]), times[1]))
        if rules.get("ratio"):
            ratios = rules.get("ratio").split("#")
            if ratios[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="分享率">分享率: %s %s</span>'
                    % (rule_filter_string.get(ratios[0]), ratios[1]))
        if rules.get("uploadsize"):
            uploadsizes = rules.get("uploadsize").split("#")
            if uploadsizes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="上传量">上传量: %s %sGB</span>'
                    % (rule_filter_string.get(uploadsizes[0]), uploadsizes[1]))
        if rules.get("dltime"):
            dltimes = rules.get("dltime").split("#")
            if dltimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="下载耗时">下载耗时: %s %s小时</span>'
                    % (rule_filter_string.get(dltimes[0]), dltimes[1]))
        if rules.get("avg_upspeed"):
            avg_upspeeds = rules.get("avg_upspeed").split("#")
            if avg_upspeeds[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="平均上传速度">平均上传速度: %s %sKB/S</span>'
                    % (rule_filter_string.get(avg_upspeeds[0]), avg_upspeeds[1]))
        if rules.get("iatime"):
            iatimes = rules.get("iatime").split("#")
            if iatimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="未活动时间">未活动时间: %s %s小时</span>'
                    % (rule_filter_string.get(iatimes[0]), iatimes[1]))
        if rules.get("freestatus"):
            freestatus = rules.get("freestatus")
            if freestatus == "Y":
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="Free 到期">Free 到期: 开</span>')
            else:
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="Free 到期">Free 到期: 关</span>')

        if rules.get("stopfree"):
            stopfree = rules.get("stopfree")
            if stopfree == "Y":
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="Free 到期">Free 到期: 开</span>')
            else:
                rule_htmls.append(
                    '<span class="badge badge-outline text-green me-1 mb-1" title="Free 到期">Free 到期: 关</span>')

        if rules.get("freespace"):
            freespace = rules.get("freespace").split("#")
            if freespace[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="磁盘剩余空间">磁盘剩余空间: %s %sGB</span>'
                    % (rule_filter_string.get(freespace[0]), freespace[1]))
        return "<br>".join(rule_htmls)

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
