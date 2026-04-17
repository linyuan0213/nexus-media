from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from web.core.action_utils import mediainfo_dict, get_media_exists_info
import json
import os.path
import re
import time
from math import floor
import cn2an
import log
from app.conf import SystemConfig, ModuleConf
from app.downloader import Downloader
from app.filetransfer import FileTransfer
from app.helper import ThreadHelper
from app.media import Media, Bangumi, DouBan, Scraper
from app.media.meta import MetaInfo, MetaBase
from app.mediaserver import MediaServer
from app.plugins import EventManager
from app.searcher import Searcher
from app.subscribe import Subscribe
from app.utils import StringUtils, SystemUtils, ExceptionUtils
from app.utils.types import MediaType, MovieTypes, EventType, SystemConfigKey
from config import Config
from web.backend.web_utils import WebUtils
from web.cache import cache
from web.controllers.sync import re_identification

media_bp = Blueprint("media", __name__, url_prefix="/api/web/media")

@media_bp.route('/download_subtitle', methods=['POST'])
@any_auth
@parse_json_data
def _download_subtitle(data):
        """
        从配置的字幕服务下载单个文件的字幕
        """
        path = data.get("path")
        name = data.get("name")
        media = Media().get_media_info(title=name)
        if not media or not media.tmdb_info:
            return fail(code=-1, msg=f"{name} 无法从TMDB查询到媒体信息")
        if not media.imdb_id:
            media.set_tmdb_info(Media().get_tmdb_info(mtype=media.type,
                                                      tmdbid=media.tmdb_id))
        # 触发字幕下载事件
        EventManager().send_event(EventType.SubtitleDownload, {
            "media_info": media.to_dict(),
            "file": os.path.splitext(path)[0],
            "file_ext": os.path.splitext(name)[-1],
            "bluray": False
        })
        return success(msg="字幕下载任务已提交，正在后台运行。")

@media_bp.route('/get_season_episodes', methods=['POST'])
@any_auth
@parse_json_data
def _get_season_episodes(data):
        """
        查询TMDB剧集情况
        """
        tmdbid = data.get("tmdbid")
        title = data.get("title")
        year = data.get("year")
        season = 1 if data.get("season") is None else data.get("season")
        if not tmdbid:
            return fail(msg="TMDBID为空")
        episodes = Media().get_tmdb_season_episodes(tmdbid=tmdbid,
                                                    season=season)
        MediaServerHandler = MediaServer()
        for episode in episodes:
            episode.update({
                "state": True if MediaServerHandler.check_item_exists(
                    mtype=MediaType.TV,
                    title=title,
                    year=year,
                    tmdbid=tmdbid,
                    season=season,
                    episode=episode.get("episode_number")) else False
            })
        return success(episodes=episodes)

@media_bp.route('/get_tvseason_list', methods=['POST'])
@any_auth
@parse_json_data
def _get_tvseason_list(data):
        """
        获取剧集季列表
        """
        tmdbid = data.get("tmdbid")
        title = data.get("title")
        if title:
            title_season = MetaInfo(title=title).begin_season
        else:
            title_season = None
        if not str(tmdbid).isdigit():
            media_info = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV,
                                                        mediaid=tmdbid)
            season_infos = Media().get_tmdb_tv_seasons(media_info.tmdb_info)
        else:
            season_infos = Media().get_tmdb_tv_seasons_byid(tmdbid=tmdbid)
        if title_season:
            seasons = [
                {
                    "text": "第%s季" % title_season,
                    "num": title_season
                }
            ]
        else:
            seasons = [
                {
                    "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                    "num": season.get("season_number")
                }
                for season in season_infos
            ]
        return success(seasons=seasons)

@media_bp.route('/media_info', methods=['POST'])
@any_auth
@parse_json_data
def _media_info(data):
        """
        查询媒体信息
        """
        mediaid = data.get("id")
        mtype = data.get("type")
        title = data.get("title")
        year = data.get("year")
        page = data.get("page")
        rssid = data.get("rssid")
        seasons = []
        link_url = ""
        vote_average = 0
        poster_path = ""
        release_date = ""
        overview = ""
        # 类型
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.TV

        # 先取订阅信息
        _subcribe = Subscribe()
        _media = Media()
        rssid_ok = False
        if rssid:
            rssid = str(rssid)
            if media_type == MediaType.MOVIE:
                rssinfo = _subcribe.get_subscribe_movies(rid=rssid)
            else:
                rssinfo = _subcribe.get_subscribe_tvs(rid=rssid)
            if not rssinfo:
                return fail(msg="无法查询到订阅信息", rssid=rssid, type_str=media_type.value)
            overview = rssinfo[rssid].get("overview")
            poster_path = rssinfo[rssid].get("poster")
            title = rssinfo[rssid].get("name")
            vote_average = rssinfo[rssid].get("vote")
            year = rssinfo[rssid].get("year")
            release_date = rssinfo[rssid].get("release_date")
            link_url = _media.get_detail_url(mtype=media_type,
                                             tmdbid=rssinfo[rssid].get("tmdbid"))
            if overview and poster_path:
                rssid_ok = True

        # 订阅信息不足
        if not rssid_ok:
            if mediaid:
                media = WebUtils.get_mediainfo_from_id(
                    mtype=media_type, mediaid=mediaid)
            else:
                media = _media.get_media_info(
                    title=f"{title} {year}", mtype=media_type)
            if not media or not media.tmdb_info:
                return fail(msg="无法查询到TMDB信息", rssid=rssid, type_str=media_type.value)
            if not mediaid:
                mediaid = media.tmdb_id
            link_url = media.get_detail_url()
            overview = media.overview
            poster_path = media.get_poster_image()
            title = media.title
            vote_average = round(float(media.vote_average or 0), 1)
            year = media.year
            if media_type != MediaType.MOVIE:
                release_date = media.tmdb_info.get('first_air_date')
                seasons = [{
                    "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                    "num": season.get("season_number")} for season in
                    _media.get_tmdb_tv_seasons(tv_info=media.tmdb_info)]
            else:
                release_date = media.tmdb_info.get('release_date')

            # 查订阅信息
            if not rssid:
                rssid = _subcribe.get_subscribe_id(mtype=media_type,
                                                   title=title,
                                                   tmdbid=mediaid)

        # 处理图片URL，转换为代理格式
        if poster_path:
            poster_path = Config().get_proxy_image_url(poster_path)

        return success(type=mtype, type_str=media_type.value, page=page, title=title, vote_average=vote_average, poster_path=poster_path, release_date=release_date, year=year, overview=overview, link_url=link_url, tmdbid=mediaid, rssid=rssid, seasons=seasons)

@media_bp.route('/media_path_scrap', methods=['POST'])
@any_auth
@parse_json_data
def _media_path_scrap(data):
        """
        刮削媒体文件夹或文件
        """
        path = data.get("path")
        if not path:
            return fail(code=-1, msg="请指定刮削路径")
        ThreadHelper().start_thread(Scraper().folder_scraper, (path, None, 'force_all'))
        return success(msg="刮削任务已提交，正在后台运行。")

@media_bp.route('/media_person', methods=['POST'])
@any_auth
@parse_json_data
def _media_person(data):
        """
        根据TMDBID或关键字查询TMDB演员
        """
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        keyword = data.get("keyword")
        if not tmdbid and not keyword:
            return fail(msg="未指定TMDBID或关键字")
        if tmdbid:
            result = Media().get_tmdb_cats(tmdbid=tmdbid, mtype=mtype)
        else:
            result = Media().search_tmdb_person(name=keyword)
        return success(data=result)

@media_bp.route('/media_recommendations', methods=['POST'])
@any_auth
@parse_json_data
def _media_recommendations(data):
        """
        查询TMDB同类推荐媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return fail(msg="未指定TMDBID")
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_recommendations(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_recommendations(tmdbid=tmdbid, page=page)
        return success(data=result)

@media_bp.route('/media_similar', methods=['POST'])
@any_auth
@parse_json_data
def _media_similar(data):
        """
        查询TMDB相似媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return fail(msg="未指定TMDBID")
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_similar(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_similar(tmdbid=tmdbid, page=page)
        return success(data=result)

@media_bp.route('/mediasync_state', methods=['POST'])
@any_auth
@parse_json_data
def _mediasync_state(data):
        """
        获取媒体库同步数据情况
        """
        status = MediaServer().get_mediasync_status()
        if not status:
            return success(text="未同步")
        else:
            return success(text="电影：%s，电视剧：%s，同步时间：%s" %
                                       (status.get("movie_count"),
                                        status.get("tv_count"),
                                        status.get("time")))

@media_bp.route('/movie_calendar_data', methods=['POST'])
@any_auth
@parse_json_data
def _movie_calendar_data(data):
        """
        查询电影上映日期
        """
        tid = data.get("id")
        rssid = data.get("rssid")
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DouBan().get_douban_detail(
                doubanid=doubanid, mtype=MediaType.MOVIE)
            if not douban_info:
                return fail(msg="无法查询到豆瓣信息")
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "无"
            release_date = douban_info.get("pubdate")
            if release_date:
                release_date = re.sub(
                    r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return fail(msg="上映日期不正确")
            else:
                return success(type="电影", title=title, start=release_date, id=tid, year=release_date[0:4] if release_date else "", poster=poster_path, vote_average=vote_average, rssid=rssid)
        else:
            if tid:
                tmdb_info = Media().get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tid)
            else:
                return fail(msg="没有TMDBID信息")
            if not tmdb_info:
                return fail(msg="无法查询到TMDB信息")
                poster_path = Config().get_tmdbimage_url(tmdb_info.get('poster_path')) \
                if tmdb_info.get('poster_path') else ""
            title = tmdb_info.get('title')
            vote_average = tmdb_info.get("vote_average")
            release_date = tmdb_info.get('release_date')
            if not release_date:
                return fail(msg="上映日期不正确")
            else:
                return success(type="电影", title=title, start=release_date, id=tid, year=release_date[0:4] if release_date else "", poster=poster_path, vote_average=vote_average, rssid=rssid)

@media_bp.route('/name_test', methods=['POST'])
@any_auth
@parse_json_data
def _name_test(data):
        """
        名称识别测试
        """
        name = data.get("name")
        subtitle = data.get("subtitle")
        if not name:
            return fail(code=-1)
        media_info = Media().get_media_info(title=name, subtitle=subtitle)
        if not media_info:
            return success(data={"name": "无法识别"})
        return success(data=mediainfo_dict(media_info))

@media_bp.route('/person_medias', methods=['POST'])
@any_auth
@parse_json_data
def _person_medias(data):
        """
        查询演员参演作品
        """
        personid = data.get("personid")
        page = data.get("page") or 1
        if data.get("type"):
            mtype = MediaType.MOVIE if data.get(
                "type") in MovieTypes else MediaType.TV
        else:
            mtype = None
        if not personid:
            return fail(msg="未指定演员ID")
        return success(data=Media().get_person_medias(personid=personid,
                                                             mtype=mtype,
                                                             page=page))

@media_bp.route('/save_user_script', methods=['POST'])
@any_auth
@parse_json_data
def _save_user_script(data):
        """
        保存用户自定义脚本
        """
        script = data.get("javascript") or ""
        css = data.get("css") or ""
        SystemConfig().set(key=SystemConfigKey.CustomScript,
                           value={
                               "css": css,
                               "javascript": script
                           })
        return success(msg="保存成功")

@media_bp.route('/start_mediasync', methods=['POST'])
@any_auth
@parse_json_data
def _start_mediasync(data):
        """
        开始媒体库同步
        """
        cache.delete("index")
        librarys = data.get("librarys") or []
        SystemConfig().set(key=SystemConfigKey.SyncLibrary, value=librarys)
        ThreadHelper().start_thread(MediaServer().sync_mediaserver, ())
        return success()

@media_bp.route('/tv_calendar_data', methods=['POST'])
@any_auth
@parse_json_data
def _tv_calendar_data(data):
        """
        查询电视剧上映日期
        """
        tid = data.get("id")
        season = data.get("season")
        name = data.get("name")
        rssid = data.get("rssid")
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DouBan().get_douban_detail(doubanid=doubanid, mtype=MediaType.TV)
            if not douban_info:
                return fail(msg="无法查询到豆瓣信息")
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "无"
            release_date = re.sub(r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return fail(msg="上映日期不正确")
            else:
                return success(events=[{
                        "type": "电视剧",
                        "title": title,
                        "start": release_date,
                        "id": tid,
                        "year": release_date[0:4] if release_date else "",
                        "poster": poster_path,
                        "vote_average": vote_average,
                        "rssid": rssid
                    }])
        else:
            if tid:
                tmdb_info = Media().get_tmdb_tv_season_detail(tmdbid=tid, season=season)
            else:
                return fail(msg="没有TMDBID信息")
            if not tmdb_info:
                return fail(msg="无法查询到TMDB信息")
            episode_events = []
            air_date = tmdb_info.get("air_date")
            if not tmdb_info.get("poster_path"):
                tv_tmdb_info = Media().get_tmdb_info(mtype=MediaType.TV, tmdbid=tid)
                if tv_tmdb_info:
                    poster_path = Config().get_tmdbimage_url(tv_tmdb_info.get('poster_path'))
                else:
                    poster_path = ""
            else:
                poster_path = Config().get_tmdbimage_url(tmdb_info.get('poster_path'))
            year = air_date[0:4] if air_date else ""
            for episode in tmdb_info.get("episodes"):
                episode_events.append({
                    "type": "剧集",
                    "title": "%s 第%s季第%s集" % (
                        name,
                        season,
                        episode.get("episode_number")
                    ) if season != 1 else "%s 第%s集" % (
                        name,
                        episode.get("episode_number")
                    ),
                    "start": episode.get("air_date"),
                    "id": tid,
                    "year": year,
                    "poster": poster_path,
                    "vote_average": episode.get("vote_average") or "无",
                    "rssid": rssid
                })
            return success(events=episode_events)

@media_bp.route('/clear_history', methods=['POST'])
@any_auth
@parse_json_data
def clear_history(data):
        """
        删除识别记录
        """
        _filetransfer = FileTransfer()
        # 删除记录
        _filetransfer.delete_transfer()
        # 删除该识别记录对应的转移记录
        _filetransfer.truncate_transfer_blacklist()
        return success()

@media_bp.route('/get_category_config', methods=['POST'])
@any_auth
@parse_json_data
def get_category_config(data):
        """
        获取二级分类配置
        """
        category_name = data.get("category_name")
        if not category_name:
            return fail(msg="请输入二级分类策略名称")
        if category_name == "config":
            return fail(msg="非法二级分类策略名称")
        category_path = os.path.join(
            Config().get_config_path(), f"{category_name}.yaml")
        if not os.path.exists(category_path):
            return fail(msg="请保存生成配置文件")
        # 读取category配置文件数据
        with open(category_path, "r", encoding="utf-8") as f:
            category_text = f.read()
        return success(text=category_text)

@media_bp.route('/get_downloaded', methods=['POST'])
@any_auth
@parse_json_data
def get_downloaded(data):
        page = data.get("page")
        Items = Downloader().get_download_history(page=page)
        if Items:
            return success(Items=[{
                'id': item.TMDBID,
                'orgid': item.TMDBID,
                'tmdbid': item.TMDBID,
                'title': item.TITLE,
                'type': 'MOV' if item.TYPE == "电影" else "TV",
                'media_type': item.TYPE,
                'year': item.YEAR,
                'vote': item.VOTE,
                'image': item.POSTER,
                'overview': item.TORRENT,
                "date": item.DATE,
                "site": item.SITE
            } for item in Items])
        else:
            return success(Items=[])

@media_bp.route('/get_library_mediacount', methods=['POST'])
@any_auth
@parse_json_data
def get_library_mediacount(data):
        """
        查询媒体库统计数据
        """
        MediaServerClient = MediaServer()
        media_counts = MediaServerClient.get_medias_count()
        UserCount = MediaServerClient.get_user_count()
        if media_counts:
            return success(Movie="{:,}".format(media_counts.get('MovieCount')), Series="{:,}".format(media_counts.get('SeriesCount')), Episodes="{:,}".format(media_counts.get('EpisodeCount')) if media_counts.get(
                    'EpisodeCount') else "", Music="{:,}".format(media_counts.get('SongCount')), User=UserCount)
        else:
            return fail(code=-1, msg="媒体库服务器连接失败")

@media_bp.route('/get_library_playhistory', methods=['POST'])
@any_auth
@parse_json_data
def get_library_playhistory(data):
        """
        查询媒体库播放记录
        """
        return success(result=MediaServer().get_activity_log(30))

@media_bp.route('/get_library_spacesize', methods=['POST'])
@any_auth
@parse_json_data
def get_library_spacesize(data):
        """
        查询媒体库存储空间
        """
        # 磁盘空间
        UsedSapce = 0
        UsedPercent = 0
        media = Config().get_config('media')
        # 电影目录
        movie_paths = media.get('movie_path')
        if not isinstance(movie_paths, list):
            movie_paths = [movie_paths]
        # 电视目录
        tv_paths = media.get('tv_path')
        if not isinstance(tv_paths, list):
            tv_paths = [tv_paths]
        # 动漫目录
        anime_paths = media.get('anime_path')
        if not isinstance(anime_paths, list):
            anime_paths = [anime_paths]
        # 总空间、剩余空间
        TotalSpace, FreeSpace = SystemUtils.calculate_space_usage(
            movie_paths + tv_paths + anime_paths)
        if TotalSpace:
            # 已使用空间
            UsedSapce = TotalSpace - FreeSpace
            # 百分比格式化
            UsedPercent = "%0.1f" % ((UsedSapce / TotalSpace) * 100)
            # 总剩余空间 格式化
            if FreeSpace > 1024:
                FreeSpace = "{:,} TB".format(round(FreeSpace / 1024, 2))
            else:
                FreeSpace = "{:,} GB".format(round(FreeSpace, 2))
            # 总使用空间 格式化
            if UsedSapce > 1024:
                UsedSapce = "{:,} TB".format(round(UsedSapce / 1024, 2))
            else:
                UsedSapce = "{:,} GB".format(round(UsedSapce, 2))
            # 总空间 格式化
            if TotalSpace > 1024:
                TotalSpace = "{:,} TB".format(round(TotalSpace / 1024, 2))
            else:
                TotalSpace = "{:,} GB".format(round(TotalSpace, 2))

        return success(UsedPercent=UsedPercent, FreeSpace=FreeSpace, UsedSapce=UsedSapce, TotalSpace=TotalSpace)

@media_bp.route('/get_recommend', methods=['POST'])
@any_auth
@parse_json_data
def get_recommend(data):
        Type = data.get("type")
        SubType = data.get("subtype")
        CurrentPage = data.get("page")
        if not CurrentPage:
            CurrentPage = 1
        else:
            CurrentPage = int(CurrentPage)

        res_list = []
        if Type in ['MOV', 'TV', 'ALL']:
            if SubType == "hm":
                # TMDB热门电影
                res_list = Media().get_tmdb_hot_movies(CurrentPage)
            elif SubType == "ht":
                # TMDB热门电视剧
                res_list = Media().get_tmdb_hot_tvs(CurrentPage)
            elif SubType == "nm":
                # TMDB最新电影
                res_list = Media().get_tmdb_new_movies(CurrentPage)
            elif SubType == "nt":
                # TMDB最新电视剧
                res_list = Media().get_tmdb_new_tvs(CurrentPage)
            elif SubType == "dbom":
                # 豆瓣正在上映
                res_list = DouBan().get_douban_online_movie(CurrentPage)
            elif SubType == "dbhm":
                # 豆瓣热门电影
                res_list = DouBan().get_douban_hot_movie(CurrentPage)
            elif SubType == "dbht":
                # 豆瓣热门电视剧
                res_list = DouBan().get_douban_hot_tv(CurrentPage)
            elif SubType == "dbdh":
                # 豆瓣热门动画
                res_list = DouBan().get_douban_hot_anime(CurrentPage)
            elif SubType == "dbnm":
                # 豆瓣最新电影
                res_list = DouBan().get_douban_new_movie(CurrentPage)
            elif SubType == "dbtop":
                # 豆瓣TOP250电影
                res_list = DouBan().get_douban_top250_movie(CurrentPage)
            elif SubType == "dbzy":
                # 豆瓣热门综艺
                res_list = DouBan().get_douban_hot_show(CurrentPage)
            elif SubType == "dbct":
                # 华语口碑剧集榜
                res_list = DouBan().get_douban_chinese_weekly_tv(CurrentPage)
            elif SubType == "dbgt":
                # 全球口碑剧集榜
                res_list = DouBan().get_douban_weekly_tv_global(CurrentPage)
            elif SubType == "sim":
                # 相似推荐
                TmdbId = data.get("tmdbid")
                res_list = _media_similar({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "more":
                # 更多推荐
                TmdbId = data.get("tmdbid")
                res_list = _media_recommendations({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "person":
                # 人物作品
                PersonId = data.get("personid")
                res_list = _person_medias({
                    "personid": PersonId,
                    "type": None if Type == 'ALL' else Type,
                    "page": CurrentPage
                }).get("data")
            elif SubType == "bangumi":
                # Bangumi每日放送
                Week = data.get("week")
                res_list = Bangumi().get_bangumi_calendar(page=CurrentPage, week=Week)
        elif Type == "SEARCH":
            # 搜索词条
            Keyword = data.get("keyword")
            Source = data.get("source")
            medias = WebUtils.search_media_infos(
                keyword=Keyword, source=Source, page=CurrentPage)
            res_list = [media.to_dict() for media in medias]
        elif Type == "DOWNLOADED":
            # 近期下载
            res_list = get_downloaded({
                "page": CurrentPage
            }).get("Items")
        elif Type == "TRENDING":
            # TMDB流行趋势
            res_list = Media().get_tmdb_trending_all_week(page=CurrentPage)
        elif Type == "DISCOVER":
            # TMDB发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 过滤参数 with_genres with_original_language
            params = data.get("params") or {}

            res_list = Media().get_tmdb_discover(mtype=mtype, page=CurrentPage, params=params)
        elif Type == "DOUBANTAG":
            # 豆瓣发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 参数
            params = data.get("params") or {}
            # 排序
            sort = params.get("sort") or "R"
            # 选中的分类
            tags = params.get("tags") or ""
            # 过滤参数
            res_list = DouBan().get_douban_disover(mtype=mtype,
                                                   sort=sort,
                                                   tags=tags,
                                                   page=CurrentPage)

        # 补充存在与订阅状态
        for res in res_list:
            fav, rssid, item_url = get_media_exists_info(mtype=res.get("type"),
                                                              title=res.get(
                                                                  "title"),
                                                              year=res.get(
                                                                  "year"),
                                                              mediaid=res.get("id"))
            res.update({
                'fav': fav,
                'rssid': rssid
            })
        return success(Items=res_list)

@media_bp.route('/get_search_result', methods=['POST'])
@any_auth
@parse_json_data
def get_search_result(data):
        """
        查询所有搜索结果
        """
        SearchResults = {}
        res = Searcher().get_search_results()
        total = len(res)
        for item in res:
            # 质量(来源、效果)、分辨率
            if item.RES_TYPE:
                try:
                    res_mix = json.loads(item.RES_TYPE)
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
                respix = res_mix.get("respix") or ""
                video_encode = res_mix.get("video_encode") or ""
                restype = res_mix.get("restype") or ""
                reseffect = res_mix.get("reseffect") or ""
            else:
                restype = ""
                respix = ""
                reseffect = ""
                video_encode = ""
            # 分组标识 (来源，分辨率)
            group_key = re.sub(r"[-.\s@|]", "", f"{respix}_{restype}").lower()
            # 分组信息
            group_info = {
                "respix": respix,
                "restype": restype,
            }
            # 种子唯一标识 （大小，质量(来源、效果)，制作组组成）
            unique_key = re.sub(r"[-.\s@|]", "",
                                f"{respix}_{restype}_{video_encode}_{reseffect}_{item.SIZE}_{item.OTHERINFO}").lower()
            # 标识信息
            unique_info = {
                "video_encode": video_encode,
                "size": StringUtils.str_filesize(item.SIZE),
                "reseffect": reseffect,
                "releasegroup": item.OTHERINFO
            }
            # 结果
            title_string = f"{item.TITLE}"
            if item.YEAR:
                title_string = f"{title_string} ({item.YEAR})"
            # 电视剧季集标识
            mtype = item.TYPE or ""
            SE_key = item.ES_STRING if item.ES_STRING and mtype != "MOV" else "MOV"
            media_type = {"MOV": "电影", "TV": "电视剧", "ANI": "动漫"}.get(mtype)
            # 只需要部分种子标签
            labels = [label for label in str(item.NOTE).split("|")
                      if label in ["官方", "官组", "中字", "国语", "粤语", "国配", "特效", "特效字幕"]]
            # 种子信息
            torrent_item = {
                "id": item.ID,
                "seeders": item.SEEDERS,
                "enclosure": item.ENCLOSURE,
                "site": item.SITE,
                "torrent_name": item.TORRENT_NAME,
                "description": item.DESCRIPTION,
                "pageurl": item.PAGEURL,
                "uploadvalue": item.UPLOAD_VOLUME_FACTOR,
                "downloadvalue": item.DOWNLOAD_VOLUME_FACTOR,
                "size": StringUtils.str_filesize(item.SIZE),
                "respix": respix,
                "restype": restype,
                "reseffect": reseffect,
                "releasegroup": item.OTHERINFO,
                "video_encode": video_encode,
                "labels": labels
            }
            # 促销
            free_item = {
                "value": f"{item.UPLOAD_VOLUME_FACTOR} {item.DOWNLOAD_VOLUME_FACTOR}",
                "name": MetaBase.get_free_string(item.UPLOAD_VOLUME_FACTOR, item.DOWNLOAD_VOLUME_FACTOR)
            }
            # 制作组、字幕组
            if item.OTHERINFO is None:
                releasegroup = "未知"
            else:
                releasegroup = item.OTHERINFO
            # 季
            filter_season = SE_key.split()[0] if SE_key and SE_key not in [
                "MOV", "TV"] else None
            # 合并搜索结果
            if SearchResults.get(title_string):
                # 种子列表
                result_item = SearchResults[title_string]
                torrent_dict = SearchResults[title_string].get("torrent_dict")
                SE_dict = torrent_dict.get(SE_key)
                if SE_dict:
                    group = SE_dict.get(group_key)
                    if group:
                        unique = group.get("group_torrents").get(unique_key)
                        if unique:
                            unique["torrent_list"].append(torrent_item)
                            group["group_total"] += 1
                        else:
                            group["group_total"] += 1
                            group.get("group_torrents")[unique_key] = {
                                "unique_info": unique_info,
                                "torrent_list": [torrent_item]
                            }
                    else:
                        SE_dict[group_key] = {
                            "group_info": group_info,
                            "group_total": 1,
                            "group_torrents": {
                                unique_key: {
                                    "unique_info": unique_info,
                                    "torrent_list": [torrent_item]
                                }
                            }
                        }
                else:
                    torrent_dict[SE_key] = {
                        group_key: {
                            "group_info": group_info,
                            "group_total": 1,
                            "group_torrents": {
                                unique_key: {
                                    "unique_info": unique_info,
                                    "torrent_list": [torrent_item]
                                }
                            }
                        }
                    }
                # 过滤条件
                torrent_filter = dict(result_item.get("filter"))
                if free_item not in torrent_filter.get("free"):
                    torrent_filter["free"].append(free_item)
                if releasegroup not in torrent_filter.get("releasegroup"):
                    torrent_filter["releasegroup"].append(releasegroup)
                if item.SITE not in torrent_filter.get("site"):
                    torrent_filter["site"].append(item.SITE)
                if video_encode \
                        and video_encode not in torrent_filter.get("video"):
                    torrent_filter["video"].append(video_encode)
                if filter_season \
                        and filter_season not in torrent_filter.get("season"):
                    torrent_filter["season"].append(filter_season)
            else:
                fav, rssid = 0, None
                # 存在标志
                if item.TMDBID:
                    fav, rssid, item_url = get_media_exists_info(
                        mtype=mtype,
                        title=item.TITLE,
                        year=item.YEAR,
                        mediaid=item.TMDBID)

                SearchResults[title_string] = {
                    "key": item.ID,
                    "title": item.TITLE,
                    "year": item.YEAR,
                    "type_key": mtype,
                    "image": item.IMAGE,
                    "type": media_type,
                    "vote": item.VOTE,
                    "tmdbid": item.TMDBID,
                    "backdrop": item.IMAGE,
                    "poster": item.POSTER,
                    "overview": item.OVERVIEW,
                    "fav": fav,
                    "rssid": rssid,
                    "torrent_dict": {
                        SE_key: {
                            group_key: {
                                "group_info": group_info,
                                "group_total": 1,
                                "group_torrents": {
                                    unique_key: {
                                        "unique_info": unique_info,
                                        "torrent_list": [torrent_item]
                                    }
                                }
                            }
                        }
                    },
                    "filter": {
                        "site": [item.SITE],
                        "free": [free_item],
                        "releasegroup": [releasegroup],
                        "video": [video_encode] if video_encode else [],
                        "season": [filter_season] if filter_season else []
                    }
                }

        # 提升整季的顺序到顶层
        def se_sort(k):
            k = re.sub(r" +|(?<=s\d)\D*?(?=e)|(?<=s\d\d)\D*?(?=e)",
                       " ", k[0], flags=re.I).split()
            return (k[0], k[1]) if len(k) > 1 else ("Z" + k[0], "ZZZ")

        # 开始排序季集顺序
        for title, item in SearchResults.items():
            # 排序筛选器 季
            item["filter"]["season"].sort(reverse=True)
            # 排序筛选器 制作组、字幕组.  将未知放到最后
            item["filter"]["releasegroup"] = sorted(
                item["filter"]["releasegroup"], key=lambda x: (x == "未知", x))
            # 排序种子列 集
            item["torrent_dict"] = sorted(item["torrent_dict"].items(),
                                          key=se_sort,
                                          reverse=True)
        return success(total=total, result=SearchResults)

@media_bp.route('/get_transfer_history', methods=['POST'])
@any_auth
@parse_json_data
def get_transfer_history(data):
        """
        查询媒体整理历史记录
        """
        PageNum = data.get("pagenum")
        if not PageNum:
            PageNum = 30
        SearchStr = data.get("keyword")
        CurrentPage = data.get("page")
        if not CurrentPage:
            CurrentPage = 1
        else:
            CurrentPage = int(CurrentPage)
        totalCount, historys = FileTransfer().get_transfer_history(
            SearchStr, CurrentPage, PageNum)
        historys_list = []
        for history in historys:
            history = history.as_dict()
            sync_mode = history.get("MODE")
            rmt_mode = ModuleConf.get_dictenum_key(
                ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            history.update({
                "SYNC_MODE": sync_mode,
                "RMT_MODE": rmt_mode
            })
            historys_list.append(history)
        TotalPage = floor(totalCount / PageNum) + 1

        return success(total=totalCount, result=historys_list, totalPage=TotalPage, pageNum=PageNum, currentPage=CurrentPage)

@media_bp.route('/get_transfer_statistics', methods=['POST'])
@any_auth
@parse_json_data
def get_transfer_statistics(data):
        """
        查询转移历史统计数据
        """
        Labels = []
        MovieNums = []
        TvNums = []
        AnimeNums = []
        for statistic in FileTransfer().get_transfer_statistics(90):
            if not statistic[2]:
                continue
            if statistic[1] not in Labels:
                Labels.append(statistic[1])
            if statistic[0] == "电影":
                MovieNums.append(statistic[2])
                TvNums.append(0)
                AnimeNums.append(0)
            elif statistic[0] == "电视剧":
                TvNums.append(statistic[2])
                MovieNums.append(0)
                AnimeNums.append(0)
            else:
                AnimeNums.append(statistic[2])
                MovieNums.append(0)
                TvNums.append(0)
        return success(Labels=Labels, MovieNums=MovieNums, TvNums=TvNums, AnimeNums=AnimeNums)

@media_bp.route('/get_unknown_list', methods=['POST'])
@any_auth
@parse_json_data
def get_unknown_list(data):
        """
        查询所有未识别记录
        """
        Items = []
        Records = FileTransfer().get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES,
                                                   sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID,
                "path": path,
                "to": path_to,
                "name": path,
                "sync_mode": sync_mode,
                "rmt_mode": rmt_mode,
            })

        return success(items=Items)

@media_bp.route('/get_unknown_list_by_page', methods=['POST'])
@any_auth
@parse_json_data
def get_unknown_list_by_page(data):
        """
        查询所有未识别记录
        """
        PageNum = data.get("pagenum")
        if not PageNum:
            PageNum = 30
        SearchStr = data.get("keyword")
        CurrentPage = data.get("page")
        if not CurrentPage:
            CurrentPage = 1
        else:
            CurrentPage = int(CurrentPage)
        totalCount, Records = FileTransfer().get_transfer_unknown_paths_by_page(
            SearchStr, CurrentPage, PageNum)
        Items = []
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES,
                                                   sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID,
                "path": path,
                "to": path_to,
                "name": path,
                "sync_mode": sync_mode,
                "rmt_mode": rmt_mode,
            })
        TotalPage = floor(totalCount / PageNum) + 1

        return success(total=totalCount, items=Items, totalPage=TotalPage, pageNum=PageNum, currentPage=CurrentPage)

@media_bp.route('/media_detail', methods=['POST'])
@any_auth
@parse_json_data
def media_detail(data):
        """
        获取媒体详情
        """
        import time
        start_time = time.time()

        # TMDBID 或 DB:豆瓣ID
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return fail(msg="未指定媒体ID")

        log.info(f"【media_detail】开始处理请求: tmdbid={tmdbid}, type={mtype}")

        media_info = WebUtils.get_mediainfo_from_id(
            mtype=mtype, mediaid=tmdbid)

        log.info(f"【media_detail】获取媒体信息完成，耗时: {time.time() - start_time:.2f}s")

        # 检查TMDB信息
        if not media_info or not media_info.tmdb_info:
            return fail(msg="无法查询到TMDB信息")

        # 查询存在及订阅状态
        fav_start = time.time()
        fav, rssid, item_url = get_media_exists_info(mtype=mtype,
                                                          title=media_info.title,
                                                          year=media_info.year,
                                                          mediaid=media_info.tmdb_id)
        log.info(f"【media_detail】获取订阅状态完成，耗时: {time.time() - fav_start:.2f}s")

        MediaHandler = Media()
        MediaServerHandler = MediaServer()

        # 查询季
        seasons_start = time.time()
        seasons = MediaHandler.get_tmdb_tv_seasons(media_info.tmdb_info)
        log.info(
            f"【media_detail】获取季信息完成，耗时: {time.time() - seasons_start:.2f}s")

        # 查询季是否存在
        if seasons:
            check_start = time.time()
            for season in seasons:
                try:
                    exists = MediaServerHandler.check_item_exists(
                        mtype=mtype,
                        title=media_info.title,
                        year=media_info.year,
                        tmdbid=media_info.tmdb_id,
                        season=season.get("season_number"))
                    season.update({"state": True if exists else False})
                except Exception as e:
                    log.error(f"【media_detail】检查季存在状态失败: {str(e)}")
                    season.update({"state": False})
            log.info(
                f"【media_detail】检查季存在状态完成，共{len(seasons)}季，耗时: {time.time() - check_start:.2f}s")
        # 处理图片URL，转换为代理格式
        poster_image = media_info.get_poster_image()
        if poster_image:
            poster_image = Config().get_proxy_image_url(poster_image)

        return success(data={
                "tmdbid": media_info.tmdb_id,
                "douban_id": media_info.douban_id,
                "background": MediaHandler.get_tmdb_backdrops(tmdbinfo=media_info.tmdb_info),
                "image": poster_image,
                "vote": media_info.vote_average,
                "year": media_info.year,
                "title": media_info.title,
                "genres": MediaHandler.get_tmdb_genres_names(tmdbinfo=media_info.tmdb_info),
                "overview": media_info.overview,
                "runtime": StringUtils.str_timehours(media_info.runtime),
                "fact": MediaHandler.get_tmdb_factinfo(media_info),
                "crews": MediaHandler.get_tmdb_crews(tmdbinfo=media_info.tmdb_info, nums=6),
                "actors": MediaHandler.get_tmdb_cats(mtype=mtype, tmdbid=media_info.tmdb_id),
                "link": media_info.get_detail_url(),
                "douban_link": media_info.get_douban_detail_url(),
                "fav": fav,
                "item_url": item_url,
                "rssid": rssid,
                "seasons": seasons
            })

@media_bp.route('/search_media_infos', methods=['POST'])
@any_auth
@parse_json_data
def search_media_infos(data):
        """
        根据关键字搜索相似词条
        """
        SearchWord = data.get("keyword")
        if not SearchWord:
            return []
        SearchSourceType = data.get("searchtype")
        medias = WebUtils.search_media_infos(keyword=SearchWord,
                                             source=SearchSourceType)

        return success(result=[media.to_dict() for media in medias])

@media_bp.route('/unidentification', methods=['POST'])
@any_auth
@parse_json_data
def unidentification(data):
        """
        重新识别所有未识别记录
        """
        ItemIds = []
        Records = FileTransfer().get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            ItemIds.append(rec.ID)

        if len(ItemIds) > 0:
            re_identification(
                {"flag": "unidentification", "ids": ItemIds})
        return success()

@media_bp.route('/update_category_config', methods=['POST'])
@any_auth
@parse_json_data
def update_category_config(data):
        """
        保存二级分类配置
        """
        text = data.get("config") or ''
        # 保存配置
        category_path = Config().category_path
        if category_path:
            with open(category_path, "w", encoding="utf-8") as f:
                f.write(text)
        return success(msg="保存成功")
