"""
DbHelper - 兼容层

此模块保留用于向后兼容。
所有方法都委托给 app.db.repositories 中的新 Repository 类。

新代码建议直接使用 Repository 类：
- SearchRepository - 搜索结果
- TransferRepository - 转移历史
- SiteRepository - 站点配置和统计
- RssRepository - RSS订阅
- BrushRepository - 刷流任务
- DownloadRepository - 下载历史和设置
- UserRepository - 用户管理
- SyncRepository - 目录同步
- WordRepository - 自定义识别词
- ConfigRepository - 配置相关
- PluginRepository - 插件历史和黑名单
"""
from enum import Enum
from functools import wraps

from app.db import MainDb
from app.db.models import *
from app.utils.types import  RmtMode

# Import new repositories
from app.db.repositories import (
    SearchRepository,
    TransferRepository,
    SiteRepository,
    RssRepository,
    BrushRepository,
    DownloadRepository,
    UserRepository,
    SyncRepository,
    WordRepository,
    ConfigRepository,
    PluginRepository,
)


def _deprecated(func):
    """Decorator to mark deprecated methods"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


class DbHelper:
    """
    数据库帮助类 - 兼容层
    
    此类保留用于向后兼容，所有方法都委托给新的 Repository 类。
    新代码建议直接使用 Repository 类。
    
    维护状态: 仅维护，不新增功能
    """
    _db = MainDb()

    def __init__(self):
        """初始化所有仓储实例"""
        # Initialize repository instances
        self._search_repo = SearchRepository()
        self._transfer_repo = TransferRepository()
        self._site_repo = SiteRepository()
        self._rss_repo = RssRepository()
        self._brush_repo = BrushRepository()
        self._download_repo = DownloadRepository()
        self._user_repo = UserRepository()
        self._sync_repo = SyncRepository()
        self._word_repo = WordRepository()
        self._config_repo = ConfigRepository()
        self._plugin_repo = PluginRepository()

    # ==================== Search Results ====================

    def insert_search_results(self, media_items: list, title=None, ident_flag=True):
        """将返回信息插入数据库"""
        return self._search_repo.insert_search_results(media_items, title, ident_flag)

    def get_search_result_by_id(self, dl_id):
        """根据ID从数据库中查询搜索结果的一条记录"""
        return self._search_repo.get_search_result_by_id(dl_id)

    def get_search_results(self):
        """查询搜索结果的所有记录"""
        return self._search_repo.get_search_results()

    def delete_all_search_torrents(self):
        """删除所有搜索的记录"""
        return self._search_repo.delete_all_search_torrents()

    # ==================== Transfer History ====================

    def is_transfer_history_exists(self, source_path, source_filename, dest_path, dest_filename):
        """查询识别转移记录"""
        return self._transfer_repo.is_transfer_history_exists(source_path, source_filename, dest_path, dest_filename)

    def update_transfer_history_date(self, source_path, source_filename, dest_path, dest_filename, date):
        """更新历史转移记录时间"""
        return self._transfer_repo.update_transfer_history_date(source_path, source_filename, dest_path, dest_filename, date)

    def insert_transfer_history(self, in_from: Enum, rmt_mode: RmtMode, in_path, out_path, dest, media_info):
        """插入识别转移记录"""
        return self._transfer_repo.insert_transfer_history(in_from, rmt_mode, in_path, out_path, dest, media_info)

    def get_transfer_history(self, search, page, rownum):
        """查询识别转移记录"""
        return self._transfer_repo.get_transfer_history(search, page, rownum)

    def get_transfer_info_by_id(self, logid):
        """据logid查询PATH"""
        return self._transfer_repo.get_transfer_info_by_id(logid)

    def get_transfer_info_by(self, tmdbid, season=None, season_episode=None):
        """据tmdbid、season、season_episode查询转移记录"""
        return self._transfer_repo.get_transfer_info_by(tmdbid, season, season_episode)

    def is_transfer_history_exists_by_source_full_path(self, source_full_path):
        """据源文件的全路径查询识别转移记录"""
        return self._transfer_repo.is_transfer_history_exists_by_source_full_path(source_full_path)

    def delete_transfer_log_by_id(self, logid):
        """根据logid删除记录"""
        return self._transfer_repo.delete_transfer_log_by_id(logid)

    def delete_transfer(self):
        """删除所有识别记录"""
        return self._transfer_repo.delete_transfer()

    def get_transfer_statistics(self, days=30):
        """查询历史记录统计"""
        return self._transfer_repo.get_transfer_statistics(days)

    # ==================== Transfer Unknown ====================

    def get_transfer_unknown_paths(self):
        """查询未识别的记录列表"""
        return self._transfer_repo.get_transfer_unknown_paths()

    def get_transfer_unknown_paths_by_page(self, search, page, rownum):
        """按页查询未识别的记录列表"""
        return self._transfer_repo.get_transfer_unknown_paths_by_page(search, page, rownum)

    def update_transfer_unknown_state(self, path):
        """更新未识别记录为识别"""
        return self._transfer_repo.update_transfer_unknown_state(path)

    def delete_transfer_unknown(self, tid):
        """删除未识别记录"""
        return self._transfer_repo.delete_transfer_unknown(tid)

    def get_unknown_info_by_id(self, tid):
        """查询未识别记录"""
        return self._transfer_repo.get_unknown_info_by_id(tid)

    def get_transfer_unknown_by_path(self, path):
        """根据路径查询未识别记录"""
        return self._transfer_repo.get_transfer_unknown_by_path(path)

    def is_transfer_unknown_exists(self, path):
        """查询未识别记录是否存在"""
        return self._transfer_repo.is_transfer_unknown_exists(path)

    def is_need_insert_transfer_unknown(self, path):
        """检查是否需要插入未识别记录"""
        return self._transfer_repo.is_need_insert_transfer_unknown(path)

    def insert_transfer_unknown(self, path, dest, rmt_mode):
        """插入未识别记录"""
        return self._transfer_repo.insert_transfer_unknown(path, dest, rmt_mode)

    # ==================== Transfer Blacklist ====================

    def is_transfer_in_blacklist(self, path):
        """查询是否为黑名单"""
        return self._transfer_repo.is_transfer_in_blacklist(path)

    def is_transfer_notin_blacklist(self, path):
        """查询是否为黑名单"""
        return self._transfer_repo.is_transfer_notin_blacklist(path)

    def insert_transfer_blacklist(self, path):
        """插入黑名单记录"""
        return self._transfer_repo.insert_transfer_blacklist(path)

    def delete_transfer_blacklist(self, path):
        """删除黑名单记录"""
        return self._transfer_repo.delete_transfer_blacklist(path)

    def truncate_transfer_blacklist(self):
        """清空黑名单记录"""
        return self._transfer_repo.truncate_transfer_blacklist()

    # ==================== Sync History ====================

    def is_sync_in_history(self, path, dest):
        """查询是否存在同步历史记录"""
        return self._transfer_repo.is_sync_in_history(path, dest)

    def insert_sync_history(self, path, src, dest):
        """插入黑名单记录"""
        return self._transfer_repo.insert_sync_history(path, src, dest)

    # ==================== Site Configuration ====================

    def get_config_site(self):
        """查询所有站点信息"""
        return self._site_repo.get_config_site()

    def get_site_by_id(self, tid):
        """查询1个站点信息"""
        return self._site_repo.get_site_by_id(tid)

    def insert_config_site(self, name, site_pri, rssurl=None, signurl=None, cookie=None, note=None, rss_uses=None):
        """插入站点信息"""
        return self._site_repo.insert_config_site(name, site_pri, rssurl, signurl, cookie, note, rss_uses)

    def delete_config_site(self, tid):
        """删除站点信息"""
        return self._site_repo.delete_config_site(tid)

    def update_config_site(self, tid, name, site_pri, rssurl, signurl, cookie, note, rss_uses):
        """更新站点信息"""
        return self._site_repo.update_config_site(tid, name, site_pri, rssurl, signurl, cookie, note, rss_uses)

    def update_config_site_note(self, tid, note):
        """更新站点属性"""
        return self._site_repo.update_config_site_note(tid, note)

    def update_site_cookie_ua(self, tid, cookie, ua=None):
        """更新站点Cookie和ua"""
        return self._site_repo.update_site_cookie_ua(tid, cookie, ua)

    def update_site_rssurl(self, tid, rssurl):
        """更新站点rssurl"""
        return self._site_repo.update_site_rssurl(tid, rssurl)

    # ==================== Site User Statistics ====================

    def update_site_user_statistics_site_name(self, new_name, old_name):
        """更新站点用户数据中站点名称"""
        return self._site_repo.update_site_user_statistics_site_name(new_name, old_name)

    def update_site_user_statistics(self, site_user_infos: list):
        """更新站点用户粒度数据"""
        return self._site_repo.update_site_user_statistics(site_user_infos)

    def is_exists_site_user_statistics(self, url):
        """判断站点数据是滞存在"""
        return self._site_repo.is_exists_site_user_statistics(url)

    def is_site_user_statistics_exists(self, url):
        """判断站点用户数据是否存在"""
        return self._site_repo.is_site_user_statistics_exists(url)

    def get_site_user_statistics(self, num=100, strict_urls=None):
        """查询站点数据历史"""
        return self._site_repo.get_site_user_statistics(num, strict_urls)

    # ==================== Site Favicon ====================

    def update_site_favicon(self, site_user_infos: list):
        """更新站点图标数据"""
        return self._site_repo.update_site_favicon(site_user_infos)

    def is_exists_site_favicon(self, site):
        """判断站点图标是否存在"""
        return self._site_repo.is_exists_site_favicon(site)

    def get_site_favicons(self, site=None):
        """查询站点数据历史"""
        return self._site_repo.get_site_favicons(site)

    # ==================== Site Seeding Info ====================

    def update_site_seed_info_site_name(self, new_name, old_name):
        """更新站点做种数据中站点名称"""
        return self._site_repo.update_site_seed_info_site_name(new_name, old_name)

    def update_site_seed_info(self, site_user_infos: list):
        """更新站点做种数据"""
        return self._site_repo.update_site_seed_info(site_user_infos)

    def is_site_seeding_info_exist(self, url):
        """判断做种数据是否已存在"""
        return self._site_repo.is_site_seeding_info_exist(url)

    def get_site_seeding_info(self, site):
        """查询站点做种信息"""
        return self._site_repo.get_site_seeding_info(site)

    # ==================== Site Statistics History ====================

    def is_site_statistics_history_exists(self, url, date):
        """判断站点历史数据是否存在"""
        return self._site_repo.is_site_statistics_history_exists(url, date)

    def update_site_statistics_site_name(self, new_name, old_name):
        """更新站点做种数据中站点名称"""
        return self._site_repo.update_site_statistics_site_name(new_name, old_name)

    def insert_site_statistics_history(self, site_user_infos: list):
        """插入站点数据"""
        return self._site_repo.insert_site_statistics_history(site_user_infos)

    def get_site_statistics_history(self, site, days=30):
        """查询站点数据历史"""
        return self._site_repo.get_site_statistics_history(site, days)

    def get_site_statistics_recent_sites(self, days=7, end_day=None, strict_urls=None):
        """查询近期上传下载量"""
        return self._site_repo.get_site_statistics_recent_sites(days, end_day, strict_urls)

    # ==================== Filter Rules ====================

    def get_config_filter_group(self, gid=None):
        """查询过滤规则组"""
        return self._config_repo.get_config_filter_group(gid)

    def get_config_filter_rule(self, groupid=None):
        """查询过滤规则"""
        return self._config_repo.get_config_filter_rule(groupid)

    def add_filter_group(self, name, default='N'):
        """新增规则组"""
        return self._config_repo.add_filter_group(name, default)

    def get_filter_groupid_by_name(self, name):
        """根据名称获取规则组ID"""
        return self._config_repo.get_filter_groupid_by_name(name)

    def set_default_filtergroup(self, groupid):
        """设置默认的规则组"""
        return self._config_repo.set_default_filtergroup(groupid)

    def delete_filtergroup(self, groupid):
        """删除规则组"""
        return self._config_repo.delete_filtergroup(groupid)

    def delete_filterrule(self, ruleid):
        """删除规则"""
        return self._config_repo.delete_filterrule(ruleid)

    def insert_filter_rule(self, item, ruleid=None):
        """新增规则"""
        return self._config_repo.insert_filter_rule(item, ruleid)

    # ==================== RSS Movies ====================

    def get_rss_movies(self, state=None, rssid=None):
        """查询订阅电影信息"""
        return self._rss_repo.get_rss_movies(state, rssid)

    def get_rss_movie_id(self, title, year=None, tmdbid=None):
        """获取订阅电影ID"""
        return self._rss_repo.get_rss_movie_id(title, year, tmdbid)

    def get_rss_movie_sites(self, rssid):
        """获取订阅电影站点"""
        return self._rss_repo.get_rss_movie_sites(rssid)

    def update_rss_movie_tmdb(self, rid, tmdbid, title, year, image, desc, note):
        """更新订阅电影的部分信息"""
        return self._rss_repo.update_rss_movie_tmdb(rid, tmdbid, title, year, image, desc, note)

    def update_rss_movie_desc(self, rid, desc):
        """更新订阅电影的DESC"""
        return self._rss_repo.update_rss_movie_desc(rid, desc)

    def update_rss_filter_order(self, rtype, rssid, res_order):
        """更新订阅命中的过滤规则优先级"""
        return self._rss_repo.update_rss_filter_order(rtype, rssid, res_order)

    def get_rss_overedition_order(self, rtype, rssid):
        """查询当前订阅的过滤优先级"""
        return self._rss_repo.get_rss_overedition_order(rtype, rssid)

    def is_exists_rss_movie(self, title, year):
        """判断RSS电影是否存在"""
        return self._rss_repo.is_exists_rss_movie(title, year)

    def insert_rss_movie(self, media_info, state='D', rss_sites=None, search_sites=None,
                         over_edition=0, filter_restype=None, filter_pix=None, filter_team=None,
                         filter_rule=None, filter_include=None, filter_exclude=None, save_path=None,
                         download_setting=-1, fuzzy_match=0, desc=None, note=None, keyword=None):
        """新增RSS电影"""
        return self._rss_repo.insert_rss_movie(media_info, state, rss_sites, search_sites,
                                               over_edition, filter_restype, filter_pix, filter_team,
                                               filter_rule, filter_include, filter_exclude, save_path,
                                               download_setting, fuzzy_match, desc, note, keyword)

    def delete_rss_movie(self, title=None, year=None, rssid=None, tmdbid=None):
        """删除RSS电影"""
        return self._rss_repo.delete_rss_movie(title, year, rssid, tmdbid)

    def update_rss_movie_state(self, title=None, year=None, rssid=None, state='R'):
        """更新电影订阅状态"""
        return self._rss_repo.update_rss_movie_state(title, year, rssid, state)

    # ==================== RSS TV Shows ====================

    def get_rss_tvs(self, state=None, rssid=None):
        """查询订阅电视剧信息"""
        return self._rss_repo.get_rss_tvs(state, rssid)

    def get_rss_tv_id(self, title, year=None, season=None, tmdbid=None):
        """获取订阅电视剧ID"""
        return self._rss_repo.get_rss_tv_id(title, year, season, tmdbid)

    def get_rss_tv_sites(self, rssid):
        """获取订阅电视剧站点"""
        return self._rss_repo.get_rss_tv_sites(rssid)

    def update_rss_tv_tmdb(self, rid, tmdbid, title, year, total, lack, image, desc, note):
        """更新订阅电影的TMDBID"""
        return self._rss_repo.update_rss_tv_tmdb(rid, tmdbid, title, year, total, lack, image, desc, note)

    def update_rss_tv_desc(self, rid, desc):
        """更新订阅电视剧的DESC"""
        return self._rss_repo.update_rss_tv_desc(rid, desc)

    def is_exists_rss_tv(self, title, year, season=None):
        """判断RSS电视剧是否存在"""
        return self._rss_repo.is_exists_rss_tv(title, year, season)

    def insert_rss_tv(self, media_info, total, lack=0, state="D", rss_sites=None, search_sites=None,
                      over_edition=0, filter_restype=None, filter_pix=None, filter_team=None,
                      filter_rule=None, filter_include=None, filter_exclude=None, save_path=None,
                      download_setting=-1, total_ep=None, current_ep=None, fuzzy_match=0, desc=None, note=None, keyword=None):
        """新增RSS电视剧"""
        return self._rss_repo.insert_rss_tv(media_info, total, lack, state, rss_sites, search_sites,
                                            over_edition, filter_restype, filter_pix, filter_team,
                                            filter_rule, filter_include, filter_exclude, save_path,
                                            download_setting, total_ep, current_ep, fuzzy_match, desc, note, keyword)

    def update_rss_tv_lack(self, title=None, year=None, season=None, rssid=None, lack_episodes: list = None):
        """更新电视剧缺失的集数"""
        return self._rss_repo.update_rss_tv_lack(title, year, season, rssid, lack_episodes)

    def delete_rss_tv(self, title=None, season=None, rssid=None, tmdbid=None):
        """删除RSS电视剧"""
        return self._rss_repo.delete_rss_tv(title, season, rssid, tmdbid)

    def update_rss_tv_state(self, title=None, year=None, season=None, rssid=None, state='R'):
        """更新电视剧订阅状态"""
        return self._rss_repo.update_rss_tv_state(title, year, season, rssid, state)

    # ==================== RSS TV Episodes ====================

    def is_exists_rss_tv_episodes(self, rid):
        """判断RSS电视剧是否存在"""
        return self._rss_repo.is_exists_rss_tv_episodes(rid)

    def update_rss_tv_episodes(self, rid, episodes):
        """插入或更新电视剧订阅缺失剧集"""
        return self._rss_repo.update_rss_tv_episodes(rid, episodes)

    def get_rss_tv_episodes(self, rid):
        """查询电视剧订阅缺失剧集"""
        return self._rss_repo.get_rss_tv_episodes(rid)

    def delete_rss_tv_episodes(self, rid):
        """删除电视剧订阅缺失剧集"""
        return self._rss_repo.delete_rss_tv_episodes(rid)

    def truncate_rss_episodes(self):
        """清空RSS历史记录"""
        return self._rss_repo.truncate_rss_episodes()

    # ==================== User Management ====================

    def get_users(self, uid=None, name=None):
        """查询用户列表"""
        return self._user_repo.get_users(uid, name)

    def is_user_exists(self, name):
        """判断用户是否存在"""
        return self._user_repo.is_user_exists(name)

    def insert_user(self, name, password, pris):
        """新增用户"""
        return self._user_repo.insert_user(name, password, pris)

    def delete_user(self, name):
        """删除用户"""
        return self._user_repo.delete_user(name)

    # ==================== Download History ====================

    def is_exists_download_history(self, enclosure, downloader, download_id):
        """查询下载历史是否存在"""
        return self._download_repo.is_exists_download_history(enclosure, downloader, download_id)

    def is_exists_download_history_by_tmdb(self, tmdb_id, season_episode):
        """查询下载历史是否存在，根据TMDB ID和季集信息"""
        return self._download_repo.is_exists_download_history_by_tmdb(tmdb_id, season_episode)

    def insert_download_history(self, media_info, downloader, download_id, save_dir):
        """新增下载历史"""
        return self._download_repo.insert_download_history(media_info, downloader, download_id, save_dir)

    def get_download_history(self, date=None, hid=None, num=30, page=1):
        """查询下载历史"""
        return self._download_repo.get_download_history(date, hid, num, page)

    def get_download_history_by_title(self, title):
        """根据标题查找下载历史"""
        return self._download_repo.get_download_history_by_title(title)

    def get_download_history_by_path(self, path):
        """根据路径查找下载历史"""
        return self._download_repo.get_download_history_by_path(path)

    def get_download_history_by_downloader(self, downloader, download_id):
        """根据下载器查找下载历史"""
        return self._download_repo.get_download_history_by_downloader(downloader, download_id)

    # ==================== Brush Tasks ====================

    def update_brushtask(self, brush_id, item):
        """新增刷流任务"""
        return self._brush_repo.update_brushtask(brush_id, item)

    def delete_brushtask(self, brush_id):
        """删除刷流任务"""
        return self._brush_repo.delete_brushtask(brush_id)

    def get_brushtasks(self, brush_id=None):
        """查询刷流任务"""
        return self._brush_repo.get_brushtasks(brush_id)

    def get_brushtask_totalsize(self, brush_id):
        """查询刷流任务总体积"""
        return self._brush_repo.get_brushtask_totalsize(brush_id)

    def update_brushtask_state(self, state, tid=None):
        """改变所有刷流任务的状态"""
        return self._brush_repo.update_brushtask_state(state, tid)

    def add_brushtask_download_count(self, brush_id):
        """增加刷流下载数"""
        return self._brush_repo.add_brushtask_download_count(brush_id)

    def get_brushtask_remove_size(self, brush_id):
        """获取已删除种子的上传量"""
        return self._brush_repo.get_brushtask_remove_size(brush_id)

    def add_brushtask_upload_count(self, brush_id, upload_size, download_size, remove_count):
        """更新上传下载量和删除种子数"""
        return self._brush_repo.add_brushtask_upload_count(brush_id, upload_size, download_size, remove_count)

    def insert_brushtask_torrent(self, brush_id, title, enclosure, downloader, download_id, size):
        """增加刷流下载的种子信息"""
        return self._brush_repo.insert_brushtask_torrent(brush_id, title, enclosure, downloader, download_id, size)

    def get_brushtask_torrents(self, brush_id, active=True):
        """查询刷流任务所有种子"""
        return self._brush_repo.get_brushtask_torrents(brush_id, active)

    def get_brushtask_torrent_by_enclosure(self, enclosure):
        """根据URL查询刷流任务种子"""
        return self._brush_repo.get_brushtask_torrent_by_enclosure(enclosure)

    def is_brushtask_torrent_exists(self, brush_id, title, enclosure):
        """查询刷流任务种子是否已存在"""
        return self._brush_repo.is_brushtask_torrent_exists(brush_id, title, enclosure)

    def update_brushtask_torrent_state(self, ids: list):
        """更新刷流种子的状态"""
        return self._brush_repo.update_brushtask_torrent_state(ids)

    def delete_brushtask_torrent(self, brush_id, download_id):
        """删除刷流种子记录"""
        return self._brush_repo.delete_brushtask_torrent(brush_id, download_id)

    # ==================== User RSS ====================

    def get_userrss_tasks(self, tid=None):
        """查询自定义RSS任务"""
        return self._config_repo.get_userrss_tasks(tid)

    def delete_userrss_task(self, tid):
        """删除自定义RSS任务"""
        return self._config_repo.delete_userrss_task(tid)

    def update_userrss_task_info(self, tid, count):
        """更新自定义RSS任务处理计数"""
        return self._config_repo.update_userrss_task_info(tid, count)

    def update_userrss_task(self, item):
        """更新或插入自定义RSS任务"""
        return self._config_repo.update_userrss_task(item)

    def check_userrss_task(self, tid=None, state=None):
        """设置自定义RSS任务状态"""
        return self._config_repo.check_userrss_task(tid, state)

    def insert_userrss_mediainfos(self, tid=None, mediainfo=None):
        """插入自定义RSS媒体信息"""
        return self._config_repo.insert_userrss_mediainfos(tid, mediainfo)

    def insert_userrss_task_history(self, task_id, title, downloader):
        """增加自定义RSS订阅任务的下载记录"""
        return self._config_repo.insert_userrss_task_history(task_id, title, downloader)

    def get_userrss_task_history(self, task_id):
        """查询自定义RSS订阅任务的下载记录"""
        return self._config_repo.get_userrss_task_history(task_id)

    def get_userrss_parser(self, pid=None):
        """获取自定义RSS解析器"""
        return self._config_repo.get_userrss_parser(pid)

    def delete_userrss_parser(self, pid):
        """删除自定义RSS解析器"""
        return self._config_repo.delete_userrss_parser(pid)

    def update_userrss_parser(self, item):
        """更新或插入自定义RSS解析器"""
        return self._config_repo.update_userrss_parser(item)

    # ==================== RSS History ====================

    def get_rss_history(self, rtype=None, rid=None):
        """查询RSS历史"""
        return self._rss_repo.get_rss_history(rtype, rid)

    def is_exists_rss_history(self, rssid):
        """判断RSS历史是否存在"""
        return self._rss_repo.is_exists_rss_history(rssid)

    def check_rss_history(self, type_str, name, year, season):
        """检查RSS历史是否存在"""
        return self._rss_repo.check_rss_history(type_str, name, year, season)

    def insert_rss_history(self, rssid, rtype, name, year, tmdbid, image, desc, season=None, total=None, start=None):
        """登记RSS历史"""
        return self._rss_repo.insert_rss_history(rssid, rtype, name, year, tmdbid, image, desc, season, total, start)

    def delete_rss_history(self, rssid):
        """删除RSS历史"""
        return self._rss_repo.delete_rss_history(rssid)

    # ==================== Custom Words ====================

    def insert_custom_word(self, replaced, replace, front, back, offset, wtype, gid, season, enabled, regex, whelp, note=None):
        """增加自定义识别词"""
        return self._word_repo.insert_custom_word(replaced, replace, front, back, offset, wtype, gid, season, enabled, regex, whelp, note)

    def delete_custom_word(self, wid=None):
        """删除自定义识别词"""
        return self._word_repo.delete_custom_word(wid)

    def check_custom_word(self, wid=None, enabled=None):
        """设置自定义识别词状态"""
        return self._word_repo.check_custom_word(wid, enabled)

    def get_custom_words(self, wid=None, gid=None, enabled=None):
        """查询自定义识别词"""
        return self._word_repo.get_custom_words(wid, gid, enabled)

    def is_custom_words_existed(self, replaced=None, front=None, back=None):
        """查询自定义识别词是否存在"""
        return self._word_repo.is_custom_words_existed(replaced, front, back)

    def insert_custom_word_groups(self, title, year, gtype, tmdbid, season_count, note=None):
        """增加自定义识别词组"""
        return self._word_repo.insert_custom_word_groups(title, year, gtype, tmdbid, season_count, note)

    def delete_custom_word_group(self, gid):
        """删除自定义识别词组"""
        return self._word_repo.delete_custom_word_group(gid)

    def get_custom_word_groups(self, gid=None, tmdbid=None, gtype=None):
        """查询自定义识别词组"""
        return self._word_repo.get_custom_word_groups(gid, tmdbid, gtype)

    def is_custom_word_group_existed(self, tmdbid=None, gtype=None):
        """查询自定义识别词组是否存在"""
        return self._word_repo.is_custom_word_group_existed(tmdbid, gtype)

    # ==================== Directory Sync ====================

    def insert_config_sync_path(self, source, dest, unknown, mode, compatibility, rename, enabled, note=None):
        """增加目录同步"""
        return self._sync_repo.insert_config_sync_path(source, dest, unknown, mode, compatibility, rename, enabled, note)

    def delete_config_sync_path(self, sid):
        """删除目录同步"""
        return self._sync_repo.delete_config_sync_path(sid)

    def get_config_sync_paths(self, sid=None):
        """查询目录同步"""
        return self._sync_repo.get_config_sync_paths(sid)

    def check_config_sync_paths(self, sid=None, compatibility=None, rename=None, enabled=None):
        """设置目录同步状态"""
        return self._sync_repo.check_config_sync_paths(sid, compatibility, rename, enabled)

    # ==================== Download Settings ====================

    def delete_download_setting(self, sid):
        """删除下载设置"""
        return self._download_repo.delete_download_setting(sid)

    def get_download_setting(self, sid=None):
        """查询下载设置"""
        return self._download_repo.get_download_setting(sid)

    def update_download_setting(self, sid, name, category, tags, is_paused, upload_limit, download_limit,
                                ratio_limit, seeding_time_limit, downloader):
        """设置下载设置"""
        return self._download_repo.update_download_setting(sid, name, category, tags, is_paused, upload_limit,
                                                           download_limit, ratio_limit, seeding_time_limit, downloader)

    # ==================== Message Client ====================

    def delete_message_client(self, cid):
        """删除消息服务器"""
        return self._config_repo.delete_message_client(cid)

    def get_message_client(self, cid=None):
        """查询消息服务器"""
        return self._config_repo.get_message_client(cid)

    def insert_message_client(self, name, ctype, config, switchs: list, interactive, enabled, note='', templates=None):
        """设置消息服务器"""
        return self._config_repo.insert_message_client(name, ctype, config, switchs, interactive, enabled, note, templates)

    def check_message_client(self, cid=None, interactive=None, enabled=None, ctype=None):
        """设置目录同步状态"""
        return self._config_repo.check_message_client(cid, interactive, enabled, ctype)

    # ==================== Torrent Remove Task ====================

    def delete_torrent_remove_task(self, tid):
        """删除自动删种策略"""
        return self._config_repo.delete_torrent_remove_task(tid)

    def get_torrent_remove_tasks(self, tid=None):
        """查询自动删种策略"""
        return self._config_repo.get_torrent_remove_tasks(tid)

    def insert_torrent_remove_task(self, name, action, interval, enabled, samedata, onlynastool, downloader, config: dict, note=None):
        """设置自动删种策略"""
        return self._config_repo.insert_torrent_remove_task(name, action, interval, enabled, samedata, onlynastool, downloader, config, note)

    # ==================== Downloader ====================

    def update_downloader(self, did, name, enabled, dtype, transfer, only_nastool, match_path, rmt_mode, config, download_dir):
        """更新下载器"""
        return self._config_repo.update_downloader(did, name, enabled, dtype, transfer, only_nastool, match_path, rmt_mode, config, download_dir)

    def delete_downloader(self, did):
        """删除下载器"""
        return self._config_repo.delete_downloader(did)

    def check_downloader(self, did=None, transfer=None, only_nastool=None, enabled=None, match_path=None):
        """设置下载器状态"""
        return self._config_repo.check_downloader(did, transfer, only_nastool, enabled, match_path)

    def get_downloaders(self):
        """查询下载器"""
        return self._config_repo.get_downloaders()

    # ==================== Indexer Statistics ====================

    def insert_indexer_statistics(self, indexer, itype, seconds, result):
        """插入索引器统计"""
        return self._download_repo.insert_indexer_statistics(indexer, itype, seconds, result)

    def delete_all_indexer_statistics(self):
        """删除所有搜索的记录"""
        return self._download_repo.delete_all_indexer_statistics()

    def get_indexer_statistics(self, client_id):
        """查询索引器统计"""
        return self._download_repo.get_indexer_statistics(client_id)

    # ==================== Plugin History ====================

    def insert_plugin_history(self, plugin_id, key, value):
        """新增插件运行记录"""
        return self._plugin_repo.insert_plugin_history(plugin_id, key, value)

    def get_plugin_history(self, plugin_id, key):
        """查询插件运行记录"""
        return self._plugin_repo.get_plugin_history(plugin_id, key)

    def update_plugin_history(self, plugin_id, key, value):
        """更新插件运行记录"""
        return self._plugin_repo.update_plugin_history(plugin_id, key, value)

    def delete_plugin_history(self, plugin_id, key):
        """删除插件运行记录"""
        return self._plugin_repo.delete_plugin_history(plugin_id, key)

    # ==================== TMDB Blacklist ====================

    def is_tmdb_blacklisted(self, tmdb_id, media_type=None):
        """检查TMDB ID是否在黑名单中"""
        return self._plugin_repo.is_tmdb_blacklisted(tmdb_id, media_type)

    def get_tmdb_blacklist(self):
        """获取所有TMDB黑名单记录"""
        return self._plugin_repo.get_tmdb_blacklist()

    def insert_tmdb_blacklist(self, tmdb_id, title=None, year=None, media_type=None, poster_path=None, backdrop_path=None, note=None):
        """添加到TMDB黑名单"""
        return self._plugin_repo.insert_tmdb_blacklist(tmdb_id, title, year, media_type, poster_path, backdrop_path, note)

    def delete_tmdb_blacklist(self, tmdb_id, media_type=None):
        """从TMDB黑名单删除"""
        return self._plugin_repo.delete_tmdb_blacklist(tmdb_id, media_type)

    def clear_tmdb_blacklist(self):
        """清空所有TMDB黑名单记录"""
        return self._plugin_repo.clear_tmdb_blacklist()

    # ==================== SQL Operations ====================

    def excute(self, sql):
        """执行SQL语句"""
        return self._config_repo.excute(sql)

    def drop_table(self, table_name):
        """删除表"""
        return self._config_repo.drop_table(table_name)
