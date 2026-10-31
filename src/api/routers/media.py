import os
import urllib.parse

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import log
from api.deps import (
    get_discovery_service,
    get_downloader_service,
    get_file_index_service,
    get_filetransfer_service,
    get_media_config_service,
    get_media_file_service,
    get_media_info_service,
    get_media_library_service,
    get_media_recommendation_service,
    get_metadata_service,
    get_search_result_service,
    get_searcher_service,
    get_subscribe_service,
    get_sync_service,
    get_tmdb_blacklist_service,
    get_transfer_history_service,
    require_any_permission,
    require_permission,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    DomainError,
    ResourceNotFoundError,
    ServiceError,
    ValidationError,
)
from app.domain.mediatypes import MediaType, normalize_media_type_input
from app.infrastructure.cache_system import TokenCache
from app.media.metadata import ProviderError, ProviderRef
from app.media.metadata.naming import naming_field_catalog, naming_field_keys
from app.media.metadata.registry import registry as metadata_registry
from app.schemas.common import CommonResponse
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.file_index_service import FileIndexService
from app.services.media_config_service import MediaConfigService
from app.services.media_service import (
    MediaFileService,
    MediaInfoService,
    MediaLibraryService,
    MediaRecommendationService,
    SearchResultService,
    TransferHistoryService,
)
from app.services.metadata_service import MetadataService
from app.services.search_service import Searcher
from app.services.transfer.filetransfer_service import FileTransferService
from app.services.transfer.name_format import FIELD_CATALOG, field_groups, render_path, validate
from app.utils import StringUtils
from app.utils.response import fail, success

router = APIRouter()


def _private_scope(current_user) -> tuple[bool, set[str] | None]:
    """返回私有来源访问开关与权限集；超管不受显式权限码限制."""
    if bool(getattr(current_user, "is_superadmin", False)):
        return True, None
    permissions = set(getattr(current_user, "permissions", []) or [])
    return "metadata:private:view" in permissions, permissions


# ---------- Request Models ----------


class DownloadSubtitleRequest(BaseModel):
    path: str
    name: str


class GetSeasonEpisodesRequest(BaseModel):
    tmdbid: int
    title: str | None = None
    year: str | None = None
    season: int | None = None
    content_profile: str | None = None


class GetTvSeasonListRequest(BaseModel):
    tmdbid: str | int
    title: str | None = None


class MetadataPreviewRef(BaseModel):
    provider: str
    external_id: str
    media_type: str | None = None
    scope: str = "default"


class MetadataSearchRequest(BaseModel):
    query: str
    provider: str | None = None
    media_type: str | None = None
    content_profile: str = "default"
    limit: int = 20


class IdentityMergeRequest(BaseModel):
    source_id: str
    target_id: str


class IdentityReviewRequest(BaseModel):
    identity_id: str
    provider: str
    external_id: str
    scope: str = "default"
    approve: bool = True
    confidence: float = 1.0


class DiscoveryItemsRequest(BaseModel):
    provider: str
    feed: str
    page: int = 1
    filters: dict = Field(default_factory=dict)


class MetadataPreviewRequest(BaseModel):
    refs: list[MetadataPreviewRef] = Field(default_factory=list)
    policy: str | None = None
    anchor_provider: str | None = None
    content_profile: str = "default"
    media_type: str | None = None


class MediaInfoRequest(BaseModel):
    id: str | None = None
    type: str | None = None
    title: str | None = None
    year: str | None = None
    page: str | None = None
    rssid: str | None = None


class MediaPathScrapRequest(BaseModel):
    path: str
    backend_id: str = "local"


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


class StartMediasyncRequest(BaseModel):
    librarys: list[str] | None = None
    server_id: int | None = None


class LibraryTargetRequest(BaseModel):
    server_id: int | None = None


class RefreshLibraryRequest(LibraryTargetRequest):
    items: list[dict] | None = None


class SaveLibraryRouteRequest(BaseModel):
    content_profile: str = ""
    target_path: str | None = None
    server_id: int
    backend_id: str = "local"
    library_id: str | None = None
    enabled: bool = True
    note: str = ""


class TvCalendarRequest(BaseModel):
    id: str | None = None
    season: int | None = None
    name: str | None = None
    rssid: str | None = None


class GetCategoryConfigRequest(BaseModel):
    pass


class GetDownloadedRequest(BaseModel):
    page: int | None = None
    page_size: int | None = Field(default=30, ge=1, le=200)
    user_id: int | None = None  # superadmin 按归属用户过滤


class DeleteDownloadedRequest(BaseModel):
    history_id: int  # DOWNLOAD_HISTORY.ID
    user_id: int | None = None  # superadmin 按归属用户校验


class DeleteAllDownloadedRequest(BaseModel):
    user_id: int | None = None  # superadmin 按归属用户校验


class GetTransferHistoryRequest(BaseModel):
    keyword: str | None = None
    page: int | None = None
    pagenum: int | None = None
    type: str | None = None


class GetTransferStatisticsRequest(BaseModel):
    days: int | None = None


class HistoryIdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class HistoryFilesDeleteRequest(HistoryIdsRequest):
    targets: list[str] = Field(default_factory=list)


class HistoryFilesCheckRequest(HistoryIdsRequest):
    targets: list[str] | None = None


class GetUnknownListByPageRequest(BaseModel):
    keyword: str | None = None
    page: int | None = None
    pagenum: int | None = None


class MediaDetailRequest(BaseModel):
    tmdbid: str
    type: str | None = None


class MediaDetailByRefRequest(BaseModel):
    provider: str
    external_id: str
    media_type: str | None = None
    content_profile: str = "default"
    content_id: str | None = None


class FieldOverrideRequest(BaseModel):
    field_name: str
    value: str
    locked: bool = True


class SearchMediaInfosRequest(BaseModel):
    keyword: str
    searchtype: str | None = None


class UpdateCategoryConfigRequest(BaseModel):
    config: list | None = None


class DirListRequest(BaseModel):
    path: str | None = None
    filter: str | None = None
    backend_id: str | None = None


class MkdirRequest(BaseModel):
    path: str
    name: str
    backend_id: str = "local"


class FileBatchRequest(BaseModel):
    files: list[str]
    dest_dir: str
    backend_id: str = "local"


class TmdbBlacklistRequest(BaseModel):
    tmdb_id: str | None = None
    media_type: str | None = None


def _field_value(fields: dict, name: str):
    item = fields.get(name)
    return item.get("value") if isinstance(item, dict) else None


def _record_detail_data(record: dict, media_type: MediaType, status: dict | None) -> dict:
    """非默认画像直接使用 provider 记录，避免通用合成丢失私有来源图片."""
    provider = str(record.get("provider") or "")
    external_id = str(record.get("external_id") or "")

    def image(name: str) -> str:
        assets = (record.get("images") or {}).get(name) or []
        return next(
            (str(item.get("url")) for item in assets if isinstance(item, dict) and item.get("url")),
            "",
        )

    poster = image("poster")
    backdrop = image("background") or image("backdrop") or image("fanart") or poster
    genres = [str(item) for item in (record.get("genres") or []) if item]
    credits = [item for item in (record.get("credits") or []) if isinstance(item, dict)]
    crews = [{item.get("name"): item.get("character") or "演员"} for item in credits[:12] if item.get("name")]
    actor_profiles = [
        {
            "name": item.get("name"),
            "aliases": list(item.get("aliases") or []),
            "image_url": item.get("image_url") or "",
        }
        for item in credits[:24]
        if item.get("name") and str(item.get("role") or "actor") == "actor"
    ]
    release_date = str(record.get("release_date") or "")
    runtime = record.get("runtime")
    runtime_text = StringUtils.str_timehours(runtime) if isinstance(runtime, int) and runtime else ""
    facts = []
    for label, value in (
        ("类型", " / ".join(genres)),
        ("发行", release_date),
        ("片长", runtime_text),
        ("片商", " / ".join(record.get("studios") or [])),
        ("系列", str(record.get("series") or "")),
    ):
        if value:
            facts.append({label: value})
    return {
        "id": external_id,
        "mediaid": external_id,
        "tmdbid": "",
        "provider": provider,
        "anchor_provider": provider,
        "anchor_external_id": external_id,
        "douban_id": "",
        "title": record.get("title") or "",
        "original_title": record.get("original_title") or "",
        "year": record.get("year") or "",
        "overview": record.get("overview") or "",
        "type": media_type.value,
        "image": poster,
        "poster": poster,
        "background": backdrop,
        "backdrop": backdrop,
        "genres": genres,
        "runtime": runtime_text,
        "vote": next(iter((record.get("ratings") or {}).values()), None),
        "crews": crews,
        "actor_profiles": actor_profiles,
        "fact": facts,
        "seasons": [],
        "links": [],
        "link": "",
        "similar": [],
        "fav": (status or {}).get("fav", "0"),
        "rssid": (status or {}).get("rssid", ""),
        "sub_seasons": (status or {}).get("sub_seasons", []),
    }


# ---------- Endpoints ----------


@router.post("/subtitle/download", response_model=CommonResponse, summary="下载字幕")
def download_subtitle(
    req: DownloadSubtitleRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        svc.download_subtitle(path=req.path, name=req.name)
        return success(message="字幕下载任务已提交，正在后台运行。")
    except (ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(code=ErrorCode.OPERATION_FAILED, msg=e.message)


@router.post("/season/episodes", response_model=CommonResponse, summary="获取剧集列表")
def get_season_episodes(
    req: GetSeasonEpisodesRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="TMDBID为空")
    season = 1 if req.season is None else req.season
    result = svc.get_season_episodes(
        tmdbid=req.tmdbid,
        title=req.title,
        year=req.year,
        season=season,
        content_profile=req.content_profile,
    )
    return success(data=result.episodes)


@router.post("/season/list", response_model=CommonResponse, summary="获取电视剧季列表")
def get_tvseason_list(
    req: GetTvSeasonListRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    seasons = svc.get_tvseason_list(tmdbid=req.tmdbid, title=req.title)
    return success(data=seasons)


@router.post("/info", response_model=CommonResponse, summary="获取媒体信息")
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


@router.post("/scrap", response_model=CommonResponse, summary="刮削媒体路径")
def media_path_scrap(
    req: MediaPathScrapRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.scrap_media_path(path=req.path, backend_id=req.backend_id)
    if msg.startswith("请"):
        return fail(code=ErrorCode.OPERATION_FAILED, msg=msg)
    return success(message=msg)


@router.post("/person", response_model=CommonResponse, summary="获取演员信息")
def media_person(
    req: MediaPersonRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid and not req.keyword:
        return fail(msg="未指定TMDBID或关键字")
    result = svc.get_media_person(tmdbid=req.tmdbid, mtype_str=req.type, keyword=req.keyword)
    return success(data=result)


@router.post("/recommendations", response_model=CommonResponse, summary="获取媒体推荐")
def media_recommendations(
    req: MediaRecommendationsRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_recommendations(tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/similar", response_model=CommonResponse, summary="获取相似媒体")
def media_similar(
    req: MediaSimilarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.tmdbid:
        return fail(msg="未指定TMDBID")
    result = svc.get_media_similar(tmdbid=req.tmdbid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/sync/state", response_model=CommonResponse, summary="获取媒体同步状态")
def mediasync_state(
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    text = svc.get_sync_state()
    return success(data=text)


@router.post("/calendar/movie", response_model=CommonResponse, summary="获取电影日历")
def movie_calendar_data(
    req: MovieCalendarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_movie_calendar(tid=req.id, rssid=req.rssid)
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(data=result)


@router.post("/name_test", response_model=CommonResponse, summary="名称测试")
def name_test(
    req: NameTestRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.name:
        return fail(code=ErrorCode.PARAM_VALIDATION_FAILED)
    result = svc.name_test(name=req.name, subtitle=req.subtitle, user=current_user)
    return success(data=result)


@router.post("/person/medias", response_model=CommonResponse, summary="获取演员作品")
def person_medias(
    req: PersonMediasRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.personid:
        return fail(msg="未指定演员ID")
    result = svc.get_person_medias(personid=req.personid, mtype_str=req.type, page=req.page or 1)
    return success(data=result)


@router.post("/sync/start", response_model=CommonResponse, summary="启动媒体同步")
def start_mediasync(
    req: StartMediasyncRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    svc.start_sync(librarys=req.librarys or [], server_id=req.server_id)
    return success()


@router.post("/library/libraries", response_model=CommonResponse, summary="获取指定实例的媒体库")
def get_media_libraries(
    req: LibraryTargetRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    try:
        return success(data=svc.get_libraries(req.server_id))
    except Exception as err:  # noqa: BLE001
        log.debug(f"[MediaLibrary]获取实例媒体库失败: {err}")
        return fail(msg="无法连接媒体服务器，请检查实例配置")


@router.post("/library/refresh", response_model=CommonResponse, summary="刷新指定媒体服务器")
def refresh_library(
    req: RefreshLibraryRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    svc.refresh_library(server_id=req.server_id, items=req.items)
    return success()


@router.post("/library/routes", response_model=CommonResponse, summary="获取媒体库画像路由")
def get_library_routes(
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(data=svc.get_routes())


@router.post("/library/routes/save", response_model=CommonResponse, summary="保存媒体库画像路由")
def save_library_route(
    req: SaveLibraryRouteRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    try:
        return success(data=svc.save_route(req.model_dump()))
    except ValueError as err:
        return fail(msg=str(err))


@router.post("/library/routes/update", response_model=CommonResponse, summary="更新媒体库画像路由")
def update_library_route(
    req: dict,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    try:
        return success(data=svc.save_route(req, route_id=int(req.get("id") or 0)))
    except ValueError as err:
        return fail(msg=str(err))


@router.post("/library/routes/delete", response_model=CommonResponse, summary="删除媒体库画像路由")
def delete_library_route(
    req: dict,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(data=svc.delete_route(int(req.get("id") or 0)))


@router.post("/calendar/tv", response_model=CommonResponse, summary="获取电视剧日历")
def tv_calendar_data(
    req: TvCalendarRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    result = svc.get_tv_calendar(tid=req.id, season=req.season, name=req.name, rssid=req.rssid)
    if not result:
        return fail(msg="无法查询到信息或上映日期不正确")
    return success(data=result)


@router.post("/history/clear", response_model=CommonResponse, summary="清空转移历史")
def clear_history(
    current_user=Depends(require_permission("library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.clear_history()
    return success()


@router.post("/category/config", response_model=CommonResponse, summary="获取分类配置")
def get_category_config(
    req: GetCategoryConfigRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        result = svc.get_category_config()
        return success(data=result)
    except (ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.post("/library/downloaded", response_model=CommonResponse, summary="获取已下载列表")
def get_downloaded(
    req: GetDownloadedRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    # superadmin 可按归属用户过滤；普通用户行级过滤兜底
    scoped_user = current_user
    if req.user_id and current_user.is_superadmin:
        scoped_user = current_user.model_copy(update={"user_id": req.user_id, "role_codes": []})
    items = svc.get_download_history(page=req.page or 1, num=req.page_size or 30, user=scoped_user)
    if items:
        return success(
            data=[
                {
                    "id": item.TMDBID,
                    "orgid": item.TMDBID,
                    "tmdbid": item.TMDBID,
                    "title": item.TITLE,
                    "type": MediaType.from_string(item.TYPE or "").value,
                    "media_type": MediaType.from_string(item.TYPE or "").display_name,
                    "year": item.YEAR,
                    "vote": item.VOTE,
                    "image": item.POSTER,
                    "overview": item.TORRENT,
                    "enclosure": item.ENCLOSURE,
                    "season_episode": item.SE or "",
                    "date": item.DATE,
                    "site": item.SITE,
                    "content_profile": getattr(item, "CONTENT_PROFILE", "") or "",
                    "history_id": item.ID,
                }
                for item in items
            ]
        )
    return success(data=[])


@router.post("/library/downloaded/delete", response_model=CommonResponse, summary="删除单条已下载记录")
def delete_downloaded(
    req: DeleteDownloadedRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    """删除一条下载历史记录（非超管仅能删除本人或系统记录）."""
    scoped_user = current_user
    if req.user_id and current_user.is_superadmin:
        scoped_user = current_user.model_copy(update={"user_id": req.user_id, "role_codes": []})
    if svc.delete_download_history_by_id(req.history_id, user=scoped_user):
        return success(data=True)
    return fail(msg="记录不存在或无权删除")


@router.post("/library/downloaded/delete_all", response_model=CommonResponse, summary="清空已下载记录")
def delete_all_downloaded(
    req: DeleteAllDownloadedRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: Downloader = Depends(get_downloader_service),
):
    """清空下载历史记录（非超管仅清空本人或系统记录），返回删除条数."""
    scoped_user = current_user
    if req.user_id and current_user.is_superadmin:
        scoped_user = current_user.model_copy(update={"user_id": req.user_id, "role_codes": []})
    count = svc.delete_all_download_history(user=scoped_user)
    return success(data={"count": count})


@router.post("/library/servers", response_model=CommonResponse, summary="获取媒体服务器实例")
def get_library_servers(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(data=svc.get_servers())


@router.post("/library/count", response_model=CommonResponse, summary="获取媒体库统计")
def get_library_mediacount(
    server_id: int | None = None,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    result = svc.get_media_count(server_id)
    if result:
        return success(data=result)
    return fail(code=ErrorCode.MEDIA_SERVER_ERROR, msg="媒体库服务器连接失败")


@router.post("/library/history", response_model=CommonResponse, summary="获取播放历史")
def get_library_playhistory(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    return success(data=svc.get_play_history())


@router.post("/library/space", response_model=CommonResponse, summary="获取媒体库空间")
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


@router.post("/library/home", response_model=CommonResponse, summary="获取媒体库首页")
def get_library_home(
    req: LibraryTargetRequest | None = None,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaLibraryService = Depends(get_media_library_service),
):
    requested_id = req.server_id if req else None
    if requested_id is not None and requested_id not in {item["id"] for item in svc.get_servers()}:
        return fail(msg="媒体服务器不存在或未启用")
    return success(data=svc.get_home_data(requested_id))


@router.post("/recommend", response_model=CommonResponse, summary="获取推荐")
def get_recommend(
    req: dict,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaRecommendationService = Depends(get_media_recommendation_service),
):
    # 兼容前端 ajax_post 格式 {data: params}
    data = req.get("data", req)
    res_list = svc.get_recommend_items(data)
    return success(data=res_list)


@router.post("/search/results", response_model=CommonResponse, summary="获取搜索结果")
def get_search_result(
    req: dict | None = None,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: Searcher = Depends(get_searcher_service),
    result_svc: SearchResultService = Depends(get_search_result_service),
):
    req = req or {}
    session_id = req.get("session_id") or TokenCache.get(f"search_session:{current_user.user_id}")
    search_results = svc.get_search_results(session_id, user_id=current_user.user_id)
    result = result_svc.group_search_results(search_results)
    return success(data={"total": result.total, "result": result.result})


@router.post("/transfer/history", response_model=CommonResponse, summary="获取转移历史")
def get_transfer_history(
    req: GetTransferHistoryRequest,
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_history_page(
        search_str=req.keyword, page=req.page, page_num=req.pagenum, media_type=req.type
    )
    return success(
        data={
            "total": result.total,
            "result": result.result,
            "totalPage": result.total_page,
            "pageNum": result.page_num,
            "currentPage": result.current_page,
        }
    )


@router.post("/transfer/statistics", response_model=CommonResponse, summary="获取转移统计")
def get_transfer_statistics(
    req: GetTransferStatisticsRequest,
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    result = svc.get_transfer_statistics(days=req.days if req.days is not None else 90)
    return success(data=result)


@router.post("/history/records/delete", response_model=CommonResponse, summary="删除识别记录（不删除文件）")
def delete_history_records(
    req: HistoryIdsRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
    ft: FileTransferService = Depends(get_filetransfer_service),
):
    ids = [int(item) for item in req.ids if item is not None]
    if not ids:
        return fail(msg="未选择要删除的记录")
    results = ft.delete_records(ids)
    svc.invalidate_cache()
    deleted = sum(1 for item in results if item.get("status") == "deleted")
    return success(data={"results": results, "deleted": deleted, "total": len(ids)})


@router.post("/history/files/delete", response_model=CommonResponse, summary="删除识别记录关联文件（保留记录）")
def delete_history_files(
    req: HistoryFilesDeleteRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
    ft: FileTransferService = Depends(get_filetransfer_service),
):
    ids = [int(item) for item in req.ids if item is not None]
    targets = [target for target in req.targets if target in ("source", "library")]
    if not ids or not targets:
        return fail(msg="未选择记录或删除目标")
    results = ft.delete_record_files(ids, targets)
    svc.invalidate_cache()
    return success(data={"results": results})


@router.post("/history/files/check", response_model=CommonResponse, summary="检测识别记录关联文件状态")
def check_history_files(
    req: HistoryFilesCheckRequest,
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
    ft: FileTransferService = Depends(get_filetransfer_service),
):
    ids = [int(item) for item in req.ids if item is not None]
    if not ids:
        return fail(msg="未选择记录")
    results = ft.check_record_files(ids, req.targets)
    svc.invalidate_cache()
    return success(data={"results": results})


@router.post("/unknown", response_model=CommonResponse, summary="获取未识别列表")
def get_unknown_list(
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    items = svc.get_unknown_list()
    return success(data=items)


@router.post("/unknown/paged", response_model=CommonResponse, summary="分页获取未识别列表")
def get_unknown_list_by_page(
    req: GetUnknownListByPageRequest,
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
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


@router.post("/detail", response_model=CommonResponse, summary="获取媒体详情")
def media_detail(
    req: MediaDetailRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    tmdbid = urllib.parse.unquote(req.tmdbid) if req.tmdbid else req.tmdbid
    if not tmdbid:
        return fail(msg="未指定媒体ID")
    result = svc.get_media_detail(tmdbid=tmdbid, mtype_str=req.type)
    if not result:
        return fail(msg="无法查询到TMDB信息")
    return success(data=result)


@router.post("/detail_by_ref", response_model=CommonResponse, summary="按外部锚点获取媒体详情")
def media_detail_by_ref(
    req: MediaDetailByRefRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
    sub_svc=Depends(get_subscribe_service),
):
    allow_private, permissions = _private_scope(current_user)
    request_type, content_profile = normalize_media_type_input(req.media_type, req.content_profile)
    media_type = MediaType.from_string(request_type) if request_type else None
    if media_type == MediaType.UNKNOWN:
        media_type = None
    try:
        record = svc.lookup(
            req.provider,
            req.external_id,
            media_type=media_type,
            allow_private=allow_private,
            permissions=permissions,
        )
    except Exception:  # noqa: BLE001 - 上游抓取/熔断返回明确错误
        return fail(code=ErrorCode.OPERATION_FAILED, msg="无法获取媒体详情")
    is_custom_profile = content_profile != "default"
    if is_custom_profile and req.content_id:
        # 前端已知道内容编号时，优先按编号取聚合详情，避免来源 slug 失效。
        try:
            aggregate = svc.lookup(
                content_profile,
                req.content_id,
                media_type=media_type,
                allow_private=allow_private,
                permissions=permissions,
            )
            if aggregate:
                record = aggregate
        except Exception:  # noqa: BLE001, S110 - 聚合失败继续用来源记录
            pass
    if not record and is_custom_profile:
        # 源 provider 使用 slug 或临时失效时，回退到该内容画像的聚合 provider。
        try:
            record = svc.lookup(
                content_profile,
                req.external_id,
                media_type=media_type,
                allow_private=allow_private,
                permissions=permissions,
            )
        except Exception:  # noqa: BLE001 - 聚合回退失败按原错误处理
            record = None
    if not record:
        return fail(msg="无法获取媒体详情")
    if is_custom_profile:
        content_id = str((record.get("extra") or {}).get("adult.content_id") or "")
        if not content_id:
            content_id = next(
                (
                    str(ref.get("external_id") or "")
                    for ref in record.get("refs") or []
                    if ref.get("provider") == "content_id"
                ),
                "",
            )
        if content_id and req.provider != content_profile:
            try:
                aggregate = svc.lookup(
                    content_profile,
                    content_id,
                    media_type=media_type,
                    allow_private=allow_private,
                    permissions=permissions,
                )
                if aggregate:
                    record = aggregate
            except Exception:  # noqa: BLE001, S110 - 聚合失败保留来源记录
                pass
        status = sub_svc.get_subscribe_by_anchor(
            str(record.get("provider") or req.provider),
            str(record.get("external_id") or req.external_id),
            media_type or MediaType.MOVIE,
            user=current_user,
        )
        return success(data=_record_detail_data(record, media_type or MediaType.MOVIE, status))
    snapshot = svc.compose_for_ref(
        req.provider,
        req.external_id,
        media_type=media_type or MediaType.MOVIE,
        content_profile=content_profile,
        include_tmdb=True,
        user_id=current_user.user_id,
        allow_private=allow_private,
        permissions=permissions,
    )
    if not snapshot:
        if is_custom_profile:
            status = sub_svc.get_subscribe_by_anchor(
                str(record.get("provider") or req.provider),
                str(record.get("external_id") or req.external_id),
                media_type or MediaType.MOVIE,
                user=current_user,
            )
            return success(data=_record_detail_data(record, media_type or MediaType.MOVIE, status))
        return fail(msg="无法获取媒体详情")
    fields = snapshot.get("fields") or {}
    images = snapshot.get("images") or {}
    poster = next(
        (item.get("url") for item in images.get("poster", []) if item.get("url")),
        "",
    )
    backdrop = (
        next(
            (item.get("url") for item in images.get("backdrop", []) if item.get("url")),
            "",
        )
        or poster
    )
    if is_custom_profile:
        # 自定义画像的 provider 记录可能包含主项目快照未映射的图片，做通用兜底。
        record_images = record.get("images") or {}
        if not poster:
            poster = next(
                (item.get("url") for item in record_images.get("poster", []) if item.get("url")),
                "",
            )
        if not backdrop:
            for key in ("background", "backdrop", "fanart"):
                backdrop = next(
                    (item.get("url") for item in record_images.get(key, []) if item.get("url")),
                    "",
                )
                if backdrop:
                    break
    ratings = snapshot.get("ratings") or {}
    rating = next(iter(ratings.values()), None)
    runtime = fields.get("runtime", {}).get("value") if isinstance(fields.get("runtime"), dict) else None
    release_date = _field_value(fields, "release_date")
    genres = snapshot.get("genres") or []
    countries = snapshot.get("countries") or []
    languages = snapshot.get("spoken_languages") or []
    studios = snapshot.get("studios") or []
    credits = snapshot.get("credits") or []
    role_labels = {
        "director": "导演",
        "actor": "演员",
        "writer": "编剧",
        "music": "音乐",
        "studio": "制作",
    }
    crews = [
        {item.get("name"): role_labels.get(str(item.get("role") or ""), item.get("character") or "演员")}
        for item in credits[:12]
        if item.get("name")
    ]
    actor_profiles = [
        {
            "name": item.get("name"),
            "aliases": list(item.get("aliases") or []),
            "image_url": item.get("image_url") or "",
        }
        for item in credits[:24]
        if item.get("name") and str(item.get("role") or "actor") == "actor"
    ]
    extra = snapshot.get("extra") or {}
    aliases = snapshot.get("aliases") or []
    seasons = []
    for item in snapshot.get("seasons") or []:
        number = item.get("season_number")
        if not isinstance(number, int):
            continue
        seasons.append(
            {
                "season_number": number,
                "name": item.get("title") or f"第 {number} 季",
                "episode_count": item.get("episode_count"),
                "air_date": item.get("air_date"),
                "poster_path": item.get("poster"),
            }
        )
    episodes = snapshot.get("episodes") or []
    if not seasons and episodes:
        number = int(extra.get("douban.season") or episodes[0].get("season_number") or 1)
        seasons.append(
            {
                "season_number": number,
                "name": f"第 {number} 季",
                "episode_count": len(episodes),
                "air_date": episodes[0].get("air_date"),
            }
        )
    elif not seasons and (extra.get("douban.episodes_count") or extra.get("bangumi.eps")):
        count_value = extra.get("douban.episodes_count") or extra.get("bangumi.eps")
        episodes_count = int(str(count_value))
        if episodes_count > 0:
            number = int(extra.get("douban.season") or 1)
            seasons.append(
                {
                    "season_number": number,
                    "name": f"第 {number} 季",
                    "episode_count": episodes_count,
                }
            )
    facts = []
    episodes_count = extra.get("douban.episodes_count") or extra.get("bangumi.eps") or ""
    imdb = extra.get("douban.imdb") or ""
    for label, value in (
        ("类型", " / ".join(genres)),
        ("首播", release_date),
        ("集数", str(episodes_count) if episodes_count else ""),
        ("单集片长", StringUtils.str_timehours(runtime) if runtime else ""),
        ("地区", " / ".join(countries)),
        ("语言", " / ".join(languages)),
        ("又名", " / ".join(aliases[:6])),
        ("IMDb", str(imdb)),
        ("制片公司", " / ".join(studios)),
        ("评分", str(rating) if rating is not None else ""),
        ("季数", str(len(seasons)) if seasons else ""),
    ):
        if value:
            facts.append({label: value})
    provider = str(record.get("provider") or req.provider)
    external_id = str(record.get("external_id") or req.external_id)
    links = []
    provider_url = metadata_registry.provider_detail_url(provider, external_id, media_type or MediaType.MOVIE)
    if provider_url:
        label = {
            "douban": "豆瓣",
            "bangumi": "Bangumi",
            "tmdb": "TMDB",
        }.get(provider, provider)
        links.append({"provider": provider, "label": label, "url": provider_url})
    tmdb_ref = next(
        (item for item in snapshot.get("refs", []) if item.get("provider") == "tmdb"),
        None,
    )
    if tmdb_ref and str(tmdb_ref.get("external_id") or "").isdigit():
        tmdb_id = str(tmdb_ref["external_id"])
        links.append(
            {
                "provider": "tmdb",
                "label": "TMDB",
                "url": f"https://www.themoviedb.org/{'movie' if (media_type == MediaType.MOVIE) else 'tv'}/{tmdb_id}",
            }
        )
    status = sub_svc.get_subscribe_by_anchor(
        provider,
        external_id,
        media_type or MediaType.MOVIE,
        user=current_user,
    )
    data = {
        "id": external_id,
        "mediaid": (
            f"DB:{external_id}"
            if provider == "douban"
            else f"BG:{external_id}"
            if provider == "bangumi"
            else external_id
        ),
        "tmdbid": tmdb_ref.get("external_id", "") if tmdb_ref else "",
        "provider": provider,
        "anchor_provider": provider,
        "anchor_external_id": external_id,
        "douban_id": external_id if provider == "douban" else "",
        "title": _field_value(fields, "title") or record.get("title") or "",
        "original_title": _field_value(fields, "original_title") or "",
        "year": _field_value(fields, "year") or record.get("year") or "",
        "overview": _field_value(fields, "overview") or record.get("overview") or "",
        "type": (media_type or MediaType.MOVIE).value,
        "image": poster,
        "poster": poster,
        "background": backdrop,
        "backdrop": backdrop,
        "genres": genres,
        "runtime": StringUtils.str_timehours(runtime) if runtime else "",
        "vote": rating,
        "crews": crews,
        "actor_profiles": actor_profiles,
        "fact": facts,
        "seasons": seasons,
        "links": links,
        "link": links[0]["url"] if links else "",
        "similar": svc.similar_for_ref(
            provider,
            external_id,
            media_type=media_type or MediaType.MOVIE,
            title=str(_field_value(fields, "title") or record.get("title") or ""),
            allow_private=allow_private,
            permissions=permissions,
        ),
        "fav": (status or {}).get("fav", "0"),
        "rssid": (status or {}).get("rssid", ""),
        "sub_seasons": (status or {}).get("sub_seasons", []),
    }
    return success(data=data)


@router.post("/search", response_model=CommonResponse, summary="搜索媒体")
def search_media_infos(
    req: SearchMediaInfosRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaInfoService = Depends(get_media_info_service),
):
    if not req.keyword:
        return success(data=[])
    result = svc.search_media_infos(keyword=req.keyword, source=req.searchtype, page=1)
    return success(data=result)


@router.post("/metadata/search", response_model=CommonResponse, summary="多源元数据搜索")
def metadata_search(
    req: MetadataSearchRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    allow_private, permissions = _private_scope(current_user)
    request_type, content_profile = normalize_media_type_input(req.media_type, req.content_profile)
    media_type = MediaType.from_string(request_type) if request_type else None
    if media_type == MediaType.UNKNOWN:
        media_type = None
    return success(
        data=svc.search(
            query=req.query,
            provider=req.provider,
            media_type=media_type,
            content_profile=content_profile,
            limit=req.limit,
            allow_private=allow_private,
            permissions=permissions,
        )
    )


@router.get("/lookup", response_model=CommonResponse, summary="统一元数据查询")
def metadata_lookup(
    provider: str,
    external_id: str,
    media_type: str | None = None,
    scope: str = "default",
    allow_missing: bool = False,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    allow_private, permissions = _private_scope(current_user)
    request_type, _profile = normalize_media_type_input(media_type, scope)
    ref_type = MediaType.from_string(request_type) if request_type else None
    if ref_type == MediaType.UNKNOWN:
        ref_type = None
    try:
        data = svc.lookup(
            provider,
            external_id,
            media_type=ref_type,
            scope=scope,
            allow_private=allow_private,
            permissions=permissions,
        )
    except ProviderError as exc:
        # 单源 404/抓取失败不应变成 500；允许多源回退时返回空结果。
        if allow_missing:
            return success(data=None)
        return fail(msg=f"元数据查询失败: {exc}")
    if data is None:
        return success(data=None) if allow_missing else fail(msg="未找到元数据")
    if isinstance(data, dict):
        images = data.get("images") or {}
        if not data.get("poster"):
            data["poster"] = next(
                (item.get("url") for item in images.get("poster", []) if item.get("url")),
                "",
            )
        if not data.get("backdrop"):
            for image_type in ("background", "backdrop", "fanart"):
                data["backdrop"] = next(
                    (item.get("url") for item in images.get(image_type, []) if item.get("url")),
                    "",
                )
                if data["backdrop"]:
                    break
    return success(data=data)


@router.get("/metadata/metrics", response_model=CommonResponse, summary="元数据链路指标")
def metadata_metrics(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    return success(data=svc.metrics())


@router.get("/providers", response_model=CommonResponse, summary="元数据 provider 能力与健康状态")
def metadata_providers(
    include_health: bool = Query(True),
    provider: str | None = Query(None),
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    allow_private, permissions = _private_scope(current_user)
    return success(
        data=svc.list_providers(
            allow_private=allow_private,
            permissions=permissions,
            probe_health=include_health,
            provider_key=provider,
        )
    )


@router.get("/person/{person_id}", response_model=CommonResponse, summary="人员实体详情")
def person_detail(
    person_id: str,
    current_user=Depends(require_permission("metadata:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    data = svc.person_detail(person_id)
    return success(data=data) if data else fail(msg="人员不存在")


@router.post("/identity/merge", response_model=CommonResponse, summary="合并重复身份")
def identity_merge(
    req: IdentityMergeRequest,
    current_user=Depends(require_permission("metadata:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    return success(data={"merged": svc.merge_identity(req.source_id, req.target_id)})


@router.get("/identity/conflicts", response_model=CommonResponse, summary="待审核的跨源链接")
def identity_conflicts(
    limit: int = 100,
    current_user=Depends(require_permission("metadata:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    return success(data=svc.pending_links(limit=limit))


@router.get("/identity/{identity_id}", response_model=CommonResponse, summary="作品身份详情")
def identity_detail(
    identity_id: str,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    allow_private, _permissions = _private_scope(current_user)
    data = svc.identity_detail(identity_id, allow_private=allow_private)
    return success(data=data) if data else fail(msg="身份不存在")


@router.post("/identity/link/review", response_model=CommonResponse, summary="审核跨源链接")
def identity_review_link(
    req: IdentityReviewRequest,
    current_user=Depends(require_permission("metadata:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    result = svc.review_link(
        req.identity_id,
        provider=req.provider,
        external_id=req.external_id,
        approve=req.approve,
        confidence=req.confidence,
        scope=req.scope,
    )
    return success(data=result) if result is not None else fail(msg="链接不存在或已处理")


@router.get("/discovery/providers", response_model=CommonResponse, summary="探索页来源与 feed")
def discovery_providers(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc=Depends(get_discovery_service),
):
    allow_private, permissions = _private_scope(current_user)
    return success(data=svc.list_sources(allow_private=allow_private, permissions=permissions))


@router.post("/discovery/items", response_model=CommonResponse, summary="获取探索 feed 内容")
def discovery_items(
    req: DiscoveryItemsRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc=Depends(get_discovery_service),
):
    allow_private, permissions = _private_scope(current_user)
    try:
        page = svc.items(
            req.provider,
            req.feed,
            page=req.page,
            filters=req.filters,
            allow_private=allow_private,
            permissions=permissions,
        )
    except ValidationError as exc:
        return fail(msg=exc.message)
    return success(data=page.model_dump(mode="json"))


@router.post("/metadata/preview", response_model=CommonResponse, summary="预览多源元数据合成")
def metadata_preview(
    req: MetadataPreviewRequest,
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MetadataService = Depends(get_metadata_service),
):
    if not req.refs:
        return fail(msg="未指定元数据引用")
    private_allowed, permissions = _private_scope(current_user)
    request_type, content_profile = normalize_media_type_input(req.media_type, req.content_profile)
    refs = []
    for item in req.refs:
        ref_type_value, _profile = normalize_media_type_input(item.media_type, content_profile)
        ref_type = MediaType.from_string(ref_type_value) if ref_type_value else None
        if ref_type == MediaType.UNKNOWN:
            ref_type = None
        refs.append(
            ProviderRef(
                provider=item.provider,
                external_id=item.external_id,
                media_type=ref_type,
                scope=item.scope,
            )
        )
    media_type = MediaType.from_string(request_type) if request_type else None
    if media_type == MediaType.UNKNOWN:
        media_type = None
    try:
        result = svc.preview(
            refs,
            policy=req.policy,
            anchor_provider=req.anchor_provider,
            content_profile=content_profile,
            media_type=media_type,
            allow_private=private_allowed,
            permissions=permissions,
        )
    except ValidationError as exc:
        return fail(msg=exc.message)
    if result.metadata is None:
        return fail(msg="元数据合成失败，请检查引用或主源可用性")
    return success(
        data={
            "metadata": result.metadata.model_dump(mode="json"),
            "degraded": result.degraded,
            "errors": [{"provider": error.provider, "message": error.message} for error in result.errors],
        }
    )


@router.post("/unknown/list", response_model=CommonResponse, summary="重新识别未识别项")
def unidentification(
    current_user=Depends(require_any_permission("transfer:view", "library:manage")),
    svc: TransferHistoryService = Depends(get_transfer_history_service),
):
    svc.re_identify_unknown()
    return success()


@router.get("/category/taxonomy", response_model=CommonResponse, summary="获取分类映射词表")
def get_category_taxonomy(
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    return success(data=svc.get_category_taxonomy())


@router.post("/category/config/update", response_model=CommonResponse, summary="更新分类配置")
def update_category_config(
    req: UpdateCategoryConfigRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    msg = svc.update_category_config(items=req.config or [])
    return success(message=msg)


@router.post("/dir/list", response_model=CommonResponse, summary="获取目录列表")
def dir_list(
    req: DirListRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    """目录列表（JSON格式，供前端文件管理器使用）"""
    try:
        result = svc.get_dir_list(req.path or "", req.backend_id or "")
        return success(data=result)
    except (ValidationError, ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.post("/dir/mkdir", response_model=CommonResponse, summary="创建目录")
def make_dir(
    req: MkdirRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        target = svc.make_dir(parent=req.path, name=req.name, backend_id=req.backend_id)
        return success(data={"path": target}, message="创建成功")
    except (ValidationError, ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.post("/files/move", response_model=CommonResponse, summary="移动文件")
def move_files(
    req: FileBatchRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        msg = svc.move_or_copy_files(req.files, req.dest_dir, backend_id=req.backend_id, move=True)
        return success(message=msg)
    except (ValidationError, ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.post("/files/copy", response_model=CommonResponse, summary="复制文件")
def copy_files(
    req: FileBatchRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        msg = svc.move_or_copy_files(req.files, req.dest_dir, backend_id=req.backend_id, move=False)
        return success(message=msg)
    except (ValidationError, ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.get("/file/download", summary="下载文件")
def download_file(
    path: str = Query(..., min_length=1),
    backend_id: str = Query("local"),
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    stream, _info = svc.open_download(path, backend_id)

    def _iter():
        try:
            while chunk := stream.read(1024 * 1024):
                yield chunk
        finally:
            stream.close()

    quoted = urllib.parse.quote(os.path.basename(path))
    return StreamingResponse(
        _iter(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quoted}"},
    )


@router.post("/file/upload", response_model=CommonResponse, summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    path: str = Form(...),
    backend_id: str = Form("local"),
    current_user=Depends(require_permission("library:manage")),
    svc: MediaFileService = Depends(get_media_file_service),
):
    try:
        target = svc.save_upload(dest_dir=path, name=file.filename or "", stream=file.file, backend_id=backend_id)
        return success(data={"path": target}, message="上传成功")
    except (ValidationError, ResourceNotFoundError, ServiceError, DomainError) as e:
        return fail(msg=e.message)


@router.post("/library/paths", response_model=CommonResponse, summary="获取媒体库路径")
def get_library_paths(
    current_user=Depends(require_permission("library:manage")),
    media_svc=Depends(get_media_config_service),
    sync_svc=Depends(get_sync_service),
    media_file_svc: MediaFileService = Depends(get_media_file_service),
):
    """获取媒体库目录 + 同步源目录（从数据库 CONFIG_MEDIA 读取）"""
    media = media_svc.get_config()
    result = media_file_svc.get_library_paths(
        media=media,
        sync_svc=sync_svc,
    )
    return success(data=result)


@router.get("/tmdb_blacklist/list", response_model=CommonResponse, summary="获取 TMDB 黑名单")
def get_tmdb_blacklist(
    page: int = Query(1, ge=1),
    count: int = Query(30, ge=1, le=100),
    s: str | None = Query(""),
    current_user=Depends(require_permission("library:manage")),
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


@router.post("/tmdb_blacklist/add", response_model=CommonResponse, summary="添加 TMDB 黑名单")
def add_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if not tmdb_svc.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_svc.add_to_blacklist(tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/tmdb_blacklist/delete", response_model=CommonResponse, summary="删除 TMDB 黑名单")
def delete_tmdb_blacklist(
    req: TmdbBlacklistRequest,
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if tmdb_svc.is_blacklisted(req.tmdb_id, req.media_type):
        tmdb_svc.remove_from_blacklist(tmdb_id=req.tmdb_id, media_type=req.media_type)
    return success()


@router.post("/tmdb_blacklist/clear", response_model=CommonResponse, summary="清空 TMDB 黑名单")
def clear_tmdb_blacklist(
    current_user=Depends(require_permission("library:manage")),
    tmdb_svc=Depends(get_tmdb_blacklist_service),
):
    if tmdb_svc.get_blacklist():
        tmdb_svc.clear_blacklist()
    return success()


@router.get("/search/files", response_model=CommonResponse, summary="搜索文件")
def search_files(
    keyword: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
    svc: FileIndexService = Depends(get_file_index_service),
    current_user=Depends(require_any_permission("library:view", "library:manage")),
):
    """全局搜索媒体库 + 同步源目录中的文件（基于后台索引，O(1) 响应）"""
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
    backend: str = "local"


class MediaPathRemoveRequest(BaseModel):
    path_type: str
    path: str


class MediaPathUpdateRequest(BaseModel):
    path_type: str
    old_path: str
    new_path: str
    backend: str = "local"


class MediaLayoutRequest(BaseModel):
    movie_layout: str = "category"
    tv_layout: str = "category"
    anime_layout: str = "flat"


@router.post("/library/path", response_model=CommonResponse, summary="获取媒体库配置")
def get_media_library_config(
    current_user=Depends(require_any_permission("library:view", "library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """获取媒体库路径配置（DB 优先，YAML 回退）"""
    return success(data=svc.get_config())


@router.post("/library/layout", response_model=CommonResponse, summary="更新媒体库目录结构")
def update_media_layout(
    req: MediaLayoutRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """更新电影/电视剧/动漫的目录结构；动漫默认平铺."""
    svc.set_layouts(req.movie_layout, req.tv_layout, req.anime_layout)
    return success()


@router.post("/library/path/add", response_model=CommonResponse, summary="添加媒体库路径")
def add_media_library_path(
    req: MediaPathAddRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """添加媒体库路径"""
    svc.add_path(req.path_type, req.path, req.backend)
    return success()


@router.post("/library/path/remove", response_model=CommonResponse, summary="移除媒体库路径")
def remove_media_library_path(
    req: MediaPathRemoveRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """移除媒体库路径"""
    svc.remove_path(req.path_type, req.path)
    return success()


@router.post("/library/path/update", response_model=CommonResponse, summary="更新媒体库路径")
def update_media_library_path(
    req: MediaPathUpdateRequest,
    current_user=Depends(require_permission("library:manage")),
    svc: MediaConfigService = Depends(get_media_config_service),
):
    """更新媒体库路径"""
    svc.update_path(req.path_type, req.old_path, req.new_path, req.backend)
    return success()


# ---------- 重命名格式：字段目录 / 校验 / 预览 ----------


class NameFormatPreviewRequest(BaseModel):
    format: str
    media_type: str = "tv"
    values: dict = {}


class NameFormatValidateRequest(BaseModel):
    format: str


@router.get("/name_format/fields", response_model=CommonResponse, summary="重命名格式字段目录")
def name_format_fields(
    current_user=Depends(require_any_permission("setting:view", "setting:update")),
):
    """返回可按分组插入的占位符字段目录。"""
    extra_fields = naming_field_catalog()
    groups = field_groups()
    if extra_fields:
        groups.append({"group": "插件字段", "fields": extra_fields})
    return success(
        data={
            "groups": groups,
            "fields": FIELD_CATALOG + extra_fields,
        }
    )


@router.post("/name_format/validate", response_model=CommonResponse, summary="校验重命名格式")
def name_format_validate(
    req: NameFormatValidateRequest,
    current_user=Depends(require_any_permission("setting:view", "setting:update")),
):
    return success(data=validate(req.format, naming_field_keys()))


@router.post("/name_format/preview", response_model=CommonResponse, summary="预览重命名格式")
def name_format_preview(
    req: NameFormatPreviewRequest,
    current_user=Depends(require_any_permission("setting:view", "setting:update")),
):
    mtype = "movie" if str(req.media_type).lower() in ("movie", "电影") else "tv"
    return success(
        data={
            "segments": render_path(req.format, mtype, req.values),
            "validate": validate(req.format, naming_field_keys() | set(req.values.keys())),
        }
    )
