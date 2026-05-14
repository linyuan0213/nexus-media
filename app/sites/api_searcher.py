"""
API 站点搜索器

根据 SiteDefinition.api.endpoints.search 配置，
调用站点 API 进行搜索并返回标准化结果。

支持：
- mode_mapping: 媒体类型 → 请求参数映射（含多分类 fan-out）
- filters: 字段值后处理（regex/split/replace 等）
- transform: 命名的值转换函数
- 模板变量：{keyword} {page} {page_1}
"""
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import log
from app.sites.engine import SiteDefinition, SiteEngine
from app.sites.searchers import _TRANSFORMS
from app.utils import RequestUtils
from app.utils.config_tools import get_proxies
from app.utils.types import MediaType


class ApiSiteSearcher:
    """
    API 站点搜索器
    """

    def __init__(self, site_def: SiteDefinition, user_config: dict | None = None):
        self._site = site_def
        self._user_config = user_config or {}
        self._engine = SiteEngine.get_instance()
        self._auth_tokens: dict[str, str] = {}
        self._resolve_auth_tokens()

    def search(
        self,
        keyword: str = "",
        page: int = 0,
        mtype: MediaType | None = None,
    ) -> list[dict[str, Any]]:
        if not self._site.api:
            return []
        keyword = keyword or ""
        search_config = self._site.api.endpoints.get("search", {})
        if not search_config:
            return []
        body_template = dict(search_config.get("body") or {})
        params_template = dict(search_config.get("params") or {})
        mode_mapping = search_config.get("mode_mapping", {})
        mtype_override = {}
        mtype_name = self._mtype_name(mtype)
        if mtype_name and mode_mapping:
            mapped = mode_mapping.get(mtype_name)
            if mapped is not None:
                if isinstance(mapped, list):
                    return self._fanout_search(keyword, page, search_config, body_template, params_template, mapped)
                elif isinstance(mapped, dict):
                    mtype_override = mapped
                else:
                    mtype_override = {"mode": str(mapped)}
        template_vars = {"keyword": keyword, "page": str(page), "page_1": str(int(page) + 1)}
        body = self._render_template(body_template, **template_vars)
        body.update({k: (v.format(**template_vars) if isinstance(v, str) else v)
                     for k, v in mtype_override.items()})
        return self._execute_request(search_config, body, template_vars)

    def _fanout_search(self, keyword, page, search_config, body_template, params_template, categories):
        all_results = []
        template_vars = {"keyword": keyword, "page": str(page), "page_1": str(int(page) + 1)}
        seen = set()
        for cat_config in categories:
            fanout_body = {**body_template}
            fanout_body.update(cat_config)
            body = self._render_template(fanout_body, **template_vars)
            for result in self._execute_request(search_config, body, template_vars):
                key = result.get("title", "") + result.get("enclosure", "") + result.get("size", "")
                if key not in seen:
                    seen.add(key)
                    all_results.append(result)
        return all_results

    def _execute_request(self, search_config, body, template_vars):
        base_url = self._site.api.base_url.rstrip("/")
        method = search_config.get("method", "GET").upper()
        path = search_config.get("path", "").lstrip("/")
        url = f"{base_url}/{path}"
        headers = self._engine._build_headers(self._site, self._user_config)
        proxy = get_proxies() if self._user_config.get("proxy") else None
        if method == "POST":
            res = RequestUtils(headers=headers, proxies=proxy, timeout=30).post_res(
                url=url, data=json.dumps(body, separators=(",", ":"))
            )
        else:
            params = dict(search_config.get("params") or {})
            params = self._render_template(params, **template_vars)
            res = RequestUtils(headers=headers, proxies=proxy, timeout=30).get_res(
                url=url, params=params
            )
        if not res or res.status_code != 200:
            log.warn(f"【ApiSiteSearcher】{self._site.name} 搜索失败: "
                     f"{res.status_code if res else '无响应'}, url={url}")
            return []
        resp_data = res.json()
        result = self._parse_response(resp_data, search_config)
        log.warn(f"【ApiSiteSearcher】{self._site.name} 返回 {len(result)} 条结果, url={url}")
        if len(result) == 0:
            log.warn(f"【ApiSiteSearcher】{self._site.name} raw resp: {str(resp_data)[:200]}")
        return result

    def _resolve_auth_tokens(self):
        if not self._site.api:
            return
        auth_type = self._site.api.auth.get("type", "")
        if auth_type == "passkey":
            token = self._engine._resolve_auth_token(self._site, self._user_config, "passkey")
            if token:
                self._auth_tokens["passkey"] = token
        if auth_type == "csrf":
            token = self._engine._resolve_auth_token(self._site, self._user_config, "csrf")
            if token:
                self._auth_tokens["csrf_token"] = token
        apikey = self._user_config.get("api_key", "")
        if apikey:
            self._auth_tokens["apikey"] = apikey
        domain = self._user_config.get("domain") or self._site.domain or (self._site.api.base_url if self._site.api else "")
        if domain:
            self._auth_tokens["domain"] = domain.rstrip("/")
            self._auth_tokens["base_url"] = (self._user_config.get("domain") or self._site.api.base_url or domain).rstrip("/")

    def _render_template(self, template, **kwargs) -> dict:
        if not template:
            return {}
        result = {}
        for key, value in template.items():
            if isinstance(value, str):
                try:
                    formatted = value.format(**kwargs)
                    if formatted.isdigit() and "{" in value:
                        result[key] = int(formatted)
                    else:
                        result[key] = formatted
                except KeyError:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self._render_template(value, **kwargs)
            elif isinstance(value, list):
                result[key] = [
                    self._render_template(v, **kwargs) if isinstance(v, dict)
                    else v.format(**kwargs) if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _parse_response(self, data, search_config):
        response_config = search_config.get("response", {})
        items_key = response_config.get("items_key", "data")
        mapping = response_config.get("item_mapping", {})
        items = self._get_nested(data, items_key.split(".")) or []
        if not isinstance(items, list):
            items = []
        results = []
        for item in items:
            result = {}
            for field, config in mapping.items():
                result[field] = self._map_field(item, config)
            self._post_process_labels(result, item)
            results.append(result)
        return results

    def _post_process_labels(self, result, raw_item):
        if "labelsNew" in raw_item:
            new_labels = raw_item.get("labelsNew") or []
            old_label = raw_item.get("labels", "0")
            LABEL_MAP = {"1": "DIY", "2": "国配", "4": "中字",
                         "3": "DIY|国配", "5": "DIY|中字",
                         "6": "国配|中字", "7": "DIY|国配|中字"}
            parts = []
            if old_label and str(old_label) != "0":
                parts.append(LABEL_MAP.get(str(old_label), ""))
            if isinstance(new_labels, list):
                parts.extend(str(v) for v in new_labels)
            elif new_labels:
                parts.append(str(new_labels))
            if parts:
                result["labels"] = "|".join(parts)

    @staticmethod
    def _get_nested(obj, keys):
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            elif isinstance(obj, list):
                try:
                    obj = obj[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return obj

    def _map_field(self, item, config):
        if isinstance(config, dict):
            ftype = config.get("type")
            if ftype == "mapping":
                source_val = self._get_nested(item, config.get("source", "").split("."))
                return config.get("map", {}).get(str(source_val), 1.0)
            if ftype == "api":
                return None
            if ftype == "constant":
                return config.get("value")
            if ftype == "template":
                template = config.get("value", "")
                field_vals = dict(self._auth_tokens) if hasattr(self, '_auth_tokens') else {}
                for fk, fsource in (config.get("fields") or {}).items():
                    field_vals[fk] = str(self._get_nested(item, fsource.split(".")) or "")
                try:
                    return template.format(**field_vals)
                except KeyError:
                    return template
            source = config.get("source", "")
            if source:
                val = self._get_nested(item, source.split("."))
                filters = config.get("filters")
                if filters:
                    val = self._apply_filters(val, filters)
                transform = config.get("transform")
                if transform and transform in _TRANSFORMS:
                    val = _TRANSFORMS[transform](val)
                return val
            return config
        return str(config) if config else None

    @staticmethod
    def _apply_filters(value, filters):
        if value is None:
            return ""
        for f in filters:
            name = f.get("name", "")
            args = f.get("args", [])
            if name == "regex" or name == "re_search":
                pattern = args[0] if args else r".*"
                group = int(args[1]) if len(args) > 1 else 0
                match = re.findall(pattern, str(value))
                value = match[group] if match and len(match) > group else ""
            elif name == "split":
                delim = args[0] if args else ","
                idx = int(args[1]) if len(args) > 1 else 0
                parts = str(value).split(delim)
                value = parts[idx] if idx < len(parts) else ""
            elif name == "replace":
                old = args[0] if args else ""
                new = args[1] if len(args) > 1 else ""
                value = str(value).replace(old, new)
            elif name == "strip":
                value = str(value).strip()
            elif name == "appendleft":
                value = str(args[0]) + str(value) if args else str(value)
            elif name == "querystring":
                key = args[0] if args else ""
                try:
                    parsed = urlparse(str(value))
                    qs = parse_qs(parsed.query)
                    value = qs.get(key, [""])[0]
                except Exception:
                    value = ""
        return value

    @staticmethod
    def _mtype_name(mtype):
        if mtype is None:
            return None
        if hasattr(mtype, "name"):
            return mtype.name
        return str(mtype)
