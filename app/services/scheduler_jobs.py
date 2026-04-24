import datetime
import pytz

import log
from app.mediaserver import MediaServer
from app.services.rss_core import Rss
from app.sites import SiteUserInfo
from app.services.subscribe_service import SubscribeService as Subscribe
from app.services.sync_core import SyncCore as Sync
from config import (
    SYNC_TRANSFER_INTERVAL,
    RSS_CHECK_INTERVAL,
    RSS_REFRESH_TMDB_INTERVAL,
    REFRESH_WALLPAPER_INTERVAL,
    Config,
)
from app.utils.wallpaper import get_login_wallpaper
from app.helper.temp_cleanup_helper import TempCleanupHelper


def load_default_jobs(scheduler):
    """
    加载系统默认定时任务
    :param scheduler: SchedulerCore 实例
    """
    if not scheduler:
        return

    _pt = Config().get_config('pt')
    _media = Config().get_config('media')
    _jobstore = 'default'

    if _pt:
        # 数据统计
        ptrefresh_date_cron = _pt.get('ptrefresh_date_cron')
        if ptrefresh_date_cron:
            tz = pytz.timezone(Config().get_timezone())
            scheduler.register_smart_cron(
                job_id="SiteUserInfo.refresh_site_data_now",
                func=SiteUserInfo().refresh_site_data_now,
                name="站点数据统计",
                func_desc="站点数据统计",
                cron=str(ptrefresh_date_cron),
                next_run_time=datetime.datetime.now(tz) + datetime.timedelta(minutes=1),
                jobstore=_jobstore
            )

        # RSS下载器
        pt_check_interval = _pt.get('pt_check_interval')
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

                scheduler.register_interval(
                    job_id="Rss.rssdownload",
                    name="RSS订阅下载",
                    func=Rss().rssdownload,
                    seconds=pt_check_interval,
                    jobstore=_jobstore
                )
                log.info("RSS订阅服务启动")

        # RSS订阅定时搜索
        search_rss_interval = _pt.get('search_rss_interval')
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

                scheduler.register_interval(
                    job_id="Subscribe.subscribe_search_all",
                    name="订阅搜索",
                    func=Subscribe().subscribe_search_all,
                    hours=search_rss_interval,
                    jobstore=_jobstore
                )
                log.info("订阅定时搜索服务启动")

    # 媒体库同步
    if _media:
        mediasync_interval = _media.get("mediasync_interval")
        if mediasync_interval:
            if isinstance(mediasync_interval, str):
                if mediasync_interval.isdigit():
                    mediasync_interval = int(mediasync_interval)
                else:
                    try:
                        mediasync_interval = round(float(mediasync_interval))
                    except Exception as e:
                        log.info("豆瓣同步服务启动失败：%s" % str(e))
                        mediasync_interval = 0
            if mediasync_interval:
                scheduler.register_interval(
                    job_id="MediaServer.sync_mediaserver",
                    name="媒体库同步",
                    func=MediaServer().sync_mediaserver,
                    hours=mediasync_interval,
                    jobstore=_jobstore
                )
                log.info("媒体库同步服务启动")

    # 定时把队列中的监控文件转移走
    scheduler.register_interval(
        job_id="Sync.transfer_mon_files",
        name="目录同步监控",
        func=Sync().transfer_mon_files,
        seconds=SYNC_TRANSFER_INTERVAL,
        jobstore=_jobstore
    )

    # RSS队列中搜索
    scheduler.register_interval(
        job_id="Subscribe.subscribe_search",
        name="订阅队列状态搜索",
        func=Subscribe().subscribe_search,
        seconds=RSS_CHECK_INTERVAL,
        jobstore=_jobstore
    )

    # 豆瓣RSS转TMDB，定时更新TMDB数据
    scheduler.register_interval(
        job_id="Subscribe.refresh_rss_metainfo",
        name="豆瓣RSS转TMDB",
        func=Subscribe().refresh_rss_metainfo,
        hours=RSS_REFRESH_TMDB_INTERVAL,
        jobstore=_jobstore
    )

    # 定时刷新壁纸
    scheduler.register_interval(
        job_id="get_login_wallpaper",
        name="定时刷新壁纸",
        func=get_login_wallpaper,
        hours=REFRESH_WALLPAPER_INTERVAL,
        next_run_time=datetime.datetime.now(),
        jobstore=_jobstore
    )

    # 定时清理临时文件（每6小时执行一次）
    scheduler.register_interval(
        job_id="TempCleanupHelper.do_cleanup",
        name="定时清理临时文件",
        func=TempCleanupHelper.do_cleanup,
        seconds=6 * 3600,
        next_run_time=datetime.datetime.now(),
        jobstore=_jobstore
    )
