from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
import base64
import json
import os.path
import re
from app.services.filter_service import FilterService as Filter
from app.db.repositories import ConfigRepository
from app.media.meta import MetaInfo
from app.utils import ExceptionUtils
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
        default = data.get("default")
        if not name:
            return fail(code=-1)
        Filter().add_group(name, default)
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
        groupid = data.get("id")
        Filter().delete_filtergroup(groupid)
        return success()

@filter_bp.route('/del_filterrule', methods=['POST'])
@any_auth
@parse_json_data
def _del_filterrule(data):
        ruleid = data.get("id")
        Filter().delete_filterrule(ruleid)
        return success()

@filter_bp.route('/filterrule_detail', methods=['POST'])
@any_auth
@parse_json_data
def _filterrule_detail(data):
        rid = data.get("ruleid")
        groupid = data.get("groupid")
        ruleinfo = Filter().get_rules(groupid=groupid, ruleid=rid)
        if ruleinfo:
            ruleinfo['include'] = "\n".join(ruleinfo.get("include"))
            ruleinfo['exclude'] = "\n".join(ruleinfo.get("exclude"))
        return success(info=ruleinfo)

@filter_bp.route('/import_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _import_filtergroup(data):
        content = data.get("content")
        try:
            _filter = Filter()

            json_str = base64.b64decode(
                str(content).encode("utf-8")).decode('utf-8')
            json_obj = json.loads(json_str)
            if json_obj:
                if not json_obj.get("name"):
                    return fail(msg="数据格式不正确")
                _filter.add_group(name=json_obj.get("name"))
                group_id = _filter.get_filter_groupid_by_name(
                    json_obj.get("name"))
                if not group_id:
                    return fail(msg="数据内容不正确")
                if json_obj.get("rules"):
                    for rule in json_obj.get("rules"):
                        _filter.add_filter_rule(item={
                            "group": group_id,
                            "name": rule.get("name"),
                            "pri": rule.get("pri"),
                            "include": rule.get("include"),
                            "exclude": rule.get("exclude"),
                            "size": rule.get("size"),
                            "free": rule.get("free")
                        })
            return success(msg="")
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return fail(msg="数据格式不正确，%s" % str(err))

@filter_bp.route('/restore_filtergroup', methods=['POST'])
@any_auth
@parse_json_data
def _restore_filtergroup(data):
        """
        恢复初始规则组
        """
        groupids = data.get("groupids")
        init_rulegroups = data.get("init_rulegroups")
        _filter = Filter()
        for groupid in groupids:
            try:
                _filter.delete_filtergroup(groupid)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
            for init_rulegroup in init_rulegroups:
                if str(init_rulegroup.get("id")) == groupid:
                    for sql in init_rulegroup.get("sql"):
                        ConfigRepository().excute(sql)
        return success()

@filter_bp.route('/rule_test', methods=['POST'])
@any_auth
@parse_json_data
def _rule_test(data):
        title = data.get("title")
        subtitle = data.get("subtitle")
        size = data.get("size")
        rulegroup = data.get("rulegroup")
        if not title:
            return fail(code=-1)
        meta_info = MetaInfo(title=title, subtitle=subtitle)
        meta_info.size = float(size) * 1024 ** 3 if size else 0
        match_flag, res_order, match_msg = \
            Filter().check_torrent_filter(meta_info=meta_info,
                                          filter_args={"rule": rulegroup})
        return success(flag=match_flag, text="匹配" if match_flag else "未匹配", order=100 - res_order if res_order else 0)

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
        gid = data.get("id")
        _filter = Filter()
        group_info = _filter.get_filter_group(gid=gid)
        if not group_info:
            return fail(msg="规则组不存在")
        group_rules = _filter.get_filter_rule(groupid=gid)
        if not group_rules:
            return fail(msg="规则组没有对应规则")
        rules = []
        for rule in group_rules:
            rules.append({
                "name": rule.ROLE_NAME,
                "pri": rule.PRIORITY,
                "include": rule.INCLUDE,
                "exclude": rule.EXCLUDE,
                "size": rule.SIZE_LIMIT,
                "free": rule.NOTE
            })
        rule_json = {
            "name": group_info[0].GROUP_NAME,
            "rules": rules
        }
        json_string = base64.b64encode(json.dumps(
            rule_json).encode("utf-8")).decode('utf-8')
        return success(string=json_string)

@filter_bp.route('/get_filterrules', methods=['POST'])
@any_auth
@parse_json_data
def get_filterrules(data):
        """
        查询所有过滤规则
        """
        RuleGroups = Filter().get_rule_infos()
        sql_file = os.path.join(Config().get_script_path(), "init_filter.sql")
        with open(sql_file, "r", encoding="utf-8") as f:
            sql_list = f.read().split(';\n')
            Init_RuleGroups = []
            i = 0
            while i < len(sql_list):
                rulegroup = {}
                rulegroup_info = re.findall(
                    r"[0-9]+,'[^\"]+NULL", sql_list[i], re.I)[0].split(",")
                rulegroup['id'] = int(rulegroup_info[0])
                rulegroup['name'] = rulegroup_info[1][1:-1]
                rulegroup['rules'] = []
                rulegroup['sql'] = [sql_list[i]]
                if i + 1 < len(sql_list):
                    rules = re.findall(
                        r"[0-9]+,'[^\"]+NULL", sql_list[i + 1], re.I)[0].split("),\n (")
                    for rule in rules:
                        rule_info = {}
                        rule = rule.split(",")
                        rule_info['name'] = rule[2][1:-1]
                        rule_info['include'] = rule[4][1:-1]
                        rule_info['exclude'] = rule[5][1:-1]
                        rulegroup['rules'].append(rule_info)
                    rulegroup["sql"].append(sql_list[i + 1])
                Init_RuleGroups.append(rulegroup)
                i = i + 2
        return success(ruleGroups=RuleGroups, initRules=Init_RuleGroups)

