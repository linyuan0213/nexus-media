"""
Site Router — FastAPI 迁移
对应原 web/controllers/site.py，复用 app/services/site_service.py
"""

import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import log
from api.deps import (
    get_app_context,
    get_current_user,
    get_indexer_service,
    get_site_service,
    require_any_permission,
    require_permission,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import DomainError, ServiceError  # noqa: F401
from app.db.repositories.indexer_site_config_repository import IndexerSiteConfigRepository
from app.indexer.contract.gateway import IndexerGateway
from app.indexer.contract.global_registry import get_global_registry
from app.indexer.contract.http import HttpIndexerProvider
from app.indexer.contract.models import IndexerQuery
from app.indexer.contract.site_catalog import external_indexer_sites
from app.infrastructure.thread import ThreadExecutor
from app.schemas.common import CommonResponse
from app.services.indexer_service import IndexerService
from app.services.site_parse_health_service import SiteParseHealthService
from app.services.site_service import SiteService
from app.sites.siteconf import SiteConf
from app.utils.response import fail, success

router = APIRouter()

# 解析自检后台运行状态（单实例进程内标记，防并发重复触发）
_PARSE_HEALTH_STATE = {"running": False, "lock": threading.Lock()}


def _build_parse_health_service(app_context) -> SiteParseHealthService:
    """基于应用上下文装配解析健康自检服务（无需注册到 DI 对象图）."""
    return SiteParseHealthService(
        site_cache=app_context.site_cache,
        siteconf=SiteConf(app_context.site_engine),
        message=app_context.message,
    )


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class SiteIdRequest(BaseModel):
    id: str | None = None


class SiteBatchTestRequest(BaseModel):
    ids: list[str] = []


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
    site_api_key: str | None = None
    site_bearer_token: str | None = None
    site_headers: str | None = None
    site_note: str | None = None
    site_include: str | None = None
    rss_enable: bool | None = None
    brush_enable: bool | None = None
    statistic_enable: bool | None = None


class SiteCookieUaRequest(BaseModel):
    site_id: str | None = None
    site_cookie: str | None = None
    site_ua: str | None = None


class SiteFilterRequest(BaseModel):
    rss: bool | None = False
    brush: bool | None = False
    statistic: bool | None = False
    basic: bool | None = False
    source: str | None = None


class SiteCaptchaRequest(BaseModel):
    code: str | None = None
    value: str | None = None


class SiteUserStatisticsRequest(BaseModel):
    sites: list | None = None
    encoding: str | None = "RAW"
    sort_by: str | None = None
    sort_on: str | None = None
    site_hash: str | None = None


class SiteApiCredentialsRequest(BaseModel):
    id: str


class SiteResourcesRequest(BaseModel):
    id: str | None = None
    page: int | None = None
    page_size: int | None = None
    keyword: str | None = None


class IndexerProviderTestRequest(BaseModel):
    base_url: str
    token: str | None = None
    timeout: float = 30
    info_path: str = "/api/indexer/info"


class IndexerSiteConfigUpdateRequest(BaseModel):
    site_name: str
    source: str | None = None
    enabled: bool | None = None
    download_setting: int | None = None
    priority: int | None = None
    default_settings: dict | None = None


class IndexerSiteConfigSyncRequest(BaseModel):
    client_id: str


class IndexerSiteConfigBatchRequest(BaseModel):
    sites: list[dict] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sites/check_attr", response_model=CommonResponse, summary="检查站点属性")
def check_site_attr(
    req: SiteUrlRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.check_site_attr(req.url)
    return success(data={"site_free": dto.site_free, "site_2xfree": dto.site_2xfree, "site_hr": dto.site_hr})


@router.post("/sites/delete", response_model=CommonResponse, summary="删除站点")
def del_site(
    req: SiteIdRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    tid = req.id
    if tid:
        ret = svc.delete_site(tid)
        if ret:
            return success()
        return fail(msg="删除失败")
    return fail(msg="站点ID不能为空")


@router.post("/sites/detail", response_model=CommonResponse, summary="获取站点详情")
def get_site(
    req: SiteIdRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    allowed = _allowed_site_names(user, app_context)
    if not _index_id_allowed(allowed, app_context, req.id):
        return fail(msg="无权查看该站点")
    dto = svc.get_site(req.id)
    return success(
        data={"site": dto.site, "site_free": dto.site_free, "site_2xfree": dto.site_2xfree, "site_hr": dto.site_hr}
    )


@router.post("/sites/activity", response_model=CommonResponse, summary="获取站点活跃度")
def get_site_activity(
    req: SiteNameRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    if not req.name:
        return fail(msg="查询参数错误")
    allowed = _allowed_site_names(user, app_context)
    if allowed is not None and req.name not in allowed:
        return fail(msg="无权查看该站点数据")
    dto = svc.get_site_activity(req.name)
    return success(data={"dataset": dto.dataset})


@router.post("/sites/favicon", response_model=CommonResponse, summary="获取站点图标")
def get_site_favicon(
    req: SiteNameRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    return success(data=svc.get_site_favicon(req.name))


@router.post("/sites/history", response_model=CommonResponse, summary="获取站点历史数据")
def get_site_history(
    req: SiteDaysRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    if req.days is None or not isinstance(req.days, int):
        return fail(msg="查询参数错误")
    dto = svc.get_site_history(days=req.days, end_day=req.end_day)
    allowed = _allowed_site_names(user, app_context)
    dataset = dto.dataset
    if allowed is not None and dataset:
        # dataset[0] 为表头 ["site","upload","download"]，按站点名过滤数据行
        dataset = [dataset[0], *[row for row in dataset[1:] if row and row[0] in allowed]]
    return success(data={"dataset": dataset})


@router.post("/sites/statistics/daily", response_model=CommonResponse, summary="获取站点日统计")
def get_site_daily_history(
    req: SiteDaysRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    if req.days is None or not isinstance(req.days, int):
        return fail(msg="查询参数错误")
    allowed = _allowed_site_names(user, app_context)
    result = svc.get_site_daily_history(days=req.days, end_day=req.end_day, allowed_sites=allowed)
    return success(data=result)


@router.post("/sites/seeding", response_model=CommonResponse, summary="获取站点做种信息")
def get_site_seeding_info(
    req: SiteNameRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    if not req.name:
        return fail(msg="查询参数错误")
    allowed = _allowed_site_names(user, app_context)
    if allowed is not None and req.name not in allowed:
        return fail(msg="无权查看该站点数据")
    dto = svc.get_site_seeding_info(req.name)
    return success(data={"dataset": dto.dataset})


class SiteRefreshRequest(BaseModel):
    sites: list | None = None


@router.post("/sites/statistics/refresh", response_model=CommonResponse, summary="刷新站点统计数据")
def refresh_site_statistics(
    req: SiteRefreshRequest,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    ThreadExecutor(name="site_refresh").submit(svc.refresh_site_data_now, req.sites)
    return success(data={"message": "站点数据刷新已启动，请稍候"})


@router.post("/sites/definitions", response_model=CommonResponse, summary="获取所有可添加的站点定义")
def get_site_definitions(
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    defs = svc.get_site_definitions()
    data = [
        {
            "id": d.id,
            "name": d.name,
            "domain": d.domain,
            "type": d.type,
            "public": d.public,
            "domain_aliases": d.domain_aliases,
            "encoding": d.encoding,
            "detail_page_url": d.detail_page_url,
        }
        for d in defs
    ]
    return success(data=data)


@router.get("/sites/indexer-providers", response_model=CommonResponse, summary="列出已注册索引器 provider")
def list_indexer_providers(
    _user=Depends(require_any_permission("site:view", "site:manage")),
):
    data = []
    for provider in get_global_registry().list():
        try:
            info = provider.info()
            data.append(
                {
                    "provider_id": info.provider_id,
                    "name": info.name,
                    "api_version": info.api_version,
                    "capabilities": list(info.capabilities),
                    "sites": [{"id": site.id, "name": site.name} for site in info.sites],
                    "health": provider.health().ok,
                }
            )
        except Exception as exc:  # noqa: BLE001
            data.append({"provider_id": provider.provider_id, "error": str(exc), "health": False})
    return success(data=data)


def _external_indexer_sites() -> list[dict]:
    sites = external_indexer_sites()
    settings = {(str(row.SOURCE), str(row.SITE_NAME)): row for row in IndexerSiteConfigRepository().list_all()}
    for site in sites:
        row = settings.get((str(site.get("source") or ""), str(site.get("name") or "")))
        if row is not None:
            site["enabled"] = bool(row.ENABLED)
            site["download_setting"] = row.DOWNLOAD_SETTING
    return sites


@router.post("/sites/indexer-providers/test", response_model=CommonResponse, summary="测试 HTTP 索引器连通性")
def test_indexer_provider(
    req: IndexerProviderTestRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
):
    base_url = req.base_url.strip()
    if not base_url:
        return fail(msg="索引器地址不能为空")
    provider = HttpIndexerProvider(
        base_url,
        token=req.token or None,
        timeout=float(req.timeout or 30),
        provider_id="test",
        info_path=req.info_path,
    )
    try:
        info = provider.info()
        return success(
            data={
                "ok": True,
                "name": info.name,
                "api_version": info.api_version,
                "capabilities": list(info.capabilities),
                "sites": [{"id": site.id, "name": site.name} for site in info.sites],
            }
        )
    except Exception as exc:  # noqa: BLE001
        return fail(msg=f"连接失败: {exc}")
    finally:
        provider.close()


@router.get("/sites/indexer-providers/search", response_model=CommonResponse, summary="调试索引器 provider 搜索")
def search_indexer_providers(
    keyword: str = "",
    limit: int = 5,
    _user=Depends(require_any_permission("site:view", "site:manage")),
):
    gateway = IndexerGateway(get_global_registry())
    page = gateway.search(IndexerQuery(keyword=keyword, limit=max(1, min(50, limit))))
    return success(
        data={
            "total": page.total,
            "items": [
                {
                    "provider_id": item.provider_id,
                    "site": item.site,
                    "site_name": item.site_name,
                    "item_id": item.item_id,
                    "title": item.title,
                }
                for item in page.items
            ],
            "warnings": page.warnings,
        }
    )


@router.post("/sites", response_model=CommonResponse, summary="获取站点列表")
def get_sites(
    req: SiteFilterRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    sites = svc.get_sites(
        rss=bool(req.rss),
        brush=bool(req.brush),
        statistic=bool(req.statistic),
        basic=bool(req.basic),
        source=req.source,
    )
    external_sites = _external_indexer_sites()
    if req.source:
        external_sites = [site for site in external_sites if site.get("source") == req.source]
    existing = {(str(site.get("source") or ""), str(site.get("name") or "")): site for site in sites}
    for external in external_sites:
        key = (str(external.get("source") or ""), str(external.get("name") or ""))
        current = existing.get(key)
        if current is not None:
            external["enabled"] = current.get("enabled", external["enabled"])
            external["download_setting"] = current.get("download_setting", external.get("download_setting"))
        sites.append(external)
    # 统一优先级：显式配置优先，内置回退站点自身 pri，第三方/插件默认 100
    priority_map = IndexerSiteConfigRepository().get_priority_map()
    for site in sites:
        source = str(site.get("source") or "builtin")
        name = str(site.get("name") or "")
        configured = priority_map.get(f"{source}:{name}")
        site["priority"] = (
            configured if configured is not None else int(site.get("pri") or 0) if source == "builtin" else 100
        )
    # 无站点管理权限的用户按站点授权过滤（ADR-021 4.3）
    grant_service = getattr(app_context, "site_grant_service", None)
    can_manage = user.is_superadmin or "site:manage" in user.permissions or "*" in user.permissions
    if grant_service is not None and not can_manage:
        visible = grant_service.get_visible_sites(user)
        if visible is not None:
            sites = [s for s in sites if grant_service.is_site_name_allowed(visible, s.get("name", ""), usage="search")]
    return success(data=sites)


@router.post("/sites/captcha", response_model=CommonResponse, summary="设置站点验证码")
def set_site_captcha_code(
    req: SiteCaptchaRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    svc.set_captcha_code(code=req.code or "", value=req.value or "")
    return success()


@router.post("/sites/test", response_model=CommonResponse, summary="测试站点连接")
def test_site(
    req: SiteIdRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.test_site(req.id or "")
    if dto.code == 0:
        return success(message=dto.msg, time=dto.times)
    return fail(code=ErrorCode.SITE_REQUEST_FAILED, msg=dto.msg, time=dto.times)


@router.post("/sites/test_batch", response_model=CommonResponse, summary="批量测试站点连接")
def test_sites_batch(
    req: SiteBatchTestRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    results = svc.test_sites_batch(req.ids or [])
    return success(data=results)


@router.post("/sites/update", response_model=CommonResponse, summary="更新站点配置")
def update_site(
    req: SiteUpdateRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    dto = svc.update_site(req.model_dump())
    if dto.code == 0:
        return success(message=dto.msg or "")
    return fail(code=ErrorCode.OPERATION_FAILED, msg=dto.msg or "")


@router.post("/sites/cookie_ua", response_model=CommonResponse, summary="更新站点 Cookie 和 UA")
def update_site_cookie_ua(
    req: SiteCookieUaRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    svc.update_site_cookie_ua(siteid=req.site_id or "", cookie=req.site_cookie or "", ua=req.site_ua or "")
    return success(data={"messages": "请求发送成功"})


@router.post("/sites/statistics", response_model=CommonResponse, summary="获取站点用户统计")
def get_site_user_statistics(
    req: SiteUserStatisticsRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    # 强制使用 DICT 编码，确保返回可序列化的字典格式
    allowed = _allowed_site_names(user, app_context)
    statistics = svc.get_site_user_statistics(
        sites=req.sites,
        encoding="DICT",
        sort_by=req.sort_by,
        sort_on=req.sort_on,
        site_hash=req.site_hash,
        allowed_sites=allowed,
    )
    return success(data=statistics)


def _provider_resources(index_id: str, keyword: str, page: int, page_size: int) -> dict:
    parts = index_id.split(":", 2)
    if len(parts) != 3:
        raise ValueError("无效的 provider 站点 id")
    _, provider_id, site_id = parts
    provider = get_global_registry().get(provider_id)
    if provider is None:
        raise ValueError("索引器 provider 未注册")
    query = IndexerQuery(
        keyword=keyword or None,
        sites=(site_id,),
        offset=max(0, page) * page_size,
        limit=page_size,
    )
    result = provider.search(query) if keyword else provider.list(query)
    return {
        "list": [
            {
                "id": item.item_id,
                "indexer": item.site_name or item.site,
                "title": item.title,
                "description": item.description,
                "size": item.size_bytes,
                "seeders": item.seeders or 0,
                "leechers": item.peers or 0,
                "pubdate": item.published_at,
                "labels": [],
                "enclosure": item.download_url or item.magnet or item.ed2k or "",
                "page_url": item.detail_url,
            }
            for item in result.items
        ],
        "has_more": result.has_more,
        "total": result.total,
    }


@router.post("/sites/api-credentials", response_model=CommonResponse, summary="读取站点 API 凭据")
def get_site_api_credentials(
    req: SiteApiCredentialsRequest,
    user: str = Depends(require_permission("site:manage")),
    svc: SiteService = Depends(get_site_service),
):
    try:
        return success(data=svc.get_site_api_credentials(int(req.id)))
    except (TypeError, ValueError):
        return fail(msg="无效的站点 id")


@router.post("/sites/resources", response_model=CommonResponse, summary="获取站点资源列表")
def list_site_resources(
    req: SiteResourcesRequest,
    user=Depends(require_any_permission("site:view", "site:manage")),
    svc: SiteService = Depends(get_site_service),
    app_context=Depends(get_app_context),
):
    allowed = _allowed_site_names(user, app_context)
    if not _index_id_allowed(allowed, app_context, req.id):
        return fail(msg="无权查看该站点资源")
    if str(req.id or "").startswith("provider:"):
        try:
            return success(
                data=_provider_resources(
                    str(req.id),
                    str(req.keyword or ""),
                    int(req.page or 0),
                    int(req.page_size or 100),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return fail(msg=str(exc))
    resources = svc.list_site_resources(
        index_id=req.id or "",
        page=req.page or 0,
        page_size=req.page_size or 100,
        keyword=req.keyword or "",
    )
    if not resources.success:
        return fail(msg=resources.msg)
    return success(data=resources.data)


@router.post("/sites/indexer-config/update", response_model=CommonResponse, summary="更新第三方站点配置")
def update_indexer_site_config(
    req: IndexerSiteConfigUpdateRequest,
    user: str = Depends(require_permission("site:manage")),
    idx_svc: IndexerService = Depends(get_indexer_service),
):
    if req.enabled is not None:
        idx_svc.update_site_enabled(req.site_name, req.enabled, source=req.source)
    if req.download_setting is not None:
        idx_svc.update_site_download_setting(req.site_name, req.download_setting, source=req.source)
    if req.priority is not None:
        idx_svc.update_site_priority(req.site_name, req.priority, source=req.source)
    if req.default_settings is not None:
        idx_svc.update_site_default_settings(req.site_name, req.default_settings)
    return success()


@router.post("/sites/indexer-config/sync", response_model=CommonResponse, summary="同步第三方索引器站点")
def sync_indexer_sites(
    req: IndexerSiteConfigSyncRequest,
    user: str = Depends(require_permission("site:manage")),
    idx_svc: IndexerService = Depends(get_indexer_service),
):
    ok = idx_svc.sync_third_party_sites(req.client_id)
    if not ok:
        return fail(msg="同步失败")
    return success()


@router.post("/sites/indexer-config/batch", response_model=CommonResponse, summary="批量更新第三方站点配置")
def batch_update_indexer_site_config(
    req: IndexerSiteConfigBatchRequest,
    user: str = Depends(require_permission("site:manage")),
    idx_svc: IndexerService = Depends(get_indexer_service),
):
    for item in req.sites or []:
        site_name = item.get("site_name")
        if not site_name:
            continue
        source = item.get("source")
        if "enabled" in item:
            idx_svc.update_site_enabled(site_name, bool(item.get("enabled")), source=source)
        if "download_setting" in item:
            idx_svc.update_site_download_setting(site_name, item.get("download_setting"), source=source)
        if "priority" in item:
            idx_svc.update_site_priority(site_name, int(item.get("priority") or 0), source=source)
        if "default_settings" in item:
            idx_svc.update_site_default_settings(site_name, item.get("default_settings"))
    return success()


class SiteParseHealthRequest(BaseModel):
    site_id: int | None = None


@router.get("/parse-health/latest", response_model=CommonResponse, summary="各站点最新解析健康状态")
def parse_health_latest(
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    app_context=Depends(get_app_context),
):
    svc = _build_parse_health_service(app_context)
    return success(data=svc.latest_all())


@router.get("/parse-health/history", response_model=CommonResponse, summary="站点解析健康历史")
def parse_health_history(
    site_id: int,
    limit: int = 30,
    user: str = Depends(require_any_permission("site:view", "site:manage")),
    app_context=Depends(get_app_context),
):
    svc = _build_parse_health_service(app_context)
    return success(data=svc.history(site_id, limit))


@router.get("/parse-health/run-state", response_model=CommonResponse, summary="解析自检是否正在后台运行")
def parse_health_run_state(
    user: str = Depends(require_any_permission("site:view", "site:manage")),
):
    return success(data={"running": bool(_PARSE_HEALTH_STATE.get("running"))})


@router.post("/parse-health/run", response_model=CommonResponse, summary="手动触发站点解析健康自检（后台执行）")
def parse_health_run(
    req: SiteParseHealthRequest,
    user: str = Depends(require_permission("site:manage")),
    app_context=Depends(get_app_context),
):
    state = _PARSE_HEALTH_STATE
    with state["lock"]:
        if state.get("running"):
            return success(data={"running": True, "started": False})
        state["running"] = True

    def _run():
        try:
            svc = _build_parse_health_service(app_context)
            svc.check_all([req.site_id] if req.site_id else None)
        except Exception as e:  # noqa: BLE001
            log.error(f"[解析自检]后台任务异常: {e}")
        finally:
            with state["lock"]:
                state["running"] = False

    threading.Thread(target=_run, name="parse-health-check", daemon=True).start()
    return success(data={"running": True, "started": True})


def _index_id_allowed(allowed: set[str] | None, app_context, index_id) -> bool:
    """按索引器 id/名称判断是否属于用户授权站点（allowed=None 表示不限制）"""
    if allowed is None:
        return True
    key = str(index_id or "")
    try:
        for i in app_context.indexer_service.get_indexers(check=False) or []:
            iid = str(getattr(i, "id", ""))
            iname = str(getattr(i, "name", ""))
            if key in (iid, iname):
                return iname in allowed
    except Exception as e:  # noqa: BLE001
        log.debug(f"[Site]解析索引器授权失败: {e}")
    return key.split(":", 1)[-1] in allowed


def _allowed_site_names(user, app_context) -> set[str] | None:
    """解析用户被授权的 builtin 站点名集合（ADR-021 6.1）.

    None = 不过滤（superadmin / open 策略 / 全站通配）；否则仅返回授权站点名。
    """
    grant_service = getattr(app_context, "site_grant_service", None)
    if grant_service is None:
        return None
    visible = grant_service.get_visible_sites(user)
    if visible is None:
        return None
    if "builtin:*" in visible or "*" in visible:
        return None
    names: set[str] = set()
    for key in visible:
        if key.endswith(":*"):
            continue
        names.add(key.split(":", 1)[1] if ":" in key else key)
    return names


@router.get("/sites/visible", response_model=CommonResponse, summary="获取当前用户可见站点")
def get_visible_sites(
    current_user=Depends(get_current_user),
    app_context=Depends(get_app_context),
    site_svc: SiteService = Depends(get_site_service),
):
    """当前用户可用站点列表（closed 策略下按站点授权白名单过滤），带用途粒度.

    用途粒度同时受站点实际能力约束：搜索需站点已启用（索引器 check），
    RSS 需站点已配置 RSS 源，避免向用户展示"选了也没用"的站点。
    """
    grant_service = app_context.site_grant_service
    visible = grant_service.get_visible_sites(current_user)
    indexers = app_context.indexer_service.indexer.get_indexers_with_source(check=True)
    # RSS 能力：站点已配置 RSS 源
    try:
        rss_capable = {s.get("name") for s in (site_svc.get_sites(rss=True) or []) if s.get("name")}
    except Exception:  # noqa: BLE001
        rss_capable = set()

    def _permissions(name: str, grants: set[str] | None) -> list[str]:
        perms = set(grants) if grants is not None else {"search", "rss"}
        if name not in rss_capable:
            perms.discard("rss")
        return sorted(perms)

    if visible is None:
        # 不过滤：superadmin 或 open 策略
        sites = [{**item, "permissions": _permissions(item["name"], None)} for item in indexers]
    else:
        sites = []
        for item in indexers:
            grants: set[str] = set()
            for key in (f"{item['source']}:{item['name']}", f"{item['source']}:*", item["name"]):
                grants |= visible.get(key, set())
            perms = _permissions(item["name"], grants)
            if perms:
                sites.append({**item, "permissions": perms})
    for site in _external_indexer_sites():
        if visible is None:
            perms = _permissions(site["name"], None)
        else:
            grants: set[str] = set()
            for key in (
                f"{site['source']}:{site['name']}",
                f"{site['source']}:*",
                site["name"],
            ):
                grants |= visible.get(key, set())
            perms = _permissions(site["name"], grants)
        if perms:
            sites.append({**site, "permissions": perms})
    custom_rss_service = getattr(app_context, "custom_rss_service", None)
    if custom_rss_service is not None:
        sites.extend(custom_rss_service.visible_sites(current_user))
    return success(data=sites)
