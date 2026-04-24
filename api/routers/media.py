# -*- coding: utf-8 -*-
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import (
    get_current_user,
    get_downloader_service,
    get_media_info_service,
    get_media_library_service,
    get_media_file_service,
    get_media_recommendation_service,
    get_searcher_service,
    get_transfer_history_service,
    get_search_result_service,
)
from app.utils.types import MediaType, MovieTypes
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.search_service import Searcher
from app.services.media_service import (
    MediaInfoService,
    MediaRecommendationService,
    SearchResultService,
    MediaLibraryService,
    TransferHistoryService,
    MediaFileService,
)
from app.utils.response import success, fail

router = APIRouter()


# ---------- Request Models ----------

class DownloadSubtitleRequest(BaseModel):
    path: str
    name: str


class GetSeasonEpisodesRequest(BaseModel):
    tmdbid: int
    title: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None


class GetTvSeasonListRequest(BaseModel):
    tmdbid: int
    title: Optional[str] = None


class MediaInfoRequest(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    year: Optional[str] = None
    page: Optional[str] = None
    rssid: Optional[str] = None


class MediaPathScrapRequest(BaseModel):
    path: str


class MediaPersonRequest(BaseModel):
    tmdbid: Optional[int] = None
    type: Optional[str] = None
    keyword: Optional[str] = None


class MediaRecommendationsRequest(BaseModel):
    tmdbid: int
    type: Optional[str] = None
    page: Optional[int] = 1


class MediaSimilarRequest(BaseModel):
    tmdbid: int
    type: Optional[str] = None
    page: Optional[int] = 1


class MovieCalendarRequest(BaseModel):
    id: Optional[str] = None
    rssid: Optional[str] = None


class NameTestRequest(BaseModel):
    name: str
    subtitle: Optional[str] = None


class PersonMediasRequest(BaseModel):
    personid: int
    type: Optional[str] = None
    page: Optional[int] = 1


class SaveUserScriptRequest(BaseModel):
    javascript: Optional[str] = None
    css: Optional[str] = None


class StartMediasyncRequest(BaseModel):
    librarys: Optional[List[str]] = None


class TvCalendarRequest(BaseModel):
    id: Optional[str] = None
    season: Optional[int] = None
    name: Optional[str] = None
    rssid: Optional[str] = None


class GetCategoryConfigRequest(BaseModel):
    category_name: str


class GetDownloadedRequest(BaseModel):
    page: Optional[int] = None


class GetTransferHistoryRequest(BaseModel):
    keyword: Optional[str] = None
    page: Optional[int] = None
    pagenum: Optional[int] = None


class GetUnknownListByPageRequest(BaseModel):
    keyword: Optional[str] = None
    page: Optional[int] = None
    pagenum: Optional[int] = None


class MediaDetailRequest(BaseModel):
    tmdbid: int
    type: Optional[str] = None


class SearchMediaInfosRequest(BaseModel):
    keyword: str
    searchtype: Optional[str] = None


class UpdateCategoryConfigRequest(BaseModel):
    config: Optional[str] = None


# ---------- Endpoints ----------

@router.post("/download_subtitle")
def download_subtitle(
    req: DownloadSubtitleRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaFileService = Depends(get_media_file_service),
):
    ok, msg = svc.download_subtitle(path=req.path, name=req.name)
    if not ok:
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@router.post("/get_season_episodes")
def get_season_episodes(
    req: GetSeasonEpisodesRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="TMDBID为空")
    season = 1 if req.season is None else req.season
    result = svc.get_season_episodes(
        tmdbid=req.tmdbid, title=req.title, year=req.year, season=season
    )
    return success(episodes=result.episodes)


@router.post("/get_tvseason_list")
def get_tvseason_list(
    req: GetTvSeasonListRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    seasons = svc.get_tvseason_list(tmdbid=req.tmdbid, title=req.title)
    return success(seasons=seasons)


@router.post("/media_info")
def media_info(
    req: MediaInfoRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_media_info_detail(
        mediaid=req.id, mtype=req.type, title=req.title,
        year=req.year, page=req.page, rssid=req.rssid,
    )
    return success(
        type=result.type,
        type_str=result.type_str,
        page=result.page,
        title=result.title,
        vote_average=result.vote_average,
        poster_path=result.poster_path,
        release_date=result.release_date,
        year=result.year,
        overview=result.overview,
        link_url=result.link_url,
        tmdbid=result.tmdbid,
        rssid=result.rssid,
        seasons=result.seasons,
    )


@router.post("/media_path_scrap")
def media_path_scrap(
    req: MediaPathScrapRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.scrap_media_path(path=req.path)
    if msg.startswith("请"):
        return fail(code=-1, msg=msg)
    return success(msg=msg)


@router.post("/media_person")
def media_person(
    req: MediaPersonRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid and not req.keyword:
        return fail(msg="未指定TMDBID或关键字")
    result = svc.get_media_person(
        tmdbid=req.tmdbid, mtype_str=req.type, keyword=req.keyword
    )
    return success(data=result)


@router.post("/media_recommendations")
def media_recommendations(
    req: MediaRecommendationsRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_recommendations(
        tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1
    )
    return success(data=result)


@router.post("/media_similar")
def media_similar(
    req: MediaSimilarRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_similar(
        tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1
    )
    return success(data=result)


@router.post("/mediasync_state")
def mediasync_state(
    current_user: str = Depends(get_current_user),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    text = svc.get_sync_state()
    return success(text=text)


@router.post("/movie_calendar_data")
def movie_calendar_data(
    req: MovieCalendarRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_movie_calendar(tid=req.id, rssid=req.rssid)
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(**result)


@router.post("/name_test")
def name_test(
    req: NameTestRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.name:
        return fail(code=-1)
    result = svc.name_test(name=req.name, subtitle=req.subtitle)
    return success(data=result)


@router.post("/person_medias")
def person_medias(
    req: PersonMediasRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.personid:
        return fail(msg="未指定演员ID")
    result = svc.get_person_medias(
        personid=req.personid, mtype_str=req.type, page=req.page or 1
    )
    return success(data=result)


@router.post("/save_user_script")
def save_user_script(
    req: SaveUserScriptRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaFileService = Depends(get_media_file_service),
):
    svc.save_user_script(
        script=req.javascript or "", css=req.css or ""
    )
    return success(msg="保存成功")


@router.post("/start_mediasync")
def start_mediasync(
    req: StartMediasyncRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    svc.start_sync(librarys=req.librarys or [])
    return success()


@router.post("/tv_calendar_data")
def tv_calendar_data(
    req: TvCalendarRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_tv_calendar(
        tid=req.id, season=req.season, name=req.name, rssid=req.rssid
    )
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(events=result)


@router.post("/clear_history")
def clear_history(
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.clear_history()
    return success()


@router.post("/get_category_config")
def get_category_config(
    req: GetCategoryConfigRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaFileService = Depends(get_media_file_service),
):
    ok, result = svc.get_category_config(category_name=req.category_name)
    if not ok:
        return fail(msg=result)
    return success(text=result)


@router.post("/get_downloaded")
def get_downloaded(
    req: GetDownloadedRequest,
    current_user: str = Depends(get_current_user),
    svc: Downloader = Depends(get_downloader_service),
):
    Items = svc.get_download_history(page=req.page)
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


@router.post("/get_library_mediacount")
def get_library_mediacount(
    current_user: str = Depends(get_current_user),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    result = svc.get_media_count()
    if result:
        return success(**result)
    return fail(code=-1, msg="媒体库服务器连接失败")


@router.post("/get_library_playhistory")
def get_library_playhistory(
    current_user: str = Depends(get_current_user),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(result=svc.get_play_history())


@router.post("/get_library_spacesize")
def get_library_spacesize(
    current_user: str = Depends(get_current_user),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    result = svc.get_space_info()
    return success(
        UsedPercent=result.used_percent,
        FreeSpace=result.free_space,
        UsedSapce=result.used_space,
        TotalSpace=result.total_space,
    )


@router.post("/get_recommend")
def get_recommend(
    req: dict,
    current_user: str = Depends(get_current_user),
    svc: MediaRecommendationService = Depends(get_media_recommendation_service),
):
    # 兼容前端 ajax_post 格式 {data: params}
    data = req.get("data", req)
    res_list = svc.get_recommend_items(data)
    return success(Items=res_list)


@router.post("/get_search_result")
def get_search_result(
    current_user: str = Depends(get_current_user),
    svc: Searcher = Depends(get_searcher_service),
    result_svc: SearchResultService = Depends(get_search_result_service),
):
    search_results = svc.get_search_results()
    result = result_svc.group_search_results(search_results)
    return success(total=result.total, result=result.result)


@router.post("/get_transfer_history")
def get_transfer_history(
    req: GetTransferHistoryRequest,
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_history_page(
        search_str=req.keyword, page=req.page, page_num=req.pagenum
    )
    return success(
        total=result.total,
        result=result.result,
        totalPage=result.total_page,
        pageNum=result.page_num,
        currentPage=result.current_page,
    )


@router.post("/get_transfer_statistics")
def get_transfer_statistics(
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_statistics(days=90)
    return success(**result)


@router.post("/get_unknown_list")
def get_unknown_list(
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    items = svc.get_unknown_list()
    return success(items=items)


@router.post("/get_unknown_list_by_page")
def get_unknown_list_by_page(
    req: GetUnknownListByPageRequest,
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_unknown_list_by_page(
        search_str=req.keyword, page=req.page, page_num=req.pagenum
    )
    return success(
        total=result.total,
        items=result.items,
        totalPage=result.total_page,
        pageNum=result.page_num,
        currentPage=result.current_page,
    )


@router.post("/media_detail")
def media_detail(
    req: MediaDetailRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    mtype = MediaType.MOVIE if req.type in MovieTypes else MediaType.TV
    if not req.tmdbid:
        return fail(msg="未指定媒体ID")
    result = svc.get_media_detail(
        tmdbid=req.tmdbid, mtype_str=req.type
    )
    if not result:
        return fail(msg="无法查询到TMDB信息")
    return success(data=result)


@router.post("/search_media_infos")
def search_media_infos(
    req: SearchMediaInfosRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.keyword:
        return success(result=[])
    result = svc.search_media_infos(
        keyword=req.keyword, source=req.searchtype, page=1
    )
    return success(result=result)


@router.post("/unidentification")
def unidentification(
    current_user: str = Depends(get_current_user),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.re_identify_unknown()
    return success()


@router.post("/update_category_config")
def update_category_config(
    req: UpdateCategoryConfigRequest,
    current_user: str = Depends(get_current_user),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.update_category_config(text=req.config or '')
    return success(msg=msg)
