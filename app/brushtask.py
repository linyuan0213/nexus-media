import json
import time
from datetime import datetime, time as dtime
from urllib.parse import urlsplit

from app.brushtask_rule import BrushRuleEngine
from app.entities.torrent import Torrent
from app.entities.torrentstatus import TorrentStatus
from app.media.meta import MetaInfo
from app.message import Message
from app.sites import Sites, SiteConf
from app.downloader import Downloader
from app.services.filter_service import FilterService as Filter
from app.helper import RssHelper
from app.db.repositories import BrushRepository
from app.services.scheduler_core import SchedulerCore
from app.utils import StringUtils, ExceptionUtils, JsonUtils, RedisStore
from app.utils.commons import SingletonMeta
from app.utils.types import BrushDeleteType, MediaType
import log
from config import Config


class BrushTask(metaclass=SingletonMeta):
    message = None
    sites = None
    siteconf = None
    filter = None
    brush_repo = None
    rsshelper = None
    downloader = None
    redis_store = None
    _jobstore = "brushtask"
    _brush_tasks = {}
    _torrents_cache = set()
    _qb_client = "qbittorrent"
    _tr_client = "transmission"

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.brush_repo = BrushRepository()
        self.rsshelper = RssHelper()
        self.message = Message()
        self.sites = Sites()
        self.siteconf = SiteConf()
        self.filter = Filter()
        self.downloader = Downloader()
        self.redis_store = RedisStore()
        # 移除现有任务
        self.stop_service()
        # 读取刷流任务列表
        self.load_brushtasks()
        # 清理缓存
        self._torrents_cache.clear()
        # 启动RSS任务
        if self._brush_tasks:
            running_task = 0
            for _, task in self._brush_tasks.items():
                if task.get("state") in ['Y', 'S'] and task.get("interval"):
                    cron = str(task.get("interval")).strip()
                    if cron.isdigit() or cron.count(" ") == 4:
                        running_task += self._start_task_jobs(task, cron)
                    else:
                        log.error(f"任务 {task.get('name')} 运行周期格式不正确")
            if running_task > 0:
                log.info(f"{running_task} 个刷流服务正常启动")

    def _start_task_jobs(self, task: dict, cron: str) -> int:
        """为单个任务启动调度任务，返回成功启动的rss任务数"""
        task_id = task.get("id")
        task_name = task.get("name")
        is_running = task.get("state") == 'Y'
        running = 0

        trigger_type = "interval" if cron.isdigit() else "cron"
        trigger_args = {"seconds": int(cron) * 60} if trigger_type == "interval" else {"cron": cron}

        if is_running:
            try:
                job_id = f"BrushTask.check_task_rss_{task_id}"
                SchedulerCore().start_job({
                    "func": self.check_task_rss,
                    "name": f"刷流任务 {task_name} ",
                    "args": (task_id,),
                    "job_id": job_id,
                    "trigger": trigger_type,
                    "jobstore": self._jobstore,
                    **trigger_args
                })
                running = 1
            except Exception as err:
                log.error(f"任务 {task_name} 运行周期格式不正确：{str(err)}")

        for func, name in [(self.stop_task_torrents, "停种任务"), (self.remove_task_torrents, "删种任务")]:
            try:
                job_id = f"BrushTask.{func.__name__}_{task_id}"
                SchedulerCore().start_job({
                    "func": func,
                    "name": f"{name} {task_name} ",
                    "args": (task_id,),
                    "job_id": job_id,
                    "trigger": trigger_type,
                    "jobstore": self._jobstore,
                    **trigger_args
                })
            except Exception as err:
                log.error(f"任务 {task_name} {name} 运行周期格式不正确：{str(err)}")

        return running

    def _stop_task_jobs(self, task_id):
        """停止单个任务的所有调度任务"""
        job_ids = [
            f"BrushTask.check_task_rss_{task_id}",
            f"BrushTask.stop_task_torrents_{task_id}",
            f"BrushTask.remove_task_torrents_{task_id}",
        ]
        for job_id in job_ids:
            try:
                SchedulerCore().remove_job(job_id, jobstore=self._jobstore)
            except Exception:
                pass

    def _reload_single_task(self, task_id):
        """从数据库重载单个任务并更新内存缓存和调度"""
        task_rows = self.brush_repo.get_brushtasks(brush_id=task_id)
        if not task_rows:
            self._brush_tasks.pop(str(task_id), None)
            self._stop_task_jobs(task_id)
            return

        task = task_rows[0] if isinstance(task_rows, (list, tuple)) else task_rows
        site_info = self.sites.get_sites(siteid=task.SITE)
        site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl")) if site_info else ""
        downloader_info = self.downloader.get_downloader_conf(task.DOWNLOADER)
        total_size = round(int(self.brush_repo.get_brushtask_totalsize(task.ID)) / (1024 ** 3), 1)
        seed_size_gb = round(int(task.SEED_SIZE) / (1024 ** 3), 1) if task.SEED_SIZE else 0
        self._brush_tasks[str(task.ID)] = {
            "id": task.ID,
            "name": task.NAME,
            "site": site_info.get("name") if site_info else None,
            "site_id": task.SITE,
            "interval": task.INTEVAL,
            "label": task.LABEL,
            "savepath": task.SAVEPATH,
            "state": task.STATE,
            "downloader": task.DOWNLOADER,
            "downloader_name": downloader_info.get("name") if downloader_info else None,
            "transfer": True if task.TRANSFER == "Y" else False,
            "sendmessage": True if task.SENDMESSAGE == "Y" else False,
            "free": task.FREELEECH,
            "rss_rule": json.loads(task.RSS_RULE or '{}'),
            "remove_rule": json.loads(task.REMOVE_RULE or '{}'),
            "stop_rule": json.loads(task.STOP_RULE or '{"stopfree": "Y"}'),
            "seed_size": seed_size_gb,
            "time_range": task.TIME_RANGE,
            "total_size": total_size,
            "rss_url": task.RSSURL if task.RSSURL else (site_info.get("rssurl") if site_info else None),
            "rss_url_show": task.RSSURL,
            "cookie": site_info.get("cookie") if site_info else None,
            "ua": site_info.get("ua") if site_info else None,
            "headers": site_info.get("headers") if site_info else None,
            "download_count": task.DOWNLOAD_COUNT,
            "remove_count": task.REMOVE_COUNT,
            "download_size": StringUtils.str_filesize(task.DOWNLOAD_SIZE),
            "upload_size": StringUtils.str_filesize(task.UPLOAD_SIZE),
            "lst_mod_date": task.LST_MOD_DATE,
            "site_url": site_url
        }

        self._stop_task_jobs(task.ID)
        cron = str(task.INTEVAL).strip()
        if task.STATE in ['Y', 'S'] and cron and (cron.isdigit() or cron.count(" ") == 4):
            self._start_task_jobs(self._brush_tasks[str(task.ID)], cron)

    def load_brushtasks(self):
        """
        从数据库加载刷流任务
        """
        self._brush_tasks = {}
        brushtasks = self.brush_repo.get_brushtasks()
        if not brushtasks:
            return
        for task in brushtasks:
            site_info = self.sites.get_sites(siteid=task.SITE)
            site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl")) if site_info else ""
            downloader_info = self.downloader.get_downloader_conf(task.DOWNLOADER)
            total_size = round(int(self.brush_repo.get_brushtask_totalsize(task.ID)) / (1024 ** 3), 1)
            seed_size_gb = round(int(task.SEED_SIZE) / (1024 ** 3), 1) if task.SEED_SIZE else 0
            self._brush_tasks[str(task.ID)] = {
                "id": task.ID,
                "name": task.NAME,
                "site": site_info.get("name") if site_info else None,
                "site_id": task.SITE,
                "interval": task.INTEVAL,
                "label": task.LABEL,
                "savepath": task.SAVEPATH,
                "state": task.STATE,
                "downloader": task.DOWNLOADER,
                "downloader_name": downloader_info.get("name") if downloader_info else None,
                "transfer": True if task.TRANSFER == "Y" else False,
                "sendmessage": True if task.SENDMESSAGE == "Y" else False,
                "free": task.FREELEECH,
                "rss_rule": json.loads(task.RSS_RULE or '{}'),
                "remove_rule": json.loads(task.REMOVE_RULE or '{}'),
                "stop_rule": json.loads(task.STOP_RULE or '{"stopfree": "Y"}'),
                "seed_size": seed_size_gb,
                "time_range": task.TIME_RANGE,
                "total_size": total_size,
                "rss_url": task.RSSURL if task.RSSURL else (site_info.get("rssurl") if site_info else None),
                "rss_url_show": task.RSSURL,
                "cookie": site_info.get("cookie") if site_info else None,
                "ua": site_info.get("ua") if site_info else None,
                "headers": site_info.get("headers") if site_info else None,
                "download_count": task.DOWNLOAD_COUNT,
                "remove_count": task.REMOVE_COUNT,
                "download_size": StringUtils.str_filesize(task.DOWNLOAD_SIZE),
                "upload_size": StringUtils.str_filesize(task.UPLOAD_SIZE),
                "lst_mod_date": task.LST_MOD_DATE,
                "site_url": site_url
            }

    def get_brushtask_info(self, taskid=None):
        """
        读取刷流任务列表
        """
        if taskid:
            return self._brush_tasks.get(str(taskid)) or {}
        return list(self._brush_tasks.values())

    def check_task_rss(self, taskid):
        """
        检查RSS并添加下载，由定时服务调用
        :param taskid: 刷流任务的ID
        """
        if not taskid:
            return
        taskinfo = self.get_brushtask_info(taskid)
        if not taskinfo:
            return

        task_name = taskinfo.get("name")
        site_id = taskinfo.get("site_id")
        rss_url = taskinfo.get("rss_url")
        rss_rule = taskinfo.get("rss_rule")
        cookie = taskinfo.get("cookie")
        rss_free = taskinfo.get("free")
        downloader_id = taskinfo.get("downloader")
        ua = taskinfo.get("ua")
        headers = taskinfo.get("headers")
        if JsonUtils.is_valid_json(headers):
            headers = json.loads(headers)
        else:
            headers = {}
        headers.update({'User-Agent': ua})
        state = taskinfo.get("state")
        if state != 'Y':
            log.info("【Brush】刷流任务 %s 已停止下载新种！" % task_name)
            return

        site_info = self.sites.get_sites(siteid=site_id)
        if not site_info:
            log.error("【Brush】刷流任务 %s 的站点已不存在，无法刷流！" % task_name)
            return

        site_id = site_info.get("id")
        site_name = site_info.get("name")
        site_proxy = site_info.get("proxy")
        site_brush_enable = site_info.get("brush_enable")
        if not site_brush_enable:
            log.error("【Brush】站点 %s 未开启刷流功能，无法刷流！" % site_name)
            return
        if not rss_url:
            log.error("【Brush】站点 %s 未配置RSS订阅地址，无法刷流！" % site_name)
            return
        if rss_free and (not cookie and not taskinfo.get("headers")):
            log.warn("【Brush】站点 %s 未配置Cookie或请求头，无法开启促销刷流" % site_name)
            return

        downloader_cfg = self.downloader.get_downloader_conf(downloader_id)
        if not downloader_cfg:
            log.error("【Brush】任务 %s 下载器不存在，无法刷流！" % task_name)
            return

        log.info("【Brush】开始站点 %s 的刷流任务：%s..." % (site_name, task_name))
        if not self.__is_allow_new_torrent(taskinfo=taskinfo, dlcount=rss_rule.get("dlcount")):
            return

        rss_result = self.rsshelper.parse_rssxml(url=rss_url, proxy=site_proxy)
        if rss_result is None:
            log.error(f"【Brush】{task_name} RSS链接已过期，请重新获取！")
            return
        if len(rss_result) == 0:
            log.warn("【Brush】%s RSS未下载到数据" % site_name)
            return
        else:
            log.info("【Brush】%s RSS获取数据：%s" % (site_name, len(rss_result)))

        max_dlcount = rss_rule.get("dlcount")
        success_count = 0
        new_torrent_count = 0
        if max_dlcount:
            downloading_count = self.__get_downloading_count(downloader_id) or 0
            new_torrent_count = int(max_dlcount) - int(downloading_count)

        for res in rss_result:
            try:
                torrent_name = res.get('title')
                enclosure = res.get('enclosure')
                page_url = res.get('link')
                size = res.get('size')
                pubdate = res.get('pubdate')

                if enclosure not in self._torrents_cache:
                    if len(self._torrents_cache) >= 10000:
                        self._torrents_cache = set(list(self._torrents_cache)[5000:])
                    self._torrents_cache.add(enclosure)
                else:
                    log.debug("【Brush】%s 已处理过" % torrent_name)
                    continue

                torrent_attr = self.siteconf.check_torrent_attr(torrent_url=page_url,
                                                                cookie=cookie,
                                                                ua=ua,
                                                                headers=headers,
                                                                proxy=site_proxy)
                log.debug("【Brush】%s 解析详情, %s" % (torrent_name, torrent_attr))
                if not BrushRuleEngine.check_rss_rule(rss_rule=rss_rule,
                                                       title=torrent_name,
                                                       torrent_size=size,
                                                       pubdate=pubdate,
                                                       torrent_attr=torrent_attr):
                    continue
                if not self.__is_allow_new_torrent(taskinfo=taskinfo,
                                                   dlcount=max_dlcount,
                                                   torrent_size=size):
                    continue
                if self.is_torrent_handled(enclosure=enclosure):
                    log.info("【Brush】%s 已在刷流任务中" % torrent_name)
                    continue

                log.debug("【Brush】%s 符合条件，开始下载..." % torrent_name)
                if self.__download_torrent(taskinfo=taskinfo,
                                           rss_rule=rss_rule,
                                           site_info=site_info,
                                           title=torrent_name,
                                           enclosure=enclosure,
                                           size=size,
                                           page_url=page_url):
                    success_count += 1
                    if max_dlcount and success_count >= new_torrent_count:
                        break
                    if not self.__is_allow_new_torrent(taskinfo=taskinfo, dlcount=max_dlcount):
                        break
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue
        log.info("【Brush】任务 %s 本次添加了 %s 个下载" % (task_name, success_count))

    def remove_task_torrents(self, taskid):
        """
        根据条件检查所有任务下载完成的种子，按条件进行删除，并更新任务数据
        由定时服务调用
        """
        taskinfo = self.get_brushtask_info(taskid)
        try:
            total_uploaded = 0
            total_downloaded = 0
            delete_ids = []
            update_torrents = []
            remove_torrent_ids = set()

            site_id = taskinfo.get("site_id")
            task_name = taskinfo.get("name")
            downloader_id = taskinfo.get("downloader")
            remove_rule = taskinfo.get("remove_rule")
            sendmessage = taskinfo.get("sendmessage")
            download_dir = taskinfo.get("savepath")
            downloader_cfg = self.downloader.get_downloader_conf(downloader_id)

            site_info = self.sites.get_sites(siteid=site_id)
            if not downloader_cfg:
                log.warn(f"【Brush】任务 {task_name} 下载器不存在")
                return

            task_torrents = self.get_brushtask_torrents(taskid)
            torrent_id_maps = {
                item.DOWNLOAD_ID: item.ENCLOSURE for item in task_torrents if item.DOWNLOAD_ID}
            torrent_ids = list(torrent_id_maps.keys())
            if not torrent_ids:
                return

            # 查询下载器完成的种子并处理
            completed_torrents = self.downloader.get_completed_torrents(downloader_id, torrent_ids)
            if completed_torrents is None:
                log.warn(f"【Brush】任务 {task_name} 获取下载完成种子失败")
                return
            remove_torrent_ids = set(torrent_ids) - {torrent.id for torrent in completed_torrents}
            total_uploaded, total_downloaded, delete_ids, update_torrents = self._process_torrents(
                completed_torrents, taskinfo, downloader_cfg, site_info, remove_rule, total_uploaded, total_downloaded,
                delete_ids, update_torrents, torrent_id_maps
            )

            # 查询下载中种子并处理
            downloading_torrents = self.downloader.get_downloading_torrents(downloader_id, torrent_ids)
            if downloading_torrents is None:
                log.warn(f"【Brush】任务 {task_name} 获取下载中种子失败")
                return
            remove_torrent_ids -= {torrent.id for torrent in downloading_torrents}
            total_uploaded, total_downloaded, delete_ids, update_torrents = self._process_torrents(
                downloading_torrents, taskinfo, downloader_cfg, site_info, remove_rule, total_uploaded, total_downloaded,
                delete_ids, update_torrents, torrent_id_maps, is_downloading=True
            )

            # 删除下载器中已不存在的种子
            if remove_torrent_ids:
                log.info(f"【Brush】任务 {task_name} 删除不存在的下载任务：{remove_torrent_ids}")
                for remove_torrent_id in remove_torrent_ids:
                    self.brush_repo.delete_brushtask_torrent(taskid, remove_torrent_id)

            # 删除符合条件的种子
            if delete_ids:
                self.downloader.delete_torrents(downloader_id, delete_ids, delete_file=True)
                time.sleep(5)
                torrents = self.downloader.get_torrents(downloader_id, delete_ids)
                if torrents is None:
                    delete_ids = []
                    update_torrents = []
                else:
                    for torrent in torrents:
                        if torrent.id in delete_ids:
                            delete_ids.remove(torrent.id)

                if delete_ids:
                    self.brush_repo.update_brushtask_torrent_state(update_torrents)
                    log.info(f"【Brush】任务 {task_name} 共删除 {len(delete_ids)} 个刷流下载任务")
                else:
                    log.info(f"【Brush】任务 {task_name} 本次检查未删除下载任务")

            # 更新任务统计数据
            self.brush_repo.add_brushtask_upload_count(taskid, total_uploaded, total_downloaded,
                                                     len(delete_ids) + len(remove_torrent_ids))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def _process_torrents(self, torrents: list[Torrent], taskinfo: dict, downloader_cfg: dict, site_info: dict,
                          remove_rule: dict, total_uploaded: int, total_downloaded: int,
                          delete_ids: list, update_torrents: list, torrent_id_maps: dict,
                          is_downloading: bool = False):
        """
        处理种子的删除或更新逻辑
        """
        task_name = taskinfo.get("name")
        sendmessage = taskinfo.get("sendmessage")
        downloader_id = taskinfo.get("downloader")
        download_dir = taskinfo.get("savepath")

        for torrent in torrents:
            torrent_id = torrent.id
            total_uploaded += torrent.uploaded
            total_downloaded += torrent.downloaded

            enclosure = torrent_id_maps.get(torrent_id)
            torrent_url, torrent_attr = (None, {})
            if enclosure:
                torrent_url, torrent_attr = self.get_torrent_attr(site_info, enclosure)
            log.debug("【Brush】%s 解析详情 %s" % (torrent_url, torrent_attr))

            torrent_params = {
                "seeding_time": torrent.seeding_time,
                "ratio": round(torrent.ratio or 0, 2),
                "uploaded": torrent.uploaded,
                "iatime": torrent.iatime,
                "avg_upspeed": torrent.avg_upload_speed,
                "freespace": self.downloader.get_free_space(downloader_id, download_dir),
                "torrent_attr": torrent_attr,
            }

            if is_downloading:
                torrent_params.update({
                    "dltime": torrent.download_time,
                    "pending_time": torrent.iatime if torrent.status == TorrentStatus.Pending else None
                })

            need_delete, delete_type = BrushRuleEngine.check_remove_rule(remove_rule, torrent_params)
            if need_delete:
                if isinstance(delete_type, list):
                    delete_type_str = ",".join([d.value for d in delete_type])
                else:
                    delete_type_str = delete_type.value
                log.info(f"【Brush】{torrent.name} 达到删种条件：{delete_type_str}，删除任务...")
                if sendmessage:
                    self._send_remove_message(task_name, delete_type_str, torrent, downloader_cfg, torrent_params)

                if torrent_id not in delete_ids:
                    delete_ids.append(torrent_id)
                    update_torrents.append((f"{torrent.uploaded},{torrent.downloaded}", taskinfo.get("id"), torrent_id))

        return total_uploaded, total_downloaded, delete_ids, update_torrents

    def _send_remove_message(self, task_name, delete_type, torrent: Torrent, downloader_cfg: dict, torrent_params: dict):
        _msg_title = f"【刷流任务 {task_name} 删除做种】"
        _msg_text = (
            f"下载器名：{downloader_cfg.get('name')}\n"
            f"种子名称：{torrent.name}\n"
            f"种子大小：{StringUtils.str_filesize(torrent.size)}\n"
            f"已下载量：{StringUtils.str_filesize(torrent.downloaded)}\n"
            f"已上传量：{StringUtils.str_filesize(torrent.uploaded)}\n"
            f"分享比率：{torrent_params['ratio']}\n"
            f"添加时间：{torrent.add_time}\n"
            f"删除时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
            f"删除规则：{delete_type}"
        )
        self.message.send_brushtask_remove_message(title=_msg_title, text=_msg_text)

    def __is_allow_new_torrent(self, taskinfo, dlcount, torrent_size=None):
        """
        检查是否还能添加新的下载
        """
        if not taskinfo:
            return False
        seed_size = taskinfo.get("seed_size") or None
        time_range = taskinfo.get("time_range") or ""
        task_name = taskinfo.get("name")
        downloader_id = taskinfo.get("downloader")
        downloader_name = taskinfo.get("downloader_name")
        total_size = self.brush_repo.get_brushtask_totalsize(taskinfo.get("id"))

        if torrent_size and seed_size:
            if float(torrent_size) + int(total_size) >= (float(seed_size) + 5) * 1024 ** 3:
                log.warn("【Brush】刷流任务 %s 当前保种体积 %sGB，种子大小 %sGB，不添加刷流任务"
                         % (task_name, round(int(total_size) / (1024 ** 3), 1),
                            round(int(torrent_size) / (1024 ** 3), 1)))
                return False
        if seed_size:
            if float(seed_size) * 1024 ** 3 <= int(total_size):
                log.warn("【Brush】刷流任务 %s 当前保种体积 %sGB，不再新增下载"
                         % (task_name, round(int(total_size) / 1024 / 1024 / 1024, 1)))
                return False

        if dlcount:
            downloading_count = self.__get_downloading_count(downloader_id)
            if downloading_count is None:
                log.error("【Brush】任务 %s 下载器 %s 无法连接" % (task_name, downloader_name))
                return False
            if int(downloading_count) >= int(dlcount):
                log.warn("【Brush】下载器 %s 正在下载任务数：%s，超过设定上限，暂不添加下载" % (
                    downloader_name, downloading_count))
                return False

        if not BrushTask.is_in_time_range(time_range=time_range):
            log.warn("【Brush】任务 %s 不在所选时间段 %s 内，暂不添加下载" % (task_name, time_range))
            return False

        return True

    def __get_downloading_count(self, downloader_id):
        """
        查询当前正在下载的任务数
        """
        torrents = self.downloader.get_downloading_torrents(downloader_id=downloader_id) or []
        return len(torrents)

    def __download_torrent(self, taskinfo, rss_rule, site_info, title, enclosure, size, page_url):
        """
        添加下载任务，更新任务数据
        """
        if not enclosure:
            return False
        if self.sites.check_ratelimit(site_info.get("id")):
            return False

        taskid = taskinfo.get("id")
        taskname = taskinfo.get("name")
        transfer = taskinfo.get("transfer")
        sendmessage = taskinfo.get("sendmessage")
        downloader_id = taskinfo.get("downloader")
        download_limit = rss_rule.get("downspeed")
        upload_limit = rss_rule.get("upspeed")
        download_dir = taskinfo.get("savepath")

        _, torrent_attr = self.get_torrent_attr(site_info, enclosure)
        hr_tag = ['HR'] if torrent_attr.get("hr") else []
        tag = taskinfo.get("label").split(',') if taskinfo.get("label") else []
        if not transfer:
            tag = tag + ["已整理"] + hr_tag if tag else ["已整理"] + hr_tag

        meta_info = MetaInfo(title=title)
        meta_info.set_torrent_info(site=site_info.get("name"), enclosure=enclosure, size=size)
        _, download_id, retmsg = self.downloader.download(
            media_info=meta_info,
            tag=tag,
            downloader_id=downloader_id,
            download_dir=download_dir,
            download_setting="-2",
            download_limit=download_limit,
            upload_limit=upload_limit
        )
        if not download_id:
            log.warn(f"【Brush】{taskname} 添加下载任务出错：{title}，"
                     f"错误原因：{retmsg or '下载器添加任务失败'}，"
                     f"种子链接：{enclosure}")
            return False
        else:
            log.info("【Brush】成功添加下载：%s" % title)
            if sendmessage:
                downloader_cfg = self.downloader.get_downloader_conf(downloader_id)
                downlaod_name = downloader_cfg.get("name")
                msg_title = f"【刷流任务 {taskname} 新增下载】"
                msg_text = f"下载器名：{downlaod_name}\n" \
                           f"种子名称：{title}\n" \
                           f"种子大小：{StringUtils.str_filesize(size)}\n" \
                           f"添加时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                self.message.send_brushtask_added_message(title=msg_title, text=msg_text)

        if self.brush_repo.insert_brushtask_torrent(brush_id=taskid, title=title, enclosure=enclosure,
                                                  downloader=downloader_id, download_id=download_id, size=size):
            self.brush_repo.add_brushtask_download_count(brush_id=taskid)
        else:
            log.info("【Brush】%s 已下载过" % title)

        return True

    def stop_service(self):
        """
        停止服务
        """
        try:
            SchedulerCore().remove_all_jobs(jobstore=self._jobstore)
        except Exception as e:
            print(str(e))

    def update_brushtask(self, brushtask_id, item):
        """
        新增/更新刷种任务
        """
        ret = self.brush_repo.update_brushtask(brushtask_id, item)
        if brushtask_id:
            self._reload_single_task(brushtask_id)
        else:
            # 新增任务无法预知ID，回退到全量初始化
            self.init_config()
        return ret

    def delete_brushtask(self, brushtask_id):
        """
        删除刷种任务
        """
        self._stop_task_jobs(brushtask_id)
        ret = self.brush_repo.delete_brushtask(brushtask_id)
        self._brush_tasks.pop(str(brushtask_id), None)
        return ret

    def update_brushtask_state(self, state, brushtask_id=None):
        """
        更新刷种任务状态
        """
        ret = self.brush_repo.update_brushtask_state(tid=brushtask_id, state=state)
        if brushtask_id:
            task = self._brush_tasks.get(str(brushtask_id))
            if task:
                task["state"] = state
            self._reload_single_task(brushtask_id)
        else:
            # 批量更新全部状态：更新内存状态后统一重载缓存与调度
            for task in self._brush_tasks.values():
                task["state"] = state
            self.load_brushtasks()
            self.stop_service()
            if self._brush_tasks:
                for _, task in self._brush_tasks.items():
                    if task.get("state") in ['Y', 'S'] and task.get("interval"):
                        cron = str(task.get("interval")).strip()
                        if cron.isdigit() or cron.count(" ") == 4:
                            self._start_task_jobs(task, cron)
        return ret

    def get_brushtask_torrents(self, brush_id, active=True):
        """
        获取刷种任务的种子列表
        """
        return self.brush_repo.get_brushtask_torrents(brush_id, active)

    def is_torrent_handled(self, enclosure):
        """
        判断种子是否已经处理过
        """
        return self.brush_repo.get_brushtask_torrent_by_enclosure(enclosure)

    def stop_task_torrents(self, taskid):
        """
        检查非free的所有任务正在下载的种子并进行暂停
        由定时服务调用
        """
        taskinfo = self.get_brushtask_info(taskid)
        task_name = taskinfo.get("name")
        stop_rule = taskinfo.get("stop_rule")
        downloader_id = taskinfo.get("downloader")
        sendmessage = taskinfo.get("sendmessage")
        site_id = taskinfo.get("site_id")

        site_info = self.sites.get_sites(siteid=site_id)
        if not site_info:
            log.error("【Brush】刷流任务 %s 的站点已不存在，无法刷流！" % task_name)
            return

        log.info("【Brush】开始非免费种子暂停任务：%s..." % task_name)
        task_torrents = self.get_brushtask_torrents(taskid)
        torrent_id_maps = {
            item.DOWNLOAD_ID: item.ENCLOSURE for item in task_torrents if item.DOWNLOAD_ID}
        torrent_ids = list(torrent_id_maps.keys())
        if not torrent_id_maps:
            return

        downloader_cfg = self.downloader.get_downloader_conf(downloader_id)
        if not downloader_cfg:
            log.warn("【Brush】任务 %s 下载器不存在" % task_name)
            return

        downlaod_name = downloader_cfg.get("name")
        torrents = self.downloader.get_downloading_torrents(downloader_id=downloader_id, ids=torrent_ids)
        if torrents is None:
            log.warn("【Brush】任务 %s 获取正在下载种子失败" % task_name)
            return

        for torrent in torrents:
            torrent_id = torrent.id
            torrent_name = torrent.name
            add_time = torrent.add_time
            enclosure = torrent_id_maps.get(torrent_id)
            if not enclosure:
                continue
            torrent_url, torrent_attr = self.get_torrent_attr(site_info, enclosure)
            log.debug("【Brush】%s 解析详情 %s" % (torrent_url, torrent_attr))

            need_stop, stop_type = BrushRuleEngine.check_stop_rule(stop_rule, torrent_attr=torrent_attr)
            if need_stop:
                log.info("【Brush】%s 触发停种条件：%s，暂停任务..." % (torrent_name, stop_type.value))
                self.downloader.stop_torrents(downloader_id, [torrent_id])
                if sendmessage:
                    self._send_stop_message(task_name, torrent_name, downlaod_name, add_time)

    def _send_stop_message(self, task_name, torrent_name, download_name, add_time):
        _msg_title = f"【刷流任务 {task_name} 暂停做种】"
        _msg_text = (
            f"下载器名：{download_name}\n"
            f"种子名称：{torrent_name}\n"
            f"添加时间：{add_time}\n"
            f"暂停时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
            "暂停原因: free 时间到期"
        )
        self.message.send_brushtask_pause_message(title=_msg_title, text=_msg_text)

    def get_torrent_attr(self, site_info: dict, enclosure: str):
        """
        通过下载链接获取种子属性
        """
        if not site_info:
            return None, {}
        ua = site_info.get("ua")
        headers = site_info.get("headers")
        if JsonUtils.is_valid_json(headers):
            headers = json.loads(site_info.get("headers"))
        else:
            headers = {}
        headers.update({'User-Agent': ua})
        site_proxy = site_info.get("proxy")
        site_cookie = site_info.get("cookie")
        split_url = urlsplit(site_info.get("rssurl"))
        site_base_url = f"{split_url.scheme}://{split_url.netloc}"

        tid = StringUtils.get_tid_by_url(enclosure)
        site_key = next((key for key in ['m-team', 'yemapt', 'star-space'] if key in enclosure), 'default')
        torrent_url = f"{site_base_url}{SiteConf().URL_DETAIL_TEMPLATES[site_key].format(tid=tid)}"

        torrent_attr = self.siteconf.check_torrent_attr(torrent_url=torrent_url,
                                                        cookie=site_cookie,
                                                        ua=ua,
                                                        headers=headers,
                                                        proxy=site_proxy)
        return torrent_url, torrent_attr

    @staticmethod
    def is_in_time_range(time_range: str = ""):
        if not time_range.strip():
            return True
        try:
            periods = time_range.split(",")
            for period in periods:
                start_str, end_str = period.split('-')
                start_hour, start_minute = map(int, start_str.split(':'))
                end_hour, end_minute = map(int, end_str.split(':'))
                start_time = dtime(start_hour, start_minute)
                end_time = dtime(end_hour, end_minute)

                now = datetime.now().time()
                if start_time < end_time:
                    if start_time <= now <= end_time:
                        return True
                else:
                    if now >= start_time or now <= end_time:
                        return True
            return False
        except ValueError:
            log.warn("【Brush】时间段格式错误，应为 'HH:MM-HH:MM'")
            return False
