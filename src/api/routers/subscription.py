"""
Subscription Router — FastAPI 迁移
对应原 web/controllers/rss.py，调用 subscribe/ 领域服务
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import (
    get_subscribe_calendar_service,
    get_subscribe_history_service,
    get_subscribe_service,
    require_any_permission,
    require_permission,
)
from app.di import container
from app.media import meta_info
from app.schemas.common import CommonResponse
from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.management.service import SubscribeService
from app.utils.response import fail, success
from app.utils.types import MediaType, SystemConfigKey

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class EmptyRequest(BaseModel):
    data: dict | None = None


class AddRssMediaRequest(BaseModel):
    name: str | None = None
    year: str | None = None
    season: str | None = None
    type: str | None = None
    page: str | None = None
    rssid: str | None = None
    in_form: str | None = None
    keyword: str | None = None
    fuzzy_match: bool | None = None
    mediaid: str | int | None = None
    rss_sites: list | None = None
    search_sites: list | None = None
    over_edition: bool | None = None
    filter_restype: str | None = None
    filter_pix: str | None = None
    filter_team: str | None = None
    filter_rule: str | None = None
    filter_include: str | None = None
    filter_exclude: str | None = None
    save_path: str | None = None
    download_setting: str | None = None
    total_ep: int | None = None
    current_ep: int | None = None
    image: str | None = None
    tmdbid: str | int | None = None


class SubscribeIdRequest(BaseModel):
    rssid: str | None = None


class RedoHistoryRequest(BaseModel):
    rssid: str | None = None
    type: str | None = None


class RefreshRssRequest(BaseModel):
    type: str | None = None
    rssid: str | None = None
    page: str | None = None


class RemoveRssMediaRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    year: str | None = None
    season: str | None = None
    rssid: str | None = None
    tmdbid: str | None = None
    page: str | None = None


class SubscribeDetailRequest(BaseModel):
    rssid: str | None = None
    rsstype: str | None = None


class GetDefaultSubscribeSettingRequest(BaseModel):
    mtype: str | None = None


class DefaultSubscribeSettingSaveRequest(BaseModel):
    mtype: str | None = None
    over_edition: str | None = None
    restype: str | None = None
    pix: str | None = None
    team: str | None = None
    rule: str | None = None
    include: str | None = None
    exclude: str | None = None
    download_setting: str | None = None
    rss_sites: list | None = None
    search_sites: list | None = None


class GetSubscribeHistoryRequest(BaseModel):
    type: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_add_kwargs(req: AddRssMediaRequest) -> dict:
    mtype = MediaType.MOVIE if MediaType.from_string(req.type or "") == MediaType.MOVIE else MediaType.TV
    channel = "R" if req.in_form == "manual" else "D"
    return {
        "mtype": mtype,
        "name": req.name,
        "year": req.year,
        "channel": channel,
        "keyword": req.keyword,
        "fuzzy_match": req.fuzzy_match,
        "mediaid": req.mediaid,
        "rss_sites": req.rss_sites,
        "search_sites": req.search_sites,
        "over_edition": req.over_edition,
        "filter_restype": req.filter_restype,
        "filter_pix": req.filter_pix,
        "filter_team": req.filter_team,
        "filter_rule": req.filter_rule,
        "filter_include": req.filter_include,
        "filter_exclude": req.filter_exclude,
        "save_path": req.save_path,
        "download_setting": req.download_setting,
    }


def _build_update_kwargs(req: AddRssMediaRequest) -> dict:
    mtype = MediaType.MOVIE if MediaType.from_string(req.type or "") == MediaType.MOVIE else MediaType.TV
    return {
        "mtype": mtype,
        "rssid": req.rssid,
        "name": req.name,
        "year": req.year,
        "keyword": req.keyword,
        "fuzzy_match": req.fuzzy_match,
        "mediaid": req.mediaid,
        "rss_sites": req.rss_sites,
        "search_sites": req.search_sites,
        "over_edition": req.over_edition,
        "filter_restype": req.filter_restype,
        "filter_pix": req.filter_pix,
        "filter_team": req.filter_team,
        "filter_rule": req.filter_rule,
        "filter_include": req.filter_include,
        "filter_exclude": req.filter_exclude,
        "save_path": req.save_path,
        "download_setting": req.download_setting,
        "image": req.image,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/add", response_model=CommonResponse, summary="添加 RSS 订阅")
def add_rss_media(
    req: AddRssMediaRequest,
    user: str = Depends(require_any_permission("subscription:manage", "subscription:view")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    kwargs = _build_add_kwargs(req)
    code = 0
    msg = ""
    media_info = None
    season = req.season
    if isinstance(season, list):
        for sea in season:
            kwargs["season"] = sea
            kwargs.pop("total_ep", None)
            kwargs.pop("current_ep", None)
            code, msg, media_info = svc.add_rss_subscribe(**kwargs)
            if code != 0:
                break
    else:
        kwargs["season"] = season
        kwargs["total_ep"] = req.total_ep
        kwargs["current_ep"] = req.current_ep
        code, msg, media_info = svc.add_rss_subscribe(**kwargs)

    rssid = None
    if media_info:
        rssid = svc.get_subscribe_id(mtype=kwargs["mtype"], title=req.name or "", tmdbid=media_info.tmdb_id)

    return success(
        data={
            "msg": msg,
            "page": req.page,
            "name": req.name,
            "rssid": rssid,
        }
    )


@router.post("/update", response_model=CommonResponse, summary="更新 RSS 订阅")
def update_rss_media(
    req: AddRssMediaRequest,
    user: str = Depends(require_permission("subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    kwargs = _build_update_kwargs(req)
    code = 0
    msg = ""
    media_info = None
    season = req.season
    if not req.rssid:
        return fail(code=-1, msg="缺少订阅ID", page=req.page, name=req.name, rssid=None)

    if isinstance(season, list):
        for sea in season:
            kwargs["season"] = sea
            kwargs.pop("total_ep", None)
            kwargs.pop("current_ep", None)
            code, msg, media_info = svc.update_rss_subscribe(**kwargs)
            if code != 0:
                break
    else:
        kwargs["season"] = season
        kwargs["total_ep"] = req.total_ep
        kwargs["current_ep"] = req.current_ep
        code, msg, media_info = svc.update_rss_subscribe(**kwargs)

    return fail(code=code, msg=msg, page=req.page, name=req.name, rssid=req.rssid)


@router.post("/history/delete", response_model=CommonResponse, summary="删除 RSS 历史")
def delete_rss_history(
    req: SubscribeIdRequest,
    user: str = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    svc.delete(rssid=req.rssid or "")
    return success()


@router.post("/history/redo", response_model=CommonResponse, summary="重新执行 RSS 历史")
def re_rss_history(
    req: RedoHistoryRequest,
    user: str = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    parsed = MediaType.from_string(req.type or "")
    rtype = MediaType.MOVIE.value if parsed == MediaType.MOVIE else MediaType.TV.value
    code, msg = svc.redo(rssid=req.rssid or "", rtype=rtype)
    return fail(code=code, msg=msg)


@router.post("/refresh", response_model=CommonResponse, summary="刷新 RSS 订阅")
def refresh_rss(
    req: RefreshRssRequest,
    user: str = Depends(require_permission("subscription:manage")),
):
    container.subscription_monitor().refresh_subscription(mtype=req.type or "", rssid=req.rssid or "")
    return success(data=req.page)


@router.post("/remove", response_model=CommonResponse, summary="移除 RSS 订阅")
def remove_rss_media(
    req: RemoveRssMediaRequest,
    user: str = Depends(require_any_permission("subscription:manage", "subscription:view")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    tmdbid = req.tmdbid
    if not str(tmdbid).isdigit():
        tmdbid = None
    name = req.name
    if name:
        name = meta_info(title=name).get_name()
    mtype = req.type
    if MediaType.from_string(mtype or "") == MediaType.MOVIE:
        svc.delete_subscribe(
            mtype=MediaType.MOVIE,
            title=name or "",
            year=req.year,
            rssid=int(req.rssid) if req.rssid else None,
            tmdbid=tmdbid,
        )
    else:
        svc.delete_subscribe(
            mtype=MediaType.TV,
            title=name or "",
            season=str(req.season) if req.season is not None else None,
            rssid=int(req.rssid) if req.rssid else None,
            tmdbid=tmdbid,
        )
    return success(data=req.page)


@router.post("/detail", response_model=CommonResponse, summary="获取 RSS 订阅详情")
def rss_detail(
    req: SubscribeDetailRequest,
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    parsed = MediaType.from_string(req.rsstype or "")
    if parsed == MediaType.MOVIE:
        rssdetail = svc.get_subscribe_movies(rid=int(req.rssid) if req.rssid else None)
        if not rssdetail:
            return fail()
        detail = list(rssdetail.values())[0]
        detail["type"] = MediaType.MOVIE.value
    elif parsed == MediaType.ANIME:
        rssdetail = svc.get_subscribe_tvs(rid=int(req.rssid) if req.rssid else None)
        if not rssdetail:
            return fail()
        detail = list(rssdetail.values())[0]
        detail["type"] = MediaType.ANIME.value
    else:
        rssdetail = svc.get_subscribe_tvs(rid=int(req.rssid) if req.rssid else None)
        if not rssdetail:
            return fail()
        detail = list(rssdetail.values())[0]
        detail["type"] = MediaType.TV.value
    return success(data=detail)


@router.post("/default_setting", response_model=CommonResponse, summary="获取默认 RSS 设置")
def get_default_rss_setting(
    req: GetDefaultSubscribeSettingRequest,
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    parsed = MediaType.from_string(req.mtype or "")
    if parsed in (MediaType.TV, MediaType.ANIME):
        setting = svc.default_subscribe_setting_tv
    elif parsed == MediaType.MOVIE:
        setting = svc.default_subscribe_setting_mov
    else:
        setting = {}
    if setting:
        return success(data=setting)
    return fail()


@router.post("/default_setting/save", response_model=CommonResponse, summary="保存默认 RSS 设置")
def save_default_rss_setting(
    req: DefaultSubscribeSettingSaveRequest,
    user: str = Depends(require_permission("subscription:manage")),
):
    mtype = req.mtype
    data = req.model_dump()
    data.pop("mtype", None)
    parsed = MediaType.from_string(mtype or "")
    if parsed == MediaType.TV:
        container.system_config().set(key=SystemConfigKey.DefaultSubscribeSettingTV, value=data)
    elif parsed == MediaType.MOVIE:
        container.system_config().set(key=SystemConfigKey.DefaultSubscribeSettingMOV, value=data)
    return success()


@router.post("/calendar/ical", response_model=CommonResponse, summary="获取 RSS 日历事件")
def get_ical_events(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    events = svc.get_events()
    return success(data=events)


@router.post("/movie/items", response_model=CommonResponse, summary="获取电影 RSS 订阅项")
def get_movie_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    return success(data=svc.get_movie_items())


@router.post("/movie/list", response_model=CommonResponse, summary="获取电影 RSS 订阅列表")
def get_movie_rss_list(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    result = svc.get_subscribe_movies()
    return success(data=list(result.values()) if isinstance(result, dict) else result)


@router.post("/history", response_model=CommonResponse, summary="获取 RSS 历史")
def get_rss_history(
    req: GetSubscribeHistoryRequest,
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    parsed = MediaType.from_string(req.type or "")
    mtype = MediaType.MOVIE.value if parsed == MediaType.MOVIE else MediaType.TV.value
    return success(data=svc.get_history(mtype=mtype))


@router.post("/tv/items", response_model=CommonResponse, summary="获取电视剧 RSS 订阅项")
def get_tv_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    return success(data=svc.get_tv_items())


@router.post("/tv/list", response_model=CommonResponse, summary="获取电视剧 RSS 订阅列表")
def get_tv_rss_list(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    result = svc.get_subscribe_tvs()
    return success(data=list(result.values()) if isinstance(result, dict) else result)


@router.post("/history/clear", response_model=CommonResponse, summary="清空 RSS 历史")
def truncate_rsshistory(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    svc.truncate()
    return success()
