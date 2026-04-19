from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.downloader import Downloader
from app.searcher import Searcher
from app.utils.types import MediaType, MovieTypes
from app.services.media_service import (
    MediaInfoService,
    MediaRecommendationService,
    SearchResultService,
    MediaLibraryService,
    TransferHistoryService,
    MediaFileService,
)

media_bp = Blueprint("media", __name__, url_prefix="/api/web/media")


@media_bp.route('/download_subtitle', methods=['POST'])
@any_auth
@parse_json_data
def _download_subtitle(data):
    """
    从配置的字幕服务下载单个文件的字幕
    """
    ok, msg = MediaFileService().download_subtitle(
        path=data.get("path"), name=data.get("name"))
    if not ok:
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@media_bp.route('/get_season_episodes', methods=['POST'])
@any_auth
@parse_json_data
def _get_season_episodes(data):
    """
    查询TMDB剧集情况
    """
    tmdbid = data.get("tmdbid")
    if not tmdbid:
        return fail(msg="TMDBID为空")
    season = 1 if data.get("season") is None else data.get("season")
    result = MediaInfoService().get_season_episodes(
        tmdbid=tmdbid, title=data.get("title"),
        year=data.get("year"), season=season)
    return success(episodes=result.episodes)


@media_bp.route('/get_tvseason_list', methods=['POST'])
@any_auth
@parse_json_data
def _get_tvseason_list(data):
    """
    获取剧集季列表
    """
    seasons = MediaInfoService().get_tvseason_list(
        tmdbid=data.get("tmdbid"), title=data.get("title"))
    return success(seasons=seasons)


@media_bp.route('/media_info', methods=['POST'])
@any_auth
@parse_json_data
def _media_info(data):
    """
    查询媒体信息
    """
    result = MediaInfoService().get_media_info_detail(
        mediaid=data.get("id"), mtype=data.get("type"),
        title=data.get("title"), year=data.get("year"),
        page=data.get("page"), rssid=data.get("rssid"))
    return success(
        type=result.type, type_str=result.type_str, page=result.page,
        title=result.title, vote_average=result.vote_average,
        poster_path=result.poster_path, release_date=result.release_date,
        year=result.year, overview=result.overview, link_url=result.link_url,
        tmdbid=result.tmdbid, rssid=result.rssid, seasons=result.seasons)


@media_bp.route('/media_path_scrap', methods=['POST'])
@any_auth
@parse_json_data
def _media_path_scrap(data):
    """
    刮削媒体文件夹或文件
    """
    msg = MediaFileService().scrap_media_path(path=data.get("path"))
    if msg.startswith("请"):
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@media_bp.route('/media_person', methods=['POST'])
@any_auth
@parse_json_data
def _media_person(data):
    """
    根据TMDBID或关键字查询TMDB演员
    """
    tmdbid = data.get("tmdbid")
    keyword = data.get("keyword")
    if not tmdbid and not keyword:
        return fail(msg="未指定TMDBID或关键字")
    result = MediaInfoService().get_media_person(
        tmdbid=tmdbid, mtype_str=data.get("type"), keyword=keyword)
    return success(data=result)


@media_bp.route('/media_recommendations', methods=['POST'])
@any_auth
@parse_json_data
def _media_recommendations(data):
    """
    查询TMDB同类推荐媒体
    """
    tmdbid = data.get("tmdbid")
    if not tmdbid:
        return fail(msg="未指定TMDBID")
    result = MediaInfoService().get_media_recommendations(
        tmdbid=tmdbid, mtype_str=data.get("type"),
        page=data.get("page") or 1)
    return success(data=result)


@media_bp.route('/media_similar', methods=['POST'])
@any_auth
@parse_json_data
def _media_similar(data):
    """
    查询TMDB相似媒体
    """
    tmdbid = data.get("tmdbid")
    if not tmdbid:
        return fail(msg="未指定TMDBID")
    result = MediaInfoService().get_media_similar(
        tmdbid=tmdbid, mtype_str=data.get("type"),
        page=data.get("page") or 1)
    return success(data=result)


@media_bp.route('/mediasync_state', methods=['POST'])
@any_auth
@parse_json_data
def _mediasync_state(data):
    """
    获取媒体库同步数据情况
    """
    text = MediaLibraryService().get_sync_state()
    return success(text=text)


@media_bp.route('/movie_calendar_data', methods=['POST'])
@any_auth
@parse_json_data
def _movie_calendar_data(data):
    """
    查询电影上映日期
    """
    result = MediaInfoService().get_movie_calendar(
        tid=data.get("id"), rssid=data.get("rssid"))
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(**result)


@media_bp.route('/name_test', methods=['POST'])
@any_auth
@parse_json_data
def _name_test(data):
    """
    名称识别测试
    """
    name = data.get("name")
    if not name:
        return fail(code=-1)
    result = MediaInfoService().name_test(name=name, subtitle=data.get("subtitle"))
    return success(data=result)


@media_bp.route('/person_medias', methods=['POST'])
@any_auth
@parse_json_data
def _person_medias(data):
    """
    查询演员参演作品
    """
    personid = data.get("personid")
    if not personid:
        return fail(msg="未指定演员ID")
    result = MediaInfoService().get_person_medias(
        personid=personid, mtype_str=data.get("type"),
        page=data.get("page") or 1)
    return success(data=result)


@media_bp.route('/save_user_script', methods=['POST'])
@any_auth
@parse_json_data
def _save_user_script(data):
    """
    保存用户自定义脚本
    """
    MediaFileService().save_user_script(
        script=data.get("javascript") or "",
        css=data.get("css") or "")
    return success(msg="保存成功")


@media_bp.route('/start_mediasync', methods=['POST'])
@any_auth
@parse_json_data
def _start_mediasync(data):
    """
    开始媒体库同步
    """
    MediaLibraryService().start_sync(librarys=data.get("librarys") or [])
    return success()


@media_bp.route('/tv_calendar_data', methods=['POST'])
@any_auth
@parse_json_data
def _tv_calendar_data(data):
    """
    查询电视剧上映日期
    """
    result = MediaInfoService().get_tv_calendar(
        tid=data.get("id"), season=data.get("season"),
        name=data.get("name"), rssid=data.get("rssid"))
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(events=result)


@media_bp.route('/clear_history', methods=['POST'])
@any_auth
@parse_json_data
def clear_history(data):
    """
    删除识别记录
    """
    TransferHistoryService().clear_history()
    return success()


@media_bp.route('/get_category_config', methods=['POST'])
@any_auth
@parse_json_data
def get_category_config(data):
    """
    获取二级分类配置
    """
    ok, result = MediaFileService().get_category_config(
        category_name=data.get("category_name"))
    if not ok:
        return fail(msg=result)
    return success(text=result)


@media_bp.route('/get_downloaded', methods=['POST'])
@any_auth
@parse_json_data
def get_downloaded(data):
    Items = Downloader().get_download_history(page=data.get("page"))
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
    return success(Items=[])


@media_bp.route('/get_library_mediacount', methods=['POST'])
@any_auth
@parse_json_data
def get_library_mediacount(data):
    """
    查询媒体库统计数据
    """
    result = MediaLibraryService().get_media_count()
    if result:
        return success(**result)
    return fail(code=-1, msg="媒体库服务器连接失败")


@media_bp.route('/get_library_playhistory', methods=['POST'])
@any_auth
@parse_json_data
def get_library_playhistory(data):
    """
    查询媒体库播放记录
    """
    return success(result=MediaLibraryService().get_play_history())


@media_bp.route('/get_library_spacesize', methods=['POST'])
@any_auth
@parse_json_data
def get_library_spacesize(data):
    """
    查询媒体库存储空间
    """
    result = MediaLibraryService().get_space_info()
    return success(
        UsedPercent=result.used_percent,
        FreeSpace=result.free_space,
        UsedSapce=result.used_space,
        TotalSpace=result.total_space)


@media_bp.route('/get_recommend', methods=['POST'])
@any_auth
@parse_json_data
def get_recommend(data):
    res_list = MediaRecommendationService().get_recommend_items(data)
    return success(Items=res_list)


@media_bp.route('/get_search_result', methods=['POST'])
@any_auth
@parse_json_data
def get_search_result(data):
    """
    查询所有搜索结果
    """
    search_results = Searcher().get_search_results()
    result = SearchResultService().group_search_results(search_results)
    return success(total=result.total, result=result.result)


@media_bp.route('/get_transfer_history', methods=['POST'])
@any_auth
@parse_json_data
def get_transfer_history(data):
    """
    查询媒体整理历史记录
    """
    result = TransferHistoryService().get_transfer_history_page(
        search_str=data.get("keyword"),
        page=data.get("page"),
        page_num=data.get("pagenum"))
    return success(
        total=result.total, result=result.result,
        totalPage=result.total_page, pageNum=result.page_num,
        currentPage=result.current_page)


@media_bp.route('/get_transfer_statistics', methods=['POST'])
@any_auth
@parse_json_data
def get_transfer_statistics(data):
    """
    查询转移历史统计数据
    """
    result = TransferHistoryService().get_transfer_statistics(days=90)
    return success(**result)


@media_bp.route('/get_unknown_list', methods=['POST'])
@any_auth
@parse_json_data
def get_unknown_list(data):
    """
    查询所有未识别记录
    """
    items = TransferHistoryService().get_unknown_list()
    return success(items=items)


@media_bp.route('/get_unknown_list_by_page', methods=['POST'])
@any_auth
@parse_json_data
def get_unknown_list_by_page(data):
    """
    分页查询未识别记录
    """
    result = TransferHistoryService().get_unknown_list_by_page(
        search_str=data.get("keyword"),
        page=data.get("page"),
        page_num=data.get("pagenum"))
    return success(
        total=result.total, items=result.items,
        totalPage=result.total_page, pageNum=result.page_num,
        currentPage=result.current_page)


@media_bp.route('/media_detail', methods=['POST'])
@any_auth
@parse_json_data
def media_detail(data):
    """
    获取媒体详情
    """
    tmdbid = data.get("tmdbid")
    mtype = MediaType.MOVIE if data.get("type") in MovieTypes else MediaType.TV
    if not tmdbid:
        return fail(msg="未指定媒体ID")
    result = MediaInfoService().get_media_detail(tmdbid=tmdbid, mtype_str=data.get("type"))
    if not result:
        return fail(msg="无法查询到TMDB信息")
    return success(data=result)


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
    result = MediaInfoService().search_media_infos(
        keyword=SearchWord, source=SearchSourceType, page=1)
    return success(result=result)


@media_bp.route('/unidentification', methods=['POST'])
@any_auth
@parse_json_data
def unidentification(data):
    """
    重新识别所有未识别记录
    """
    count = TransferHistoryService().re_identify_unknown()
    return success()


@media_bp.route('/update_category_config', methods=['POST'])
@any_auth
@parse_json_data
def update_category_config(data):
    """
    保存二级分类配置
    """
    msg = MediaFileService().update_category_config(text=data.get("config") or '')
    return success(msg=msg)
