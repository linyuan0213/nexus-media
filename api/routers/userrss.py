"""
UserRss Router — FastAPI 迁移
对应原 web/controllers/userrss.py，复用 app/services/userrss_service.py
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_user_rss_service
from app.utils.response import success, fail
from app.services.userrss_service import UserRssService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: Optional[dict] = None


class CheckUserRssTaskRequest(BaseModel):
    ids: Optional[list] = None
    flag: Optional[str] = None


class TaskIdRequest(BaseModel):
    id: Optional[str] = None


class RssArticleTestRequest(BaseModel):
    taskid: Optional[str] = None
    title: Optional[str] = None


class RssArticlesActionRequest(BaseModel):
    taskid: Optional[str] = None
    flag: Optional[str] = None
    articles: Optional[list] = None


class UpdateRssParserRequest(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    format: Optional[str] = None
    params: Optional[str] = None


class UpdateUserRssTaskRequest(BaseModel):
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/check_userrss_task")
def check_userrss_task(
    req: CheckUserRssTaskRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    try:
        svc.check_tasks(
            taskids=req.ids,
            flag=req.flag or ""
        )
        return success(msg="")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return fail(msg="自定义订阅状态设置失败")


@router.post("/delete_rssparser")
def delete_rssparser(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if svc.delete_parser(req.id):
        return success()
    return fail()


@router.post("/delete_userrss_task")
def delete_userrss_task(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if svc.delete_task(req.id):
        return success()
    return fail()


@router.post("/list_rss_parsers")
def list_rss_parsers(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(parsers=svc.get_parsers())


@router.post("/get_rssparser")
def get_rssparser(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(detail=svc.get_parser(req.id))


@router.post("/get_userrss_task")
def get_userrss_task(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(detail=svc.get_task(req.id))


@router.post("/list_rss_tasks")
def list_rss_tasks(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    return success(tasks=svc.get_tasks(), parsers=svc.get_parsers())


@router.post("/list_rss_articles")
def list_rss_articles(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.get_articles(req.id)
    if dto.articles:
        return success(
            data=dto.articles,
            count=dto.count,
            uses=dto.uses,
            address_count=dto.address_count
        )
    return fail(msg="未获取到报文")


@router.post("/list_rss_history")
def list_rss_history(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.get_history(req.id)
    if dto.downloads:
        return success(data=dto.downloads, count=dto.count)
    return fail(msg="无下载记录")


@router.post("/rss_article_test")
def rss_article_test(
    req: RssArticleTestRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    taskid = req.taskid
    title = req.title
    if not taskid or not title:
        return fail(code=-1)
    dto = svc.test_article(taskid, title)
    if dto.name == "无法识别":
        return success(data={"name": "无法识别"})
    return success(data=dto.media_dict)


@router.post("/rss_articles_check")
def rss_articles_check(
    req: RssArticlesActionRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if not req.articles:
        return fail(code=2)
    res = svc.check_articles(
        taskid=req.taskid,
        flag=req.flag,
        articles=req.articles
    )
    return success() if res else fail()


@router.post("/rss_articles_download")
def rss_articles_download(
    req: RssArticlesActionRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    if not req.articles:
        return fail(code=2)
    res = svc.download_articles(
        taskid=req.taskid,
        articles=req.articles
    )
    return success() if res else fail()


@router.post("/run_userrss")
def run_userrss(
    req: TaskIdRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    svc.run_task(req.id)
    return success()


@router.post("/update_rssparser")
def update_rssparser(
    req: UpdateRssParserRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    params = {
        "id": req.id,
        "name": req.name,
        "type": req.type,
        "format": req.format,
        "params": req.params
    }
    if svc.update_parser(params):
        return success()
    return fail()


@router.post("/update_userrss_task")
def update_userrss_task(
    req: UpdateUserRssTaskRequest,
    user: str = Depends(get_current_user),
    svc: UserRssService = Depends(get_user_rss_service),
):
    dto = svc.update_task(req.data or {})
    return success() if dto.success else fail()
