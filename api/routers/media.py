import urllib.parse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.deps import (
    get_config_service,
    get_downloader_service,
    get_media_config_service,
    get_media_file_service,
    get_media_info_service,
    get_media_library_service,
    get_media_recommendation_service,
    get_search_result_service,
    get_searcher_service,
    get_sync_service,
    get_tmdb_blacklist_service,
    get_transfer_history_service,
    require_any_permission,
    require_permission,
)
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.media_config_service import MediaConfigService
from app.services.media_service import (
    MediaFileService,
    MediaInfoService,
    MediaLibraryService,
    MediaRecommendationService,
    SearchResultService,
    TransferHistoryService,
)
from app.services.search_service import Searcher
from app.utils.response import fail, success
from app.utils.types import MediaType, MovieTypes

router = APIRouter()


# ---------- Request Models ----------


class DownloadSubtitleRequest(BaseModel):
    path: str
    name: str


class GetSeasonEpisodesRequest(BaseModel):
    tmdbid: int
    title: str | None = None
    year: str | None = None
    season: int | None = None


class GetTvSeasonListRequest(BaseModel):
    tmdbid: str | int
    title: str | None = None


class MediaInfoRequest(BaseModel):
    id: str | None = None
    type: str | None = None
    title: str | None = None
    year: str | None = None
    page: str | None = None
    rssid: str | None = None


class MediaPathScrapRequest(BaseModel):
    path: str


class MediaPersonRequest(BaseModel):
    tmdbid: str | None = None
    type: str | None = None
    keyword: str | None = None


class MediaRecommendationsRequest(BaseModel):
    tmdbid: str
    type: str | None = None
    page: int | None = 1


class MediaSimilarRequest(BaseModel):
    tmdbid: str
    type: str | None = None
    page: int | None = 1


class MovieCalendarRequest(BaseModel):
    id: str | None = None
    rssid: str | None = None


class NameTestRequest(BaseModel):
    name: str
    subtitle: str | None = None


class PersonMediasRequest(BaseModel):
    personid: int
    type: str | None = None
    page: int | None = 1


class SaveUserScriptRequest(BaseModel):
    javascript: str | None = None
    css: str | None = None


class StartMediasyncRequest(BaseModel):
    librarys: list[str] | None = None


class TvCalendarRequest(BaseModel):
    id: str | None = None
    season: int | None = None
    name: str | None = None
    rssid: str | None = None


class GetCategoryConfigRequest(BaseModel):
    category_name: str


class GetDownloadedRequest(BaseModel):
    page: int | None = None


class GetTransferHistoryRequest(BaseModel):
    keyword: str | None = None
    page: int | None = None
    pagenum: int | None = None


class GetTransferStatisticsRequest(BaseModel):
    days: int | None = None


class GetUnknownListByPageRequest(BaseModel):
    keyword: str | None = None
    page: int | None = None
    pagenum: int | None = None


class MediaDetailRequest(BaseModel):
    tmdbid: str
    type: str | None = None


class SearchMediaInfosRequest(BaseModel):
    keyword: str
    searchtype: str | None = None


class UpdateCategoryConfigRequest(BaseModel):
    config: str | None = None


class DirListRequest(BaseModel):
    path: str | None = None
    filter: str | None = None


class TmdbBlacklistRequest(BaseModel):
    tmdb_id: str | None = None
    media_type: str | None = None


# ---------- Endpoints ----------


@router.post("/subtitle/download")
def download_subtitle(
    req: DownloadSubtitleRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    ok, msg = svc.download_subtitle(path=req.path, name=req.name)
    if not ok:
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@router.post("/season/episodes")
def get_season_episodes(
    req: GetSeasonEpisodesRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="TMDBID为空")
    season = 1 if req.season is None else req.season
    result = svc.get_season_episodes(tmdbid=req.tmdbid, title=req.title, year=req.year, season=season)
    return success(data=result.episodes)


@router.post("/season/list")
def get_tvseason_list(
    req: GetTvSeasonListRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    seasons = svc.get_tvseason_list(tmdbid=req.tmdbid, title=req.title)
    return success(data=seasons)


@router.post("/info")
def media_info(
    req: MediaInfoRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_media_info_detail(
        mediaid=req.id,
        mtype=req.type,
        title=req.title,
        year=req.year,
        page=req.page,
        rssid=req.rssid,
    )
    return success(
        data={
            "type": result.type,
            "type_str": result.type_str,
            "page": result.page,
            "title": result.title,
            "vote_average": result.vote_average,
            "poster_path": result.poster_path,
            "release_date": result.release_date,
            "year": result.year,
            "overview": result.overview,
            "link_url": result.link_url,
            "tmdbid": result.tmdbid,
            "rssid": result.rssid,
            "seasons": result.seasons,
        }
    )


@router.post("/scrap")
def media_path_scrap(
    req: MediaPathScrapRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.scrap_media_path(path=req.path)
    if msg.startswith("请"):
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@router.post("/person")
def media_person(
    req: MediaPersonRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid and not req.keyword:
        return fail(msg="未指定TMDBID或关键字")
    result = svc.get_media_person(tmdbid=req.tmdbid, mtype_str=req.type, keyword=req.keyword)
    return success(data=result)


@router.post("/recommendations")
def media_recommendations(
    req: MediaRecommendationsRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_recommendations(tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/similar")
def media_similar(
    req: MediaSimilarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_similar(tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/sync/state")
def mediasync_state(
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    text = svc.get_sync_state()
    return success(data=text)


@router.post("/calendar/movie")
def movie_calendar_data(
    req: MovieCalendarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_movie_calendar(tid=req.id, rssid=req.rssid)
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(data=result)


@router.post("/name_test")
def name_test(
    req: NameTestRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.name:
        return fail(code=-1)
    result = svc.name_test(name=req.name, subtitle=req.subtitle)
    return success(data=result)


@router.post("/person/medias")
def person_medias(
    req: PersonMediasRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.personid:
        return fail(msg="未指定演员ID")
    result = svc.get_person_medias(personid=req.personid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/script/save")
def save_user_script(
    req: SaveUserScriptRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    svc.save_user_script(script=req.javascript or "", css=req.css or "")
    return success(msg="保存成功")


@router.post("/sync/start")
def start_mediasync(
    req: StartMediasyncRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    svc.start_sync(librarys=req.librarys or [])
    return success()


@router.post("/calendar/tv")
def tv_calendar_data(
    req: TvCalendarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_tv_calendar(tid=req.id, season=req.season, name=req.name, rssid=req.rssid)
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(data=result)


@router.post("/history/clear")
def clear_history(
    current_user=Depends(require_permission("library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.clear_history()
    return success()


@router.post("/category/config")
def get_category_config(
    req: GetCategoryConfigRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    ok, result = svc.get_category_config(category_name=req.category_name)
    if not ok:
        return fail(msg=result)
    return success(data=result)


@router.post("/library/downloaded")
def get_downloaded(
    req: GetDownloadedRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    Items = svc.get_download_history(page=req.page or 1)
    if Items:
        return success(
            data=[
                {
                    "id": item.TMDBID,
                    "orgid": item.TMDBID,
                    "tmdbid": item.TMDBID,
                    "title": item.TITLE,
                    "type": "MOV" if item.TYPE == "电影" else "TV",
                    "media_type": item.TYPE,
                    "year": item.YEAR,
                    "vote": item.VOTE,
                    "image": item.POSTER,
                    "overview": item.TORRENT,
                    "enclosure": item.ENCLOSURE,
                    "date": item.DATE,
                    "site": item.SITE,
                }
                for item in Items
            ]
        )
    return success(data=[])


@router.post("/library/count")
def get_library_mediacount(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    result = svc.get_media_count()
    if result:
        return success(data=result)
    return fail(code=-1, msg="媒体库服务器连接失败")


@router.post("/library/history")
def get_library_playhistory(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(data=svc.get_play_history())


@router.post("/library/space")
def get_library_spacesize(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    result = svc.get_space_info()
    return success(
        data={
            "UsedPercent": result.used_percent,
            "FreeSpace": result.free_space,
            "UsedSapce": result.used_space,
            "TotalSpace": result.total_space,
        }
    )


@router.post("/library/home")
def get_library_home(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    server_success = False
    media_counts = {}
    try:
        result = svc.get_media_count()
        if result:
            media_counts = result
            server_success = True
    except Exception:
        pass

    activity = []
    try:
        activity = svc.get_play_history() or []
    except Exception:
        pass

    library_spaces = {}
    try:
        space_info = svc.get_space_info()
        library_spaces = {
            "UsedPercent": space_info.used_percent,
            "FreeSpace": space_info.free_space,
            "UsedSpace": space_info.used_space,
            "TotalSpace": space_info.total_space,
        }
    except Exception:
        pass

    libraries = []
    try:
        libraries = svc.get_libraries() or []
    except Exception:
        pass

    resumes = []
    try:
        resumes = svc.get_resume() or []
    except Exception:
        pass

    latests = []
    try:
        latests = svc.get_latest() or []
    except Exception:
        pass

    return success(
        data={
            "ServerSucess": server_success,
            "MediaCount": {
                "MovieCount": media_counts.get("Movie", 0),
                "SeriesCount": media_counts.get("Series", 0),
                "SongCount": media_counts.get("Music", 0),
                "EpisodeCount": media_counts.get("Episodes", 0),
            },
            "UserCount": media_counts.get("User", 0),
            "Activitys": activity,
            "LibrarySpaces": library_spaces,
            "Librarys": libraries,
            "Resumes": resumes,
            "Latests": latests,
        }
    )


@router.post("/recommend")
def get_recommend(
    req: dict,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaRecommendationService = Depends(get_media_recommendation_service),
):
    # 兼容前端 ajax_post 格式 {data: params}
    data = req.get("data", req)
    res_list = svc.get_recommend_items(data)
    return success(data=res_list)


@router.post("/search/results")
def get_search_result(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: Searcher = Depends(get_searcher_service),
    result_svc: SearchResultService = Depends(get_search_result_service),
):
    search_results = svc.get_search_results()
    result = result_svc.group_search_results(search_results)
    return success(data={"total": result.total, "result": result.result})


@router.post("/transfer/history")
def get_transfer_history(
    req: GetTransferHistoryRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_history_page(search_str=req.keyword, page=req.page, page_num=req.pagenum)
    return success(
        data={
            "total": result.total,
            "result": result.result,
            "totalPage": result.total_page,
            "pageNum": result.page_num,
            "currentPage": result.current_page,
        }
    )


@router.post("/transfer/statistics")
def get_transfer_statistics(
    req: GetTransferStatisticsRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_statistics(days=req.days if req.days is not None else 90)
    return success(data=result)


@router.post("/unknown")
def get_unknown_list(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    items = svc.get_unknown_list()
    return success(data=items)


@router.post("/unknown/paged")
def get_unknown_list_by_page(
    req: GetUnknownListByPageRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_unknown_list_by_page(search_str=req.keyword, page=req.page, page_num=req.pagenum)
    return success(
        data={
            "total": result.total,
            "items": result.items,
            "totalPage": result.total_page,
            "pageNum": result.page_num,
            "currentPage": result.current_page,
        }
    )


@router.post("/detail")
def media_detail(
    req: MediaDetailRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    mtype = MediaType.MOVIE if req.type in MovieTypes else MediaType.TV
    tmdbid = urllib.parse.unquote(req.tmdbid) if req.tmdbid else req.tmdbid
    if not tmdbid:
        return fail(msg="未指定媒体ID")
    result = svc.get_media_detail(tmdbid=tmdbid, mtype_str=req.type)
    if not result:
        return fail(msg="无法查询到TMDB信息")
    return success(data=result)


@router.post("/search")
def search_media_infos(
    req: SearchMediaInfosRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.keyword:
        return success(data=[])
    result = svc.search_media_infos(keyword=req.keyword, source=req.searchtype, page=1)
    return success(data=result)


@router.post("/unknown/list")
def unidentification(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.re_identify_unknown()
    return success()


@router.post("/category/config/update")
def update_category_config(
    req: UpdateCategoryConfigRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.update_category_config(text=req.config or "")
    return success(msg=msg)


@router.post("/dir/list")
def dir_list(
    req: DirListRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    """目录列表（JSON格式，供前端文件管理器使用）"""
    ok, result, msg = svc.get_dir_list(req.path or "")
    if not ok:
        return fail(msg=msg)
    return success(data=result)


@router.post("/library/paths")
def get_library_paths(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc=Depends(get_config_service),
    sync_svc=Depends(get_sync_service),
    media_file_svc: MediaFileService = Depends(get_media_file_service),
):
    """获取媒体库目录 + 同步源目录"""
    media = svc.get_media_config()
    result = media_file_svc.get_library_paths(
        media=media,
        sync_svc=sync_svc,
    )
    return success(data=result)


@router.get("/tmdb_blacklist/list")
def get_tmdb_blacklist(
    page: int = Query(1, ge=1),
    count: int = Query(30, ge=1, le=100),
    s: str | None = Query(""),
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    items, total = tmdb_svc.get_blacklist(tmdb_id=s if s else None, page=page, count=count)
    return success(
        data={
            "items": items,
            "total": total,
            "page": page,
            "count": count,
        }
    )


@router.post("/tmdb_blacklist/add")
def add_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if not tmdb_svc.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_svc.add_to_blacklist(tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/tmdb_blacklist/delete")
def delete_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if tmdb_svc.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_svc.remove_from_blacklist(tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/tmdb_blacklist/clear")
def clear_tmdb_blacklist(
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if tmdb_svc.get_blacklist():
        tmdb_svc.clear_blacklist()
    return success()


@router.get("/search/files")
def search_files(
    keyword: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_any_permission("library:view", "library:manage")),
):
    """全局搜索媒体库 + 同步源目录中的文件（基于后台索引，O(1) 响应）"""
    from app.services.file_index_service import FileIndexService

    svc = FileIndexService()
    results = svc.search(keyword, limit=limit)
    return success(
        data={
            "items": results,
            "total": len(results),
            "ready": svc.is_ready,
            "indexed": svc.indexed_count,
        }
    )


class MediaPathAddRequest(BaseModel):
    path_type: str
    path: str


class MediaPathRemoveRequest(BaseModel):
    path_type: str
    path: str


class MediaPathUpdateRequest(BaseModel):
    path_type: str
    old_path: str
    new_path: str


@router.post("/library/path")
def get_media_library_config(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """获取媒体库路径配置（DB 优先，YAML 回退）"""
    return success(data=svc.get_config())


@router.post("/library/path/add")
def add_media_library_path(
    req: MediaPathAddRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """添加媒体库路径"""
    svc.add_path(req.path_type, req.path)
    return success()


@router.post("/library/path/remove")
def remove_media_library_path(
    req: MediaPathRemoveRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """移除媒体库路径"""
    svc.remove_path(req.path_type, req.path)
    return success()


@router.post("/library/path/update")
def update_media_library_path(
    req: MediaPathUpdateRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """更新媒体库路径"""
    svc.update_path(req.path_type, req.old_path, req.new_path)
    return success()
