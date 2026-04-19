from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.services.filter_service import FilterService as Filter
from config import Config

filter_bp = Blueprint("filter", __name__, url_prefix="/api/web/filter")


@filter_bp.route('/add_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _add_filtergroup(data):
    """
    新增规则组
    """
    name = data.get("name")
    if not name:
        return fail(code=-1)
    Filter().add_group(name, data.get("default"))
    return success()


@filter_bp.route('/add_filterrule', methods=['POST'])
@any_auth
@parse_json_data
def _add_filterrule(data):
    rule_id = data.get("rule_id")
    item = {
        "group": data.get("group_id"),
        "name": data.get("rule_name"),
        "pri": data.get("rule_pri"),
        "include": data.get("rule_include"),
        "exclude": data.get("rule_exclude"),
        "size": data.get("rule_sizelimit"),
        "free": data.get("rule_free")
    }
    Filter().add_filter_rule(ruleid=rule_id, item=item)
    return success()


@filter_bp.route('/del_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _del_filtergroup(data):
    Filter().delete_filtergroup(data.get("id"))
    return success()


@filter_bp.route('/del_filterrule', methods=['POST'])
@any_auth
@parse_json_data
def _del_filterrule(data):
    Filter().delete_filterrule(data.get("id"))
    return success()


@filter_bp.route('/filterrule_detail', methods=['POST'])
@any_auth
@parse_json_data
def _filterrule_detail(data):
    ruleinfo = Filter().get_rule_detail(
        groupid=data.get("groupid"), ruleid=data.get("ruleid"))
    return success(info=ruleinfo)


@filter_bp.route('/import_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _import_filtergroup(data):
    ok, msg = Filter().import_filter_group(data.get("content"))
    if not ok:
        return fail(msg=msg)
    return success(msg=msg)


@filter_bp.route('/restore_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _restore_filtergroup(data):
    """
    恢复初始规则组
    """
    Filter().restore_filter_group(
        groupids=data.get("groupids") or [],
        init_rulegroups=data.get("init_rulegroups") or []
    )
    return success()


@filter_bp.route('/rule_test', methods=['POST'])
@any_auth
@parse_json_data
def _rule_test(data):
    title = data.get("title")
    if not title:
        return fail(code=-1)
    match_flag, text, order = Filter().test_rule(
        title=title,
        subtitle=data.get("subtitle"),
        size=data.get("size"),
        rulegroup=data.get("rulegroup")
    )
    return success(flag=match_flag, text=text, order=order)


@filter_bp.route('/set_default_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _set_default_filtergroup(data):
    groupid = data.get("id")
    if not groupid:
        return fail(code=-1)
    Filter().set_default_filtergroup(groupid)
    return success()


@filter_bp.route('/share_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _share_filtergroup(data):
    ok, msg, json_string = Filter().share_filter_group(data.get("id"))
    if not ok:
        return fail(msg=msg)
    return success(string=json_string)


@filter_bp.route('/get_filterrules', methods=['POST'])
@any_auth
@parse_json_data
def get_filterrules(data):
    """
    查询所有过滤规则
    """
    RuleGroups, Init_RuleGroups = Filter().get_filterrules(
        Config().get_script_path())
    return success(ruleGroups=RuleGroups, initRules=Init_RuleGroups)
