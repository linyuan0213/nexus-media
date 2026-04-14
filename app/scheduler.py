import datetime
import pytz

import log
from app.helper import ThreadHelper
from app.mediaserver import MediaServer
from app.rss import Rss
from app.sites import SiteUserInfo
from app.subscribe import Subscribe
from app.sync import Sync
from app.utils import SchedulerUtils
from app.utils.commons import SingletonMeta
from config import METAINFO_SAVE_INTERVAL, \
    SYNC_TRANSFER_INTERVAL, RSS_CHECK_INTERVAL, \
    RSS_REFRESH_TMDB_INTERVAL, META_DELETE_UNKNOWN_INTERVAL, REFRESH_WALLPAPER_INTERVAL, Config
from web.backend.wallpaper import get_login_wallpaper
from app.helper.temp_cleanup_helper import TempCleanupHelper

from app.scheduler_service import SchedulerService


class Scheduler(metaclass=SingletonMeta):
    scheduler = None
    _pt = None
    _media = None
    _jobstore = 'default'

    def __init__(self):
        self.init_config()

    def init_config(self):
        self._pt = Config().get_config('pt')
        self._media = Config().get_config('media')
        self.scheduler = SchedulerService()
        self.scheduler.start_service()
        self.run_service()

    def run_service(self):
        """
        读取配置，启动定时服务
        """
        if not self.scheduler:
            return

        if self._pt:
            # 数据统计
            ptrefresh_date_cron = self._pt.get('ptrefresh_date_cron')
            if ptrefresh_date_cron:
                tz = pytz.timezone(Config().get_timezone())
                SchedulerUtils.start_job(
                    scheduler=self.scheduler.SCHEDULER,
                    func=SiteUserInfo().refresh_site_data_now,
                    job_id="SiteUserInfo.refresh_site_data_now",
                    func_desc="数据统计",
                    cron=str(ptrefresh_date_cron),
                    next_run_time=datetime.datetime.now(tz) + datetime.timedelta(minutes=1)
                )

            # RSS下载器
            pt_check_interval = self._pt.get('pt_check_interval')
            if pt_check_interval:
                if isinstance(pt_check_interval, str) and pt_check_interval.isdigit():
                    pt_check_interval = int(pt_check_interval)
                else:
                    try:
                        pt_check_interval = round(float(pt_check_interval))
                    except Exception as e:
                        log.error("RSS订阅周期 配置格式错误：%s" % str(e))
                        pt_check_interval = 0
                if pt_check_interval:
                    if pt_check_interval < 300:
                        pt_check_interval = 300

                    self.scheduler.register_interval(
                        job_id="Rss.rssdownload",
                        func=Rss().rssdownload,
                        seconds=pt_check_interval,
                        jobstore=self._jobstore
                    )
                    log.info("RSS订阅服务启动")

            # RSS订阅定时搜索
            search_rss_interval = self._pt.get('search_rss_interval')
            if search_rss_interval:
                if isinstance(search_rss_interval, str) and search_rss_interval.isdigit():
                    search_rss_interval = int(search_rss_interval)
                else:
                    try:
                        search_rss_interval = round(float(search_rss_interval))
                    except Exception as e:
                        log.error("订阅定时搜索周期 配置格式错误：%s" % str(e))
                        search_rss_interval = 0
                if search_rss_interval:
                    if search_rss_interval < 2:
                        search_rss_interval = 2

                    self.scheduler.register_interval(
                        job_id="Subscribe.subscribe_search_all",
                        func=Subscribe().subscribe_search_all,
                        hours=search_rss_interval,
                        jobstore=self._jobstore
                    )
                    log.info("订阅定时搜索服务启动")

        # 媒体库同步
        if self._media:
            mediasync_interval = self._media.get("mediasync_interval")
            if mediasync_interval:
                if isinstance(mediasync_interval, str):
                    if mediasync_interval.isdigit():
                        mediasync_interval = int(mediasync_interval)
                    else:
                        try:
                            mediasync_interval = round(
                                float(mediasync_interval))
                        except Exception as e:
                            log.info("豆瓣同步服务启动失败：%s" % str(e))
                            mediasync_interval = 0
                if mediasync_interval:
                    self.scheduler.register_interval(
                        job_id="MediaServer.sync_mediaserver",
                        func=MediaServer().sync_mediaserver,
                        hours=mediasync_interval,
                        jobstore=self._jobstore
                    )
                    log.info("媒体库同步服务启动")

        # 定时把队列中的监控文件转移走
        self.scheduler.register_interval(
            job_id="Sync.transfer_mon_files",
            func=Sync().transfer_mon_files,
            seconds=SYNC_TRANSFER_INTERVAL,
            jobstore=self._jobstore
        )

        # RSS队列中搜索
        self.scheduler.register_interval(
            job_id="Subscribe.subscribe_search",
            func=Subscribe().subscribe_search,
            seconds=RSS_CHECK_INTERVAL,
            jobstore=self._jobstore
        )

        # 豆瓣RSS转TMDB，定时更新TMDB数据
        self.scheduler.register_interval(
            job_id="Subscribe.refresh_rss_metainfo",
            func=Subscribe().refresh_rss_metainfo,
            hours=RSS_REFRESH_TMDB_INTERVAL,
            jobstore=self._jobstore
        )

        # 定时刷新壁纸
        self.scheduler.register_interval(
            job_id="get_login_wallpaper",
            func=get_login_wallpaper,
            hours=REFRESH_WALLPAPER_INTERVAL,
            next_run_time=datetime.datetime.now(),
            jobstore=self._jobstore
        )

        # 定时清理临时文件（每6小时执行一次）
        self.scheduler.register_interval(
            job_id="TempCleanupHelper.do_cleanup",
            func=TempCleanupHelper.do_cleanup,
            seconds=6 * 3600,  # 6小时
            next_run_time=datetime.datetime.now(),
            jobstore=self._jobstore
        )

    def stop_service(self):
        self.scheduler.stop_service()
