"""
Site Router — FastAPI 迁移
对应原 web/controllers/site.py，复用 app/services/site_service.py
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_site_service, require_any_permission, require_permission
from app.services.site_service import SiteService
from app.utils.response import fail, success

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class SiteIdRequest(BaseModel):
    id: str | None = None


class SiteUrlRequest(BaseModel):
    url: str | None = None


class SiteNameRequest(BaseModel):
    name: str | None = None


class SiteDaysRequest(BaseModel):
    days: int | None = None
    end_day: str | None = None


class SiteUpdateRequest(BaseModel):
    site_id: str | None = None
    site_name: str | None = None
    site_pri: str | None = None
    site_rssurl: str | None = None
    site_signurl: str | None = None
    site_cookie: str | None = None
    site_note: str | None = None
    site_include: str | None = None


class SiteCookieUaRequest(BaseModel):
    site_id: str | None = None
    site_cookie: str | None = None
    site_ua: str | None = None


class SiteFilterRequest(BaseModel):
    rss: bool | None = False
    brush: bool | None = False
    statistic: bool | None = False
    basic: bool | None = False


class SiteCaptchaRequest(BaseModel):
    code: str | None = None
    value: str | None = None


class SiteUserStatisticsRequest(BaseModel):
    sites: list | None = None
    encoding: str | None = "RAW"
    sort_by: str | None = None
    sort_on: str | None = None
    site_hash: str | None = None


class SiteResourcesRequest(BaseModel):
    id: str | None = None
    page: int | None = None
    keyword: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sites/check_attr")
def check_site_attr(
    req: SiteUrlRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.check_site_attr(req.url)
    return success(data={"site_free": dto.site_free, "site_2xfree": dto.site_2xfree, "site_hr": dto.site_hr})


@router.post("/sites/delete")
def del_site(
    req: SiteIdRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    tid = req.id
    if tid:
        ret = svc.delete_site(tid)
        return fail(code=ret or 0)
    return success()


@router.post("/sites/detail")
def get_site(
    req: SiteIdRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.get_site(req.id)
    return success(
        data={"site": dto.site, "site_free": dto.site_free, "site_2xfree": dto.site_2xfree, "site_hr": dto.site_hr}
    )


@router.post("/sites/activity")
def get_site_activity(
    req: SiteNameRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    if not req.name:
        return fail(msg="查询参数错误")
    dto = svc.get_site_activity(req.name)
    return success(data={"dataset": dto.dataset})


@router.post("/sites/favicon")
def get_site_favicon(
    req: SiteNameRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    return success(data=svc.get_site_favicon(req.name))


@router.post("/sites/history")
def get_site_history(
    req: SiteDaysRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    if req.days is None or not isinstance(req.days, int):
        return fail(msg="查询参数错误")
    dto = svc.get_site_history(days=req.days, end_day=req.end_day)
    return success(data={"dataset": dto.dataset})


@router.post("/sites/statistics/daily")
def get_site_daily_history(
    req: SiteDaysRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    if req.days is None or not isinstance(req.days, int):
        return fail(msg="查询参数错误")
    result = svc.get_site_daily_history(days=req.days, end_day=req.end_day)
    return success(data=result)


@router.post("/sites/seeding")
def get_site_seeding_info(
    req: SiteNameRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    if not req.name:
        return fail(msg="查询参数错误")
    dto = svc.get_site_seeding_info(req.name)
    return success(data={"dataset": dto.dataset})


class SiteRefreshRequest(BaseModel):
    sites: list | None = None


@router.post("/sites/statistics/refresh")
def refresh_site_statistics(
    req: SiteRefreshRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    from app.helper import ThreadHelper

    ThreadHelper().start_thread(svc.refresh_site_data_now, (req.sites,))
    return success(data={"message": "站点数据刷新已启动，请稍候"})


@router.post("/sites")
def get_sites(
    req: SiteFilterRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    sites = svc.get_sites(
        rss=bool(req.rss), brush=bool(req.brush), statistic=bool(req.statistic), basic=bool(req.basic)
    )
    return success(data=sites)


@router.post("/sites/captcha")
def set_site_captcha_code(
    req: SiteCaptchaRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    svc.set_captcha_code(code=req.code or "", value=req.value or "")
    return success()


@router.post("/sites/test")
def test_site(
    req: SiteIdRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.test_site(req.id or "")
    return fail(code=dto.code, msg=dto.msg, time=dto.times)


@router.post("/sites/update")
def update_site(
    req: SiteUpdateRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.update_site(req.model_dump())
    return fail(code=dto.code or 0, msg=dto.msg or "")


@router.post("/sites/cookie_ua")
def update_site_cookie_ua(
    req: SiteCookieUaRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    svc.update_site_cookie_ua(siteid=req.site_id or "", cookie=req.site_cookie or "", ua=req.site_ua or "")
    return success(data={"messages": "请求发送成功"})


@router.post("/sites/statistics")
def get_site_user_statistics(
    req: SiteUserStatisticsRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    # 强制使用 DICT 编码，确保返回可序列化的字典格式
    statistics = svc.get_site_user_statistics(
        sites=req.sites, encoding="DICT", sort_by=req.sort_by, sort_on=req.sort_on, site_hash=req.site_hash
    )
    return success(data=statistics)


@router.post("/sites/resources")
def list_site_resources(
    req: SiteResourcesRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    resources = svc.list_site_resources(index_id=int(req.id or 0), page=req.page or 1, keyword=req.keyword or "")
    if not resources.success:
        return fail(msg=resources.msg)
    return success(data=resources.data)
