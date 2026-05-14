"""
Filter Router — FastAPI 迁移
对应原 web/controllers/filter.py，复用 app/services/filter_service.py
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_config_service, require_any_permission
from app.services.filter_service import FilterService as Filter
from app.utils.response import fail, success

router = APIRouter()


def _get_script_path():
    """获取脚本路径（兼容层）"""
    return get_config_service().get_script_path()


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class EmptyRequest(BaseModel):
    data: dict | None = None


class AddFilterGroupRequest(BaseModel):
    name: str | None = None
    default: str | None = None


class AddFilterRuleRequest(BaseModel):
    rule_id: int | None = None
    group_id: int | None = None
    rule_name: str | None = None
    rule_pri: str | None = None
    rule_include: str | None = None
    rule_exclude: str | None = None
    rule_sizelimit: str | None = None
    rule_free: str | None = None


class IdRequest(BaseModel):
    id: int | None = None


class FilterRuleDetailRequest(BaseModel):
    groupid: int | None = None
    ruleid: int | None = None


class ImportFilterGroupRequest(BaseModel):
    content: str | None = None


class RestoreFilterGroupRequest(BaseModel):
    groupids: list[int] | None = None
    init_rulegroups: list | None = None


class RuleTestRequest(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    size: str | None = None
    rulegroup: str | None = None


class SetDefaultFilterGroupRequest(BaseModel):
    id: int | None = None


class ShareFilterGroupRequest(BaseModel):
    id: int | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/groups/add")
def add_filtergroup(
    req: AddFilterGroupRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    name = req.name
    if not name:
        return fail(code=-1)
    Filter().add_group(name, req.default or 'N')
    return success()


@router.post("/rules/add")
def add_filterrule(
    req: AddFilterRuleRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    item = {
        "group": req.group_id,
        "name": req.rule_name,
        "pri": req.rule_pri,
        "include": req.rule_include,
        "exclude": req.rule_exclude,
        "size": req.rule_sizelimit,
        "free": req.rule_free,
    }
    Filter().add_filter_rule(ruleid=req.rule_id, item=item)
    return success()


@router.post("/groups/delete")
def del_filtergroup(
    req: IdRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    Filter().delete_filtergroup(req.id)
    return success()


@router.post("/rules/delete")
def del_filterrule(
    req: IdRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    Filter().delete_filterrule(req.id)
    return success()


@router.post("/rules/detail")
def filterrule_detail(
    req: FilterRuleDetailRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    ruleinfo = Filter().get_rule_detail(
        groupid=req.groupid, ruleid=req.ruleid)
    return success(data=ruleinfo)


@router.post("/groups/import")
def import_filtergroup(
    req: ImportFilterGroupRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    ok, msg = Filter().import_filter_group(req.content)
    if not ok:
        return fail(msg=msg)
    return success(msg=msg)


@router.post("/groups/restore")
def restore_filtergroup(
    req: RestoreFilterGroupRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    Filter().restore_filter_group(
        groupids=req.groupids or [],
        init_rulegroups=req.init_rulegroups or []
    )
    return success()


@router.post("/rules/test")
def rule_test(
    req: RuleTestRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    title = req.title
    if not title:
        return fail(code=-1)
    match_flag, text, order = Filter().test_rule(
        title=title,
        subtitle=req.subtitle,
        size=req.size,
        rulegroup=req.rulegroup
    )
    return success(data={"flag":match_flag, "text":text, "order":order})


@router.post("/groups/default")
def set_default_filtergroup(
    req: SetDefaultFilterGroupRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    groupid = req.id
    if not groupid:
        return fail(code=-1)
    Filter().set_default_filtergroup(groupid)
    return success()


@router.post("/groups/share")
def share_filtergroup(
    req: ShareFilterGroupRequest,
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    ok, msg, json_string = Filter().share_filter_group(req.id)
    if not ok:
        return fail(msg=msg)
    return success(data=json_string)


@router.post("/rules")
def get_filterrules(
    req: EmptyRequest = EmptyRequest(),
    user: str = Depends(require_any_permission("setting:view", "setting:update")),
):
    RuleGroups, Init_RuleGroups = Filter().get_filterrules(
        _get_script_path())
    return success(data=RuleGroups)
