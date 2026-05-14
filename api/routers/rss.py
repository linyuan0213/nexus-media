"""
RSS Router — FastAPI 迁移
对应原 web/controllers/rss.py，复用 app/services/rss_service.py
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_rss_subscription_service, require_any_permission, require_permission
from app.core.system_config import SystemConfig
from app.services.rss_service import RssSubscriptionService
from app.utils.response import fail, success
from app.utils.types import SystemConfigKey

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


class RssidRequest(BaseModel):
    rssid: str | None = None


class ReRssHistoryRequest(BaseModel):
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


class RssDetailRequest(BaseModel):
    rssid: str | None = None
    rsstype: str | None = None


class GetDefaultRssSettingRequest(BaseModel):
    mtype: str | None = None


class DefaultRssSettingSaveRequest(BaseModel):
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


class GetRssHistoryRequest(BaseModel):
    type: str | None = None


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
    return success(
        data={
            "msg": result.msg,
            "page": req.page,
            "name": req.name,
            "rssid": result.rssid,
        }
    )


@router.post("/update")
def update_rss_media(
    req: AddRssMediaRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.update_rss_media(req.model_dump())
    return fail(code=result.code, msg=result.msg, page=req.page, name=req.name, rssid=result.rssid)


@router.post("/history/delete")
def delete_rss_history(
    req: RssidRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.delete_rss_history(rssid=req.rssid or "")
    return success()


@router.post("/history/redo")
def re_rss_history(
    req: ReRssHistoryRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    code, msg = svc.re_rss_history(rssid=req.rssid or "", rtype=req.type or "")
    return fail(code=code, msg=msg)


@router.post("/refresh")
def refresh_rss(
    req: RefreshRssRequest,
    user: str = Depends(require_permission("rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.refresh_rss(mtype=req.type or "", rssid=req.rssid or "")
    return success(data=req.page)


@router.post("/remove")
def remove_rss_media(
    req: RemoveRssMediaRequest,
    user: str = Depends(require_any_permission("rss:manage", "rss:view")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    svc.remove_rss_media(
        name=req.name or "", mtype=req.type or "", year=req.year or "", season=int(req.season) if req.season else None, rssid=req.rssid, tmdbid=req.tmdbid
    )
    return success(data=req.page)


@router.post("/detail")
def rss_detail(
    req: RssDetailRequest,
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    result = svc.get_rss_detail(rid=req.rssid or "", rsstype=req.rsstype or "")
    if not result:
        return fail()
    return success(data=result.detail)


@router.post("/default_setting")
def get_default_rss_setting(
    req: GetDefaultRssSettingRequest,
    user: str = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: RssSubscriptionService = Depends(get_rss_subscription_service),
):
    setting = svc.get_default_rss_setting(mtype=req.mtype or "")
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
    return success(data=svc.get_rss_history(mtype=req.type or ""))


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
