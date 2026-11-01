"""
Subscription Router — FastAPI 迁移
对应原 web/controllers/rss.py，调用 subscribe/ 领域服务
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from api.deps import (
    get_apikey_service,
    get_app_context,
    get_current_user,
    get_subscribe_calendar_service,
    get_subscribe_history_service,
    get_subscribe_service,
    get_subscription_monitor,
    get_system_config_service,
    require_any_permission,
    require_permission,
)
from app.core.error_codes import ErrorCode
from app.core.system_config import SystemConfig
from app.domain.entities.custom_rss import custom_rss_id
from app.domain.enums import SystemConfigKey
from app.domain.media_type_utils import MediaTypeMapper
from app.domain.mediatypes import MediaType, normalize_media_type_input
from app.media import meta_info
from app.media.metadata.registry import registry as metadata_registry
from app.schemas.auth import UserContext
from app.schemas.common import CommonResponse
from app.services.apikey_service import APIKeyService
from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.management.service import SubscribeService
from app.services.subscribe.monitor import SubscriptionMonitor
from app.utils.response import fail, success

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class MovieListRequest(BaseModel):
    user_id: int | None = None
    content_profile: str | None = None


class EmptyRequest(BaseModel):
    data: dict | None = None
    user_id: int | None = None  # superadmin 按归属用户过滤订阅列表
    content_profile: str | None = None


class AddRssMediaRequest(BaseModel):
    name: str | None = None
    year: str | None = None
    season: str | None = None
    type: str | None = None
    page: str | None = None
    rssid: int | None = None
    in_form: str | None = None
    keyword: str | None = None
    fuzzy_match: bool | None = None
    mediaid: str | int | None = None
    metadata_ref: str | None = None
    provider: str | None = None
    anchor_provider: str | None = None
    anchor_external_id: str | None = None
    identity_id: str | None = None
    rss_sites: list | None = None
    search_sites: list | None = None
    over_edition: bool | None = None
    filter_restype: str | None = None
    filter_pix: str | None = None
    filter_team: str | None = None
    filter_rule: str | None = None
    filter_include: str | None = None
    filter_exclude: str | None = None
    filter_free: bool | None = None
    save_path: str | None = None
    download_setting: str | None = None
    total_ep: int | None = None
    current_ep: int | None = None
    image: str | None = None
    metadata_policy: str | None = None
    content_profile: str | None = None
    naming_profile: str | None = None


class SubscribeIdRequest(BaseModel):
    rssid: int | None = None


class RedoHistoryRequest(BaseModel):
    rssid: int | None = None
    type: str | None = None
    content_profile: str | None = None


class RefreshRssRequest(BaseModel):
    type: str | None = None
    rssid: int | None = None
    page: str | None = None
    content_profile: str | None = None


class RemoveRssMediaRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    year: str | None = None
    season: str | None = None
    rssid: int | None = None
    anchor_provider: str | None = None
    anchor_external_id: str | None = None
    page: str | None = None
    content_profile: str | None = None


class SubscribeDetailRequest(BaseModel):
    rssid: int | None = None
    rsstype: str | None = None
    content_profile: str | None = None


class SubscribeSeasonsRequest(BaseModel):
    name: str | None = None
    year: str | None = None
    anchor_provider: str | None = None
    anchor_external_id: str | None = None


class GetDefaultSubscribeSettingRequest(BaseModel):
    mtype: str | None = None
    content_profile: str | None = None


class DefaultSubscribeSettingSaveRequest(BaseModel):
    mtype: str | None = None
    content_profile: str | None = None
    over_edition: str | None = None
    restype: str | None = None
    pix: str | None = None
    team: str | None = None
    rule: str | None = None
    include: str | None = None
    exclude: str | None = None
    free: bool | None = None
    download_setting: str | None = None
    rss_sites: list | None = None
    search_sites: list | None = None


class GetSubscribeHistoryRequest(BaseModel):
    type: str | None = None
    content_profile: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_type_and_profile(type_str: str | None, content_profile: str | None) -> tuple[MediaType, str]:
    """统一解析展示类型与内容画像：支持 av 等插件展示别名，未知类型回退到载体默认."""
    normalized, profile = normalize_media_type_input(type_str, content_profile)
    parsed = MediaType.from_string(normalized or "")
    if parsed in (MediaType.MOVIE, MediaType.TV, MediaType.ANIME):
        return parsed, profile
    if profile not in ("", "default"):
        return MediaType.MOVIE, profile
    return MediaType.TV, profile


def _resolve_mtype(type_str: str | None) -> MediaType:
    """兼容旧调用：仅解析载体媒体类型。"""
    return _resolve_type_and_profile(type_str, None)[0]


def _build_add_kwargs(req: AddRssMediaRequest) -> dict:
    mtype, profile = _resolve_type_and_profile(req.type, req.content_profile)
    channel = "R" if req.in_form == "manual" else "D"
    return {
        "mtype": mtype,
        "name": req.name,
        "year": req.year,
        "channel": channel,
        "keyword": req.keyword,
        "fuzzy_match": req.fuzzy_match,
        "mediaid": req.mediaid,
        "metadata_ref": req.metadata_ref,
        "provider": req.provider,
        "rss_sites": req.rss_sites,
        "search_sites": req.search_sites,
        "over_edition": req.over_edition,
        "filter_restype": req.filter_restype,
        "filter_pix": req.filter_pix,
        "filter_team": req.filter_team,
        "filter_rule": req.filter_rule,
        "filter_include": req.filter_include,
        "filter_exclude": req.filter_exclude,
        "filter_free": req.filter_free,
        "image": req.image,
        "save_path": req.save_path,
        "download_setting": req.download_setting,
        "metadata_policy": req.metadata_policy,
        "content_profile": profile,
        "naming_profile": req.naming_profile,
    }


def _build_update_kwargs(req: AddRssMediaRequest) -> dict:
    mtype, profile = _resolve_type_and_profile(req.type, req.content_profile)
    return {
        "mtype": mtype,
        "rssid": req.rssid,
        "name": req.name,
        "year": req.year,
        "keyword": req.keyword,
        "fuzzy_match": req.fuzzy_match,
        "mediaid": req.mediaid,
        "metadata_ref": req.metadata_ref,
        "provider": req.provider,
        "content_profile": profile,
        "metadata_policy": req.metadata_policy,
        "naming_profile": req.naming_profile,
        "rss_sites": req.rss_sites,
        "search_sites": req.search_sites,
        "over_edition": req.over_edition,
        "filter_restype": req.filter_restype,
        "filter_pix": req.filter_pix,
        "filter_team": req.filter_team,
        "filter_rule": req.filter_rule,
        "filter_include": req.filter_include,
        "filter_exclude": req.filter_exclude,
        "filter_free": req.filter_free,
        "image": req.image,
        "save_path": req.save_path,
        "download_setting": req.download_setting,
    }


def _normalize_season(season) -> str | None:
    """将季号统一为数据库存储格式 "S01"。

    前端传入的季号为纯数字（如 "1"、2），而数据库 SEASON 字段存储为 "S01"。
    """
    if season is None:
        return None
    s = str(season).strip()
    if not s:
        return None
    if s.upper().startswith("S"):
        return s.upper()
    if s.isdigit():
        return f"S{int(s):02d}"
    return s


def _invoke_for_seasons(
    season,
    kwargs: dict,
    invoke,
    total_ep=None,
    current_ep=None,
):
    """按季列表或单季调用 subscribe 方法，返回 (code, msg, media_info)."""
    code = 0
    msg = ""
    media_info = None
    if isinstance(season, list):
        for sea in season:
            kwargs["season"] = sea
            kwargs.pop("total_ep", None)
            kwargs.pop("current_ep", None)
            code, msg, media_info = invoke(**kwargs)
            if code != 0:
                break
    else:
        kwargs["season"] = season
        if total_ep is not None:
            kwargs["total_ep"] = total_ep
        if current_ep is not None:
            kwargs["current_ep"] = current_ep
        code, msg, media_info = invoke(**kwargs)
    return code, msg, media_info


def _scoped_user(user: UserContext, target_user_id: int | None) -> UserContext:
    """superadmin 可通过 user_id 过滤查看指定用户订阅；普通用户忽略该参数（行级过滤兜底）"""
    if target_user_id and user.is_superadmin:
        return user.model_copy(update={"user_id": target_user_id, "role_codes": []})
    return user


def _check_site_grants(app_context, user: UserContext, kwargs: dict) -> list[str]:
    """校验订阅站点白名单：rss_sites 需 rss 用途、search_sites 需 search 用途。

    返回未授权站点名列表（空列表=通过）。open 策略或 superadmin 直接通过。
    """
    denied: list[str] = []
    custom_service = getattr(app_context, "custom_rss_service", None)
    for site in kwargs.get("rss_sites") or []:
        if custom_rss_id(site) is not None and (custom_service is None or not custom_service.can_use_ref(user, site)):
            denied.append(site)
    for site in kwargs.get("search_sites") or []:
        if custom_rss_id(site) is not None:
            denied.append(site)

    grant_service = getattr(app_context, "site_grant_service", None)
    if grant_service is None:
        return denied
    visible = grant_service.get_visible_sites(user)
    if visible is None:
        return denied
    for site in kwargs.get("rss_sites") or []:
        if custom_rss_id(site) is None and not grant_service.is_site_name_allowed(visible, site, usage="rss"):
            denied.append(site)
    for site in kwargs.get("search_sites") or []:
        if custom_rss_id(site) is None and not grant_service.is_site_name_allowed(visible, site, usage="search"):
            denied.append(site)
    return denied


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/add", response_model=CommonResponse, summary="添加 RSS 订阅")
def add_rss_media(
    req: AddRssMediaRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
    app_context=Depends(get_app_context),
):
    if req.anchor_provider and req.anchor_external_id and not req.metadata_ref:
        req.metadata_ref = f"{req.anchor_provider}:{req.anchor_external_id}"
    kwargs = _build_add_kwargs(req)
    kwargs["user_id"] = user.user_id
    permissions = set(getattr(user, "permissions", []) or [])
    allow_private = bool(getattr(user, "is_superadmin", False)) or "metadata:private:view" in permissions
    profile = str(kwargs.get("content_profile") or "").strip()
    # core 画像（default/anime）是公共能力；其余画像与 private provider 需要显式授权。
    provider_key = str(req.provider or "").strip().lower()
    if not provider_key:
        metadata_ref = str(req.metadata_ref or "")
        if ":" in metadata_ref:
            provider_key = metadata_ref.split(":", 1)[0].strip().lower()
    descriptor = getattr(metadata_registry.get_provider(provider_key), "descriptor", None) if provider_key else None
    private_provider = getattr(descriptor, "visibility", "public") == "private"
    if not allow_private and (private_provider or profile not in ("", "default", "anime")):
        return fail(msg="无权创建该内容画像的订阅")
    kwargs["allow_private"] = allow_private
    kwargs["permissions"] = None if getattr(user, "is_superadmin", False) else permissions
    denied = _check_site_grants(app_context, user, kwargs)
    if denied:
        return fail(
            code=ErrorCode.PARAM_VALIDATION_FAILED,
            msg=f"以下站点未授权给你: {', '.join(denied)}",
            page=req.page,
            name=req.name,
            rssid=None,
        )
    code, msg, media_info = _invoke_for_seasons(req.season, kwargs, svc.add_rss_subscribe, req.total_ep, req.current_ep)

    # code 0=成功, 9=订阅已存在(幂等)；其余为真实失败，需上报而非伪装成功
    if code not in (0, 9):
        return fail(
            code=ErrorCode.SUBSCRIPTION_FAILED,
            msg=msg,
            page=req.page,
            name=req.name,
            rssid=None,
        )

    rssid = None
    if media_info:
        rssid = svc.get_subscribe_id(
            mtype=kwargs["mtype"],
            title=req.name or "",
            tmdbid=media_info.tmdb_id,
            user_id=user.user_id,
            content_profile=kwargs.get("content_profile"),
        )

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
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
    app_context=Depends(get_app_context),
):
    kwargs = _build_update_kwargs(req)
    kwargs["user"] = user
    if not req.rssid:
        return fail(code=ErrorCode.PARAM_VALIDATION_FAILED, msg="缺少订阅ID", page=req.page, name=req.name, rssid=None)

    denied = _check_site_grants(app_context, user, kwargs)
    if denied:
        return fail(
            code=ErrorCode.PARAM_VALIDATION_FAILED,
            msg=f"以下站点未授权给你: {', '.join(denied)}",
            page=req.page,
            name=req.name,
            rssid=req.rssid,
        )

    code, msg, media_info = _invoke_for_seasons(
        req.season, kwargs, svc.update_rss_subscribe, req.total_ep, req.current_ep
    )

    if code == 0:
        return success(data={"page": req.page, "name": req.name, "rssid": req.rssid})
    return fail(
        code=ErrorCode.SUBSCRIPTION_FAILED,
        msg=msg,
        page=req.page,
        name=req.name,
        rssid=req.rssid,
    )


@router.post("/history/delete", response_model=CommonResponse, summary="删除 RSS 历史")
def delete_rss_history(
    req: SubscribeIdRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    svc.delete(rssid=req.rssid, user=user)
    return success()


@router.post("/history/redo", response_model=CommonResponse, summary="重新执行 RSS 历史")
def re_rss_history(
    req: RedoHistoryRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    mtype, profile = _resolve_type_and_profile(req.type, req.content_profile)
    # 动漫订阅历史存于电视剧表：按 to_tmdb 映射（ANIME -> tv），避免误判为电影
    rtype = MediaTypeMapper.to_tmdb(mtype) or MediaType.TV.value
    code, msg = svc.redo(rssid=req.rssid, rtype=rtype, user=user, content_profile=profile)
    if code == 0:
        return success(message=msg)
    return fail(code=ErrorCode.SUBSCRIPTION_FAILED, msg=msg)


@router.post("/refresh", response_model=CommonResponse, summary="刷新 RSS 订阅")
def refresh_rss(
    req: RefreshRssRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    monitor: SubscriptionMonitor = Depends(get_subscription_monitor),
):
    mtype, _profile = _resolve_type_and_profile(req.type, req.content_profile)
    monitor.refresh_subscription(mtype=mtype.value, rssid=req.rssid)
    return success(data=req.page)


@router.post("/remove", response_model=CommonResponse, summary="移除 RSS 订阅")
def remove_rss_media(
    req: RemoveRssMediaRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    name = req.name
    if name:
        name = meta_info(title=name).get_name()
    rssid = req.rssid
    mtype, _profile = _resolve_type_and_profile(req.type, req.content_profile)
    deleted = 0
    if rssid:
        deleted = int(svc.delete_subscribe(mtype=mtype, rssid=rssid, user=user) or 0)
        if deleted == 0 and not str(req.type or "").strip() and not str(req.content_profile or "").strip():
            # 只有调用方未指定类型时，才尝试另一张表。
            other = MediaType.TV if mtype == MediaType.MOVIE else MediaType.MOVIE
            deleted = int(svc.delete_subscribe(mtype=other, rssid=rssid, user=user) or 0)
    elif mtype == MediaType.MOVIE:
        deleted = int(
            svc.delete_subscribe(
                mtype=MediaType.MOVIE,
                title=name or "",
                year=req.year,
                rssid=rssid,
                tmdbid=None,
                user=user,
            )
            or 0
        )
    elif mtype in (MediaType.TV, MediaType.ANIME):
        # 动漫订阅存于电视剧表，删除同样走 TV
        deleted = int(
            svc.delete_subscribe(
                mtype=MediaType.TV,
                title=name or "",
                season=_normalize_season(req.season),
                rssid=rssid,
                tmdbid=None,
                user=user,
            )
            or 0
        )
    return success(data={"page": req.page, "deleted": deleted, "rssid": rssid})


@router.post("/detail", response_model=CommonResponse, summary="获取 RSS 订阅详情")
def rss_detail(
    req: SubscribeDetailRequest,
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    parsed, _profile = _resolve_type_and_profile(req.rsstype, req.content_profile)
    if parsed == MediaType.MOVIE:
        rssdetail = svc.get_subscribe_movies(rid=req.rssid, user=user)
        mtype_value = MediaType.MOVIE.value
    else:
        rssdetail = svc.get_subscribe_tvs(rid=req.rssid, user=user)
        mtype_value = MediaType.ANIME.value if parsed == MediaType.ANIME else MediaType.TV.value
    if not rssdetail:
        return fail()
    detail = list(rssdetail.values())[0]
    detail["type"] = mtype_value
    return success(data=detail)


@router.post("/default_setting", response_model=CommonResponse, summary="获取默认 RSS 设置")
def get_default_rss_setting(
    req: GetDefaultSubscribeSettingRequest,
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    parsed, profile = _resolve_type_and_profile(req.mtype, req.content_profile)
    if parsed in (MediaType.TV, MediaType.ANIME):
        setting = svc.default_subscribe_setting_tv
    elif parsed == MediaType.MOVIE:
        if profile and profile != "default":
            setting = SystemConfig().get(f"{SystemConfigKey.DefaultSubscribeSettingMOV.value}::{profile}") or {}
        else:
            setting = svc.default_subscribe_setting_mov
    else:
        setting = {}
    if setting:
        return success(data=setting)
    return success(data={})


@router.post("/default_setting/save", response_model=CommonResponse, summary="保存默认 RSS 设置")
def save_default_rss_setting(
    req: DefaultSubscribeSettingSaveRequest,
    user: UserContext = Depends(require_permission("subscription:manage")),
    cfg: SystemConfig = Depends(get_system_config_service),
):
    mtype = req.mtype
    data = req.model_dump()
    data.pop("mtype", None)
    profile = (data.pop("content_profile", None) or "").strip()
    parsed, profile = _resolve_type_and_profile(mtype, profile)
    # 动漫与电视剧共用一份默认设置（读取侧同样把 ANIME 归到 TV），否则动漫页保存会被静默丢弃
    if parsed in (MediaType.TV, MediaType.ANIME):
        cfg.set(key=SystemConfigKey.DefaultSubscribeSettingTV, value=data)
    elif parsed == MediaType.MOVIE and profile and profile != "default":
        cfg.set(key=f"{SystemConfigKey.DefaultSubscribeSettingMOV.value}::{profile}", value=data)
    elif parsed == MediaType.MOVIE:
        cfg.set(key=SystemConfigKey.DefaultSubscribeSettingMOV, value=data)
    return success()


@router.post("/calendar/ical", response_model=CommonResponse, summary="获取 RSS 日历事件")
def get_ical_events(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    events = svc.get_events(user=user)
    return success(data=events)


@router.post("/calendar/ical/download", summary="下载订阅日历 ICS 文件")
def download_ical(
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    ics = svc.generate_ics(user=user)
    return success(data=ics)


@router.get("/calendar/ical/webcal", summary="Webcal 订阅订阅日历")
def webcal_ical(
    request: Request,
    user: UserContext = Depends(get_current_user),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    ics = svc.generate_ics(user=user)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
    )


@router.get("/calendar/webcal_url", response_model=CommonResponse, summary="获取订阅日历 Webcal URL")
def get_webcal_url(
    request: Request,
    user: UserContext = Depends(get_current_user),
    apikey_service: APIKeyService = Depends(get_apikey_service),
):
    token = apikey_service.get_or_create_system_key("CalendarSubscription")
    return success(data={"token": token})


@router.post("/movie/items", response_model=CommonResponse, summary="获取电影 RSS 订阅项")
def get_movie_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    return success(data=svc.get_movie_items(user=user))


@router.post("/movie/list", response_model=CommonResponse, summary="获取电影 RSS 订阅列表")
def get_movie_rss_list(
    req: MovieListRequest = MovieListRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    result = svc.get_subscribe_movies(user=_scoped_user(user, req.user_id))
    items = list(result.values()) if isinstance(result, dict) else result
    profile = (req.content_profile or "").strip()
    if profile == "default":
        return success(data=[item for item in items if item.get("content_profile") in (None, "", "default")])
    if profile:
        return success(data=[item for item in items if item.get("content_profile") == profile])
    # 默认只返回默认内容画像；插件自定义画像由插件页面按 content_profile 查询
    return success(data=[item for item in items if item.get("content_profile") in (None, "", "default")])


@router.post("/count", response_model=CommonResponse, summary="获取订阅统计")
def get_subscription_count(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    return success(data=svc.get_subscription_count(user=_scoped_user(user, req.user_id)))


@router.post("/history", response_model=CommonResponse, summary="获取 RSS 历史")
def get_rss_history(
    req: GetSubscribeHistoryRequest,
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    parsed, profile = _resolve_type_and_profile(req.type, req.content_profile)
    mtype = MediaType.MOVIE.value if parsed == MediaType.MOVIE else MediaType.TV.value
    return success(data=svc.get_history(mtype=mtype, user=user, content_profile=profile))


@router.post("/tv/items", response_model=CommonResponse, summary="获取电视剧 RSS 订阅项")
def get_tv_rss_items(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeCalendarService = Depends(get_subscribe_calendar_service),
):
    return success(data=svc.get_tv_items(user=user))


@router.post("/tv/list", response_model=CommonResponse, summary="获取电视剧 RSS 订阅列表")
def get_tv_rss_list(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    result = svc.get_subscribe_tvs(user=_scoped_user(user, req.user_id))
    items = list(result.values()) if isinstance(result, dict) else result
    profile = (req.content_profile or "").strip()
    if profile == "default":
        return success(data=[item for item in items if item.get("content_profile") in (None, "", "default")])
    if profile:
        return success(data=[item for item in items if item.get("content_profile") == profile])
    return success(data=items)


@router.post("/tv/seasons", response_model=CommonResponse, summary="获取电视剧已订阅季列表")
def get_tv_subscribed_seasons(
    req: SubscribeSeasonsRequest,
    user: UserContext = Depends(require_any_permission("subscription:view", "subscription:manage")),
    svc: SubscribeService = Depends(get_subscribe_service),
):
    seasons = svc.get_subscribe_seasons(
        tmdbid=None,
        title=req.name,
        year=req.year,
        user=user,
    )
    return success(data={"seasons": seasons})


@router.post("/history/clear", response_model=CommonResponse, summary="清空 RSS 历史")
def truncate_rsshistory(
    req: EmptyRequest = EmptyRequest(),
    user: UserContext = Depends(require_permission("subscription:manage")),
    svc: SubscribeHistoryService = Depends(get_subscribe_history_service),
):
    svc.truncate(user=user)
    return success()
