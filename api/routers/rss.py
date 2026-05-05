"""
RSS Router — FastAPI 迁移
对应原 web/controllers/rss.py，复用 app/services/rss_service.py
"""
from typing import Optional, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_rss_subscription_service, require_any_permission, require_permission
from app.utils.response import success, fail
from app.services.rss_service import RssSubscriptionService
from app.conf.systemconfig import SystemConfig
from app.utils.types import SystemConfigKey

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: Optional[dict] = None


class AddRssMediaRequest(BaseModel):
    name: Optional[str] = None
    year: Optional[str] = None
    season: Optional[str] = None
    type: Optional[str] = None
    page: Optional[str] = None
    rssid: Optional[str] = None
    in_form: Optional[str] = None
    keyword: Optional[str] = None
    fuzzy_match: Optional[bool] = None
    mediaid: Optional[Union[str, int]] = None
    rss_sites: Optional[list] = None
    search_sites: Optional[list] = None
    over_edition: Optional[bool] = None
    filter_restype: Optional[str] = None
    filter_pix: Optional[str] = None
    filter_team: Optional[str] = None
    filter_rule: Optional[str] = None
    filter_include: Optional[str] = None
    filter_exclude: Optional[str] = None
    save_path: Optional[str] = None
    download_setting: Optional[str] = None
    total_ep: Optional[int] = None
    current_ep: Optional[int] = None
    image: Optional[str] = None
    tmdbid: Optional[Union[str, int]] = None


class RssidRequest(BaseModel):
    rssid: Optional[str] = None


class ReRssHistoryRequest(BaseModel):
    rssid: Optional[str] = None
    type: Optional[str] = None


class RefreshRssRequest(BaseModel):
    type: Optional[str] = None
    rssid: Optional[str] = None
    page: Optional[str] = None


class RemoveRssMediaRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    year: Optional[str] = None
    season: Optional[str] = None
    rssid: Optional[str] = None
    tmdbid: Optional[str] = None
    page: Optional[str] = None


class RssDetailRequest(BaseModel):
    rssid: Optional[str] = None
    rsstype: Optional[str] = None


class GetDefaultRssSettingRequest(BaseModel):
    mtype: Optional[str] = None


class DefaultRssSettingSaveRequest(BaseModel):
    mtype: Optional[str] = None
    over_edition: Optional[str] = None
    restype: Optional[str] = None
    pix: Optional[str] = None
    team: Optional[str] = None
    rule: Optional[str] = None
    include: Optional[str] = None
    exclude: Optional[str] = None
    download_setting: Optional[str] = None
    rss_sites: Optional[list] = None
    search_sites: Optional[list] = None


class GetRssHistoryRequest(BaseModel):
    type: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/add")
def add_rss_media(
    req: AddRssMediaRequest,
    user: str = Depends(require_any_permission("rss:manage", "rss:view")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.add_rss_media(req.model_dump())
    return success(data={
        "msg": result.msg,
        "page": req.page,
        "name": req.name,
        "rssid": result.rssid,
    })


@router.post("/update")
def update_rss_media(
    req: AddRssMediaRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.update_rss_media(req.model_dump())
    return fail(code=result.code, msg=result.msg,
                page=req.page, name=req.name, rssid=result.rssid)


@router.post("/history/delete")
def delete_rss_history(
    req: RssidRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.delete_rss_history(rssid=req.rssid)
    return success()


@router.post("/history/redo")
def re_rss_history(
    req: ReRssHistoryRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    code, msg = svc.re_rss_history(
        rssid=req.rssid, rtype=req.type)
    return fail(code=code, msg=msg)


@router.post("/refresh")
def refresh_rss(
    req: RefreshRssRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.refresh_rss(
        mtype=req.type, rssid=req.rssid)
    return success(data=req.page)


@router.post("/remove")
def remove_rss_media(
    req: RemoveRssMediaRequest,
    user: str = Depends(require_any_permission("rss:manage", "rss:view")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.remove_rss_media(
        name=req.name,
        mtype=req.type,
        year=req.year,
        season=req.season,
        rssid=req.rssid,
        tmdbid=req.tmdbid)
    return success(data=req.page)


@router.post("/detail")
def rss_detail(
    req: RssDetailRequest,
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.get_rss_detail(
        rid=req.rssid, rsstype=req.rsstype)
    if not result:
        return fail()
    return success(data=result.detail)


@router.post("/default_setting")
def get_default_rss_setting(
    req: GetDefaultRssSettingRequest,
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    setting = svc.get_default_rss_setting(
        mtype=req.mtype)
    if setting:
        return success(data=setting)
    return fail()


@router.post("/default_setting/save")
def save_default_rss_setting(
    req: DefaultRssSettingSaveRequest,
    user: str = Depends(require_permission("rss:manage")),
):
    mtype = req.mtype
    data = req.model_dump()
    data.pop("mtype", None)
    if mtype == "TV":
        SystemConfig().set(key=SystemConfigKey.DefaultRssSettingTV, value=data)
    elif mtype == "MOV":
        SystemConfig().set(key=SystemConfigKey.DefaultRssSettingMOV, value=data)
    return success()


@router.post("/calendar/ical")
def get_ical_events(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    events = svc.get_ical_events()
    return success(data=events)


@router.post("/movie/items")
def get_movie_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    return success(data=svc.get_movie_rss_items())


@router.post("/movie/list")
def get_movie_rss_list(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.get_movie_rss_list()
    return success(data=list(result.values()) if isinstance(result, dict) else result)


@router.post("/history")
def get_rss_history(
    req: GetRssHistoryRequest,
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    return success(data=svc.get_rss_history( mtype=req.type))


@router.post("/tv/items")
def get_tv_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    return success(data=svc.get_tv_rss_items())


@router.post("/tv/list")
def get_tv_rss_list(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.get_tv_rss_list()
    return success(data=list(result.values()) if isinstance(result, dict) else result)


@router.post("/history/clear")
def truncate_rsshistory(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.truncate_rss_history()
    return success()
