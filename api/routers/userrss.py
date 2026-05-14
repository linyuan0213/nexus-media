"""
UserRss Router — FastAPI 迁移
对应原 web/controllers/userrss.py，复用 app/services/userrss_service.py
"""

import traceback

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_user_rss_service, require_any_permission, require_permission
from app.services.userrss_service import UserRssService
from app.utils.response import fail, success

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class EmptyRequest(BaseModel):
    data: dict | None = None


class CheckUserRssTaskRequest(BaseModel):
    ids: list | None = None
    flag: str | None = None


class TaskIdRequest(BaseModel):
    id: str | None = None


class RssArticleTestRequest(BaseModel):
    taskid: str | None = None
    title: str | None = None


class RssArticlesActionRequest(BaseModel):
    taskid: str | None = None
    flag: str | None = None
    articles: list | None = None


class UpdateRssParserRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    type: str | None = None
    format: str | None = None
    params: str | None = None


class UpdateUserRssTaskRequest(BaseModel):
    data: dict | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks/check")
def check_userrss_task(
    req: CheckUserRssTaskRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    try:
        svc.check_tasks(taskids=req.ids, flag=req.flag or "")
        return success(msg="")
    except Exception:
        traceback.print_exc()
        return fail(msg="自定义订阅状态设置失败")


@router.post("/parsers/delete")
def delete_rssparser(
    req: TaskIdRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if svc.delete_parser(req.id):
        return success()
    return fail()


@router.post("/tasks/delete")
def delete_userrss_task(
    req: TaskIdRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if svc.delete_task(req.id):
        return success()
    return fail()


@router.post("/parsers")
def list_rss_parsers(
    req: EmptyRequest = EmptyRequest(),
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(data=svc.get_parsers())


@router.post("/parsers/detail")
def get_rssparser(
    req: TaskIdRequest,
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(data={"detail": svc.get_parser(req.id)})


@router.post("/tasks/detail")
def get_userrss_task(
    req: TaskIdRequest,
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(data={"detail": svc.get_task(req.id)})


@router.post("/tasks")
def list_rss_tasks(
    req: EmptyRequest = EmptyRequest(),
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(data=svc.get_tasks())


@router.post("/articles")
def list_rss_articles(
    req: TaskIdRequest,
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.get_articles(req.id)
    if dto.articles:
        return success(
            data={"articles": dto.articles, "count": dto.count, "uses": dto.uses, "address_count": dto.address_count}
        )
    return fail(msg="未获取到报文")


@router.post("/articles/history")
def list_rss_history(
    req: TaskIdRequest,
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.get_history(req.id)
    if dto.downloads:
        return success(data={"downloads": dto.downloads, "count": dto.count})
    return fail(msg="无下载记录")


@router.post("/articles/test")
def rss_article_test(
    req: RssArticleTestRequest,
    _: None = Depends(require_any_permission("rss:view", "rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    taskid = req.taskid
    title = req.title
    if not taskid or not title:
        return fail(code=-1)
    dto = svc.test_article(int(taskid) if taskid else 0, title)
    if dto.name == "无法识别":
        return success(data={"name": "无法识别"})
    return success(data=dto.media_dict)


@router.post("/articles/check")
def rss_articles_check(
    req: RssArticlesActionRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if not req.articles:
        return fail(code=2)
    res = svc.check_articles(taskid=req.taskid, flag=req.flag, articles=req.articles)
    return success() if res else fail()


@router.post("/articles/download")
def rss_articles_download(
    req: RssArticlesActionRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if not req.articles:
        return fail(code=2)
    res = svc.download_articles(taskid=req.taskid, articles=req.articles)
    return success() if res else fail()


@router.post("/tasks/run")
def run_userrss(
    req: TaskIdRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    svc.run_task(req.id)
    return success()


@router.post("/parsers/update")
def update_rssparser(
    req: UpdateRssParserRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    params = {"id": req.id, "name": req.name, "type": req.type, "format": req.format, "params": req.params}
    if svc.update_parser(params):
        return success()
    return fail()


@router.post("/tasks/update")
def update_userrss_task(
    req: UpdateUserRssTaskRequest,
    _: None = Depends(require_permission("rss:manage")),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.update_task(req.data or {})
    return success() if dto.success else fail()
