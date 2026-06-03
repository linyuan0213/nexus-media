"""
刷流任务规则引擎（领域层）
集中处理 RSS选种规则、删种规则、停种规则 的解析与检查

设计原则：
- 纯规则逻辑，不依赖数据库、Service 或应用层对象
- 需要的外部数据通过参数传入
- 调用方（BrushTaskService）负责获取数据并传入
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import dateutil
import pytz

import log
from app.utils import ExceptionUtils, StringUtils
from app.domain.mediatypes import MediaType
from app.domain.enums import BrushDeleteType, BrushStopType


class BrushRuleEngine:
    """刷流规则引擎 — 纯领域逻辑，不持有任何外部依赖"""

    # 操作符映射，用于前端展示
    OP_DISPLAY = {"gt": ">", "lt": "<", "bw": ""}

    # --------------------------------------------------
    # 通用范围检查
    # --------------------------------------------------
    @staticmethod
    def check_range_rule(value: float | int | None, rule_value: str, multiplier: float = 1.0) -> bool:
        """
        通用范围规则检查函数
        :param value: 实际值
        :param rule_value: 规则值，格式为 'operator#min,max'
        :param multiplier: 可选，值的单位倍数，比如 1024 ** 3 表示 GB，3600 表示小时
        """
        if value is None:
            return True
        if not rule_value or not isinstance(rule_value, str):
            return True

        rule_parts = rule_value.split("#")
        if len(rule_parts) < 2 or not rule_parts[1]:
            return True

        operator = rule_parts[0]
        range_values = rule_parts[1].split(",")

        min_value = float(range_values[0]) * multiplier if range_values[0] else 0.0
        max_value = float(range_values[1]) * multiplier if len(range_values) > 1 and range_values[1] else None

        if operator == "gt" and value < min_value:
            return False
        if operator == "lt" and value > min_value:
            return False
        return not (operator == "bw" and (value < min_value or max_value is not None and value >= max_value))

    # --------------------------------------------------
    # RSS 选种规则
    # --------------------------------------------------
    @classmethod
    def check_rss_rule(
        cls,
        rss_rule: dict | None,
        title: str,
        torrent_size: float,
        pubdate: datetime | None,
        torrent_attr: dict,
        media_info: Any = None,
        rss_movies: dict | None = None,
        rss_tvs: dict | None = None,
    ) -> bool:
        """
        检查种子是否符合刷流过滤条件

        :param rss_rule: RSS 选种规则
        :param title: 种子标题
        :param torrent_size: 种子体积（字节）
        :param pubdate: 发布时间
        :param torrent_attr: 种子属性（free/hr/peer_count 等）
        :param media_info: 已识别的媒体信息（用于排除已订阅，由调用方提供）
        :param rss_movies: 电影订阅列表（用于排除已订阅，由调用方提供）
        :param rss_tvs: 电视剧订阅列表（用于排除已订阅，由调用方提供）
        """
        if not rss_rule:
            return True

        try:
            rule_checks: dict[str, Callable[[Any], bool]] = {
                "size": lambda rv: cls.check_range_rule(torrent_size, rv, 1024**3),
                "include": lambda rv: bool(re.search(rv, title, re.IGNORECASE)),
                "exclude": lambda rv: not bool(re.search(rv, title, re.IGNORECASE)),
                "free": lambda rv: cls._check_free_status(torrent_attr, rv),
                "hr": lambda _rv: not torrent_attr.get("hr"),
                "peercount": lambda rv: cls.check_range_rule(torrent_attr.get("peer_count"), rv),
                "pubdate": lambda rv: cls._check_pubdate(pubdate, torrent_attr, rv),
                "exclude_subscribe": lambda rv: not cls._check_subscribe_status(media_info, rss_movies, rss_tvs, rv),
            }

            for rule, check_func in rule_checks.items():
                rule_value = rss_rule.get(rule)
                log.debug(f"检查字段: {rule}, 规则值: {rule_value}")
                if rule_value in ("#", "N", None, ""):
                    log.debug(f"规则 {rule} 被设置为忽略，跳过检查")
                    continue
                if not check_func(rule_value):
                    log.debug(f"字段: {rule} 不符合规则")
                    return False
        except Exception as err:
            ExceptionUtils.exception_traceback(err)

        return True

    @staticmethod
    def _check_free_status(torrent_attr: dict, rule_value: str) -> bool:
        if rule_value == "FREE" and not torrent_attr.get("free"):
            return False
        if rule_value == "2XFREE" and not torrent_attr.get("2xfree"):
            return False
        return not (rule_value == "NORMAL" and (torrent_attr.get("free") or torrent_attr.get("2xfree")))

    @classmethod
    def _check_pubdate(cls, pubdate: datetime | None, torrent_attr: dict, rule_value: str) -> bool:
        if torrent_attr.get("pubdate"):
            local_time_str = torrent_attr.get("pubdate")
            try:
                if local_time_str:
                    pubdate = dateutil.parser.parse(str(local_time_str)).replace(tzinfo=timezone(timedelta(hours=8)))
            except Exception:
                pubdate = None

        if pubdate:
            pubdate_hours = (datetime.now(pytz.utc) - pubdate).total_seconds() / 3600
            return cls.check_range_rule(pubdate_hours, rule_value, multiplier=1)
        return True

    @staticmethod
    def _check_subscribe_status(
        media_info: Any,
        rss_movies: dict | None,
        rss_tvs: dict | None,
        rule_value: str,
    ) -> bool:
        """排除已订阅的媒体 — 纯逻辑，数据由调用方提供"""
        if rule_value == "N":
            return False
        if not media_info:
            return False

        match_flag = False
        # 匹配电影
        if media_info.type == MediaType.MOVIE and rss_movies:
            for rss_info in rss_movies.values():
                if BrushRuleEngine._match_media(media_info, rss_info):
                    match_flag = True
                    break
        # 匹配电视剧
        elif rss_tvs:
            for rss_info in rss_tvs.values():
                rss_sites = rss_info.get("rss_sites")
                if rss_sites and media_info.site not in rss_sites:
                    continue
                if BrushRuleEngine._match_media(media_info, rss_info, is_tv=True):
                    match_flag = True
                    break

        return match_flag

    @staticmethod
    def _match_media(media_info, rss_info: dict, is_tv: bool = False) -> bool:
        """单个订阅与媒体信息匹配"""
        name = rss_info.get("name")
        year = rss_info.get("year")
        tmdbid = rss_info.get("tmdbid")
        fuzzy_match = rss_info.get("fuzzy_match")
        season = rss_info.get("season") if is_tv else None

        if not fuzzy_match:
            if tmdbid and not str(tmdbid).startswith("DB:"):
                if str(media_info.tmdb_id) != str(tmdbid):
                    return False
            else:
                if year and str(media_info.year) not in [str(year), str(int(year) + 1), str(int(year) - 1)]:
                    return False
                if name != media_info.title:
                    return False
            if is_tv and season and season != media_info.get_season_string():
                return False
        else:
            if is_tv and season and season != "S00" and season != media_info.get_season_string():
                return False
            if year and str(year) != str(media_info.year):
                return False
            search_title = f"{media_info.rev_string} {media_info.title} {media_info.year}"
            if name and (not re.search(name, search_title, re.I) and name not in search_title):
                return False
        return True

    # --------------------------------------------------
    # 删种规则
    # --------------------------------------------------
    @classmethod
    def check_remove_rule(
        cls, remove_rule: dict | None, params: dict
    ) -> tuple[bool, BrushDeleteType | list[BrushDeleteType]]:
        """
        检查是否符合删种规则
        :param remove_rule: 删种规则，包含 mode 字段来决定使用 and 或 or 模式
        :param params: 一个字典，包含所有要检查的参数
        """
        if not remove_rule:
            return False, BrushDeleteType.NOTDELETE

        hr = params.get("torrent_attr", {}).get("hr", False)
        log.debug(f"HR 状态 {hr}")

        values = {
            "time": params.get("seeding_time"),
            "hr_time": params.get("seeding_time"),
            "ratio": params.get("ratio"),
            "uploadsize": params.get("uploaded"),
            "dltime": params.get("dltime"),
            "avg_upspeed": params.get("avg_upspeed"),
            "iatime": params.get("iatime"),
            "pending_time": params.get("pending_time"),
            "freespace": params.get("freespace"),
            "freestatus": params.get("torrent_attr", {}).get("free", False),
        }

        rule_checks = {
            "time": (BrushDeleteType.SEEDTIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "hr_time": (BrushDeleteType.HRSEEDTIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "ratio": (BrushDeleteType.RATIO, lambda value, rv: cls.check_range_rule(value, rv)),
            "uploadsize": (BrushDeleteType.UPLOADSIZE, lambda value, rv: cls.check_range_rule(value, rv, 1024**3)),
            "dltime": (BrushDeleteType.DLTIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "avg_upspeed": (BrushDeleteType.AVGUPSPEED, lambda value, rv: cls.check_range_rule(value, rv, 1024**3)),
            "iatime": (BrushDeleteType.IATIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "pending_time": (BrushDeleteType.PENDINGTIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "freespace": (BrushDeleteType.FREESPACE, lambda value, rv: cls.check_range_rule(value, rv, 1024**3)),
            "freestatus": (
                BrushDeleteType.FREESTATUS,
                lambda value, rv: not value if rv == "FREE" else value if rv == "NORMAL" else True,
            ),
            "hr": (BrushDeleteType.HR, lambda value, rv: value if rv == "HR" else not value if rv == "NOHR" else True),
        }

        triggered_types = []
        mode = remove_rule.get("mode", "and")

        for rule, (delete_type, check_func) in rule_checks.items():
            rule_value = remove_rule.get(rule)
            if rule_value in ("#", "N", None, ""):
                continue

            value = values.get(rule)
            if value is None:
                if mode == "and":
                    continue
                else:
                    continue

            try:
                if check_func(float(value), rule_value):
                    triggered_types.append(delete_type)
                    log.debug(f"触发删种规则: {rule}={rule_value}, value={value}, type={delete_type}")
                    if mode == "or":
                        return True, triggered_types
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue

        if mode == "and" and triggered_types:
            return True, triggered_types
        return False, BrushDeleteType.NOTDELETE

    # --------------------------------------------------
    # 停种规则
    # --------------------------------------------------
    @classmethod
    def check_stop_rule(cls, stop_rule: dict | None, params: dict) -> tuple[bool, BrushStopType | list[BrushStopType]]:
        """
        检查是否符合停种规则
        """
        if not stop_rule:
            return False, BrushStopType.NOTSTOP

        values = {
            "ratio": params.get("ratio"),
            "uploadsize": params.get("uploaded"),
            "seedtime": params.get("seeding_time"),
            "avg_upspeed": params.get("avg_upspeed"),
        }

        rule_checks = {
            "ratio": (BrushStopType.RATIO, lambda value, rv: cls.check_range_rule(value, rv)),
            "uploadsize": (BrushStopType.UPLOADSIZE, lambda value, rv: cls.check_range_rule(value, rv, 1024**3)),
            "seedtime": (BrushStopType.SEEDTIME, lambda value, rv: cls.check_range_rule(value, rv, 3600)),
            "avg_upspeed": (BrushStopType.AVGUPSPEED, lambda value, rv: cls.check_range_rule(value, rv, 1024**3)),
        }

        triggered_types = []
        mode = stop_rule.get("mode", "and")

        for rule, (stop_type, check_func) in rule_checks.items():
            rule_value = stop_rule.get(rule)
            if rule_value in ("#", "N", None, ""):
                continue

            value = values.get(rule)
            if value is None:
                continue

            try:
                if check_func(float(value), rule_value):
                    triggered_types.append(stop_type)
                    log.debug(f"触发停种规则: {rule}={rule_value}, value={value}, type={stop_type}")
                    if mode == "or":
                        return True, triggered_types
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue

        if mode == "and" and triggered_types:
            return True, triggered_types
        return False, BrushStopType.NOTSTOP

    # --------------------------------------------------
    # 辅助方法
    # --------------------------------------------------
    @staticmethod
    def parse_rule_string(rule_str: str) -> dict:
        """解析规则字符串为字典"""
        rules = {}
        if not rule_str:
            return rules

        for item in rule_str.split("&&"):
            item = item.strip()
            if "#" in item:
                key, value = item.split("#", 1)
                rules[key.strip()] = value.strip()
        return rules

    @staticmethod
    def format_rule_string(rules: dict) -> str:
        """将规则字典格式化为字符串"""
        if not rules:
            return ""
        return " && ".join(f"{k}#{v}" for k, v in rules.items() if v not in (None, "", "#"))

    @classmethod
    def format_rule_html(cls, rules: dict | None) -> str:
        """将规则字典渲染为 HTML badge 字符串"""
        if not rules:
            return ""

        rule_htmls: list[str] = []

        if rules.get("exclude_subscribe") == "Y":
            rule_htmls.append(cls._badge("排除订阅: 开", "text-green", "排除订阅"))
        elif rules.get("exclude_subscribe"):
            rule_htmls.append(cls._badge("排除订阅: 关", "text-green", "排除订阅"))

        for key, title, color, unit in [
            ("size", "种子大小", "text-blue", "GB"),
            ("pubdate", "发布时间", "text-blue", "小时"),
        ]:
            cls._append_range_badge(rule_htmls, rules, key, title, color, unit)

        if rules.get("upspeed"):
            rule_htmls.append(
                cls._badge(f"上传限速: {cls._filesize(int(rules['upspeed']) * 1024)}B/s", "text-blue", "上传限速")
            )
        if rules.get("downspeed"):
            rule_htmls.append(
                cls._badge(f"下载限速: {cls._filesize(int(rules['downspeed']) * 1024)}B/s", "text-blue", "下载限速")
            )

        if rules.get("include"):
            rule_htmls.append(cls._badge_wrap(f"包含: {rules['include']}", "text-green", "包含规则"))
        if rules.get("hr"):
            rule_htmls.append(cls._badge("排除: HR", "text-red", "排除HR"))
        if rules.get("exclude"):
            rule_htmls.append(cls._badge_wrap(f"排除: {rules['exclude']}", "text-red", "排除规则"))
        if rules.get("dlcount"):
            rule_htmls.append(cls._badge(f"同时下载: {rules['dlcount']}", "text-blue", "同时下载数量限制"))

        peercount = rules.get("peercount")
        if peercount:
            parsed = cls._parse_peercount(peercount)
            if parsed:
                op, val = parsed
                rule_htmls.append(
                    cls._badge(f"做种人数: {cls.OP_DISPLAY.get(op, op)} {val}", "text-blue", "当前做种人数限制")
                )

        if rules.get("mode"):
            mode_str = "与" if rules["mode"] == "and" else "或"
            rule_htmls.append(cls._badge_wrap(f"删种模式: {mode_str}", "text-red", "删种模式"))

        for key, title, color, unit in [
            ("time", "做种时间", "text-orange", "小时"),
            ("ratio", "分享率", "text-orange", ""),
            ("uploadsize", "上传量", "text-orange", "GB"),
            ("dltime", "下载耗时", "text-orange", "小时"),
            ("avg_upspeed", "平均上传速度", "text-orange", "KB/S"),
            ("iatime", "未活动时间", "text-orange", "小时"),
            ("pending_time", "等待时间", "text-orange", "小时"),
            ("freespace", "磁盘剩余空间", "text-blue", "GB"),
        ]:
            cls._append_range_badge(rule_htmls, rules, key, title, color, unit)

        for key, title in [("freestatus", "Free 到期"), ("stopfree", "Free 到期")]:
            val = rules.get(key)
            if val == "Y":
                rule_htmls.append(cls._badge(f"{title}: 开", "text-green", title))
            elif val:
                rule_htmls.append(cls._badge(f"{title}: 关", "text-green", title))

        return "<br>".join(rule_htmls)

    @staticmethod
    def _badge(text: str, color: str, title: str = "") -> str:
        return f'<span class="badge badge-outline {color} me-1 mb-1" title="{title}">{text}</span>'

    @staticmethod
    def _badge_wrap(text: str, color: str, title: str = "") -> str:
        return f'<span class="badge badge-outline {color} me-1 mb-1 text-wrap text-start" title="{title}">{text}</span>'

    @classmethod
    def _append_range_badge(cls, htmls: list, rules: dict, key: str, title: str, color: str, unit: str):
        val = rules.get(key)
        if not val:
            return
        parts = val.split("#")
        if len(parts) < 2 or not parts[0]:
            return
        op = cls.OP_DISPLAY.get(parts[0], parts[0])
        range_str = parts[1].replace(",", "-") if parts[1] else ""
        htmls.append(cls._badge(f"{title}: {op} {range_str}{unit}", color, title))

    @staticmethod
    def _parse_peercount(peercount: str):
        """兼容处理 peercount 字段，返回 (op, val) 或 None"""
        if peercount == "#":
            return None
        if "#" in peercount:
            parts = peercount.split("#")
            return (parts[0], parts[1].replace(",", "-")) if len(parts) >= 2 else None
        try:
            return "lt", str(int(peercount))
        except Exception:
            return None

    @staticmethod
    def _filesize(size_bytes: int) -> str:
        return StringUtils.str_filesize(size_bytes)
