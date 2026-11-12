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

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import log
from app.domain.media_types import ProviderMediaType
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.media.metadata.registry import registry as metadata_registry
from app.sites import engine_tools
from app.sites.credential_provider import merge_spa_config
from app.sites.engine import SiteDefinition
from app.sites.runtime_config import ProfileRouter, SiteRuntimeConfig
from app.sites.searchers import _TRANSFORMS
from app.utils.config_tools import get_proxies
from app.utils.json_utils import JsonUtils


class ApiSiteSearcher:
    """
    API 站点搜索器
    """

    def __init__(self, site_def: SiteDefinition, site_engine, user_config: dict | None = None):
        self._site = site_def
        self._engine = site_engine
        self._raw_user_config = dict(user_config or {})
        self._profile_candidates = ProfileRouter.candidates(site_def, self._raw_user_config, "search")
        self._profile_index = 0
        self._profile_name = ""
        self._api = None
        self._user_config: dict = {}
        self._auth_tokens: dict[str, str] = {}
        self.last_error: str = ""
        self._select_profile(0)

    def _select_profile(self, index: int) -> bool:
        if index < 0 or index >= len(self._profile_candidates):
            return False
        self._profile_index = index
        self._profile_name, self._api, self._user_config = self._profile_candidates[index]
        self._runtime = SiteRuntimeConfig(
            site=self._site,
            site_info=self._raw_user_config,
            capability="search",
            profile_name=self._profile_name,
            api=self._api,
            user_config=self._user_config,
        )
        if self._api and (self._api.auth or {}).get("spa"):
            self._user_config = merge_spa_config(self._user_config, self._site)
        self._auth_tokens = {}
        self._resolve_auth_tokens()
        return True

    def _should_fallback(self) -> bool:
        error = str(self.last_error or "").lower()
        markers = ("http 401", "http 403", "401 unauthorized", "403 forbidden", "sign", "hmac")
        return any(marker in error for marker in markers)

    def search(
        self,
        keyword: str = "",
        page: int = 0,
        mtype: ProviderMediaType | None = None,
        page_size: int | None = None,
        content_profile: str | None = None,
    ) -> list[dict[str, Any]]:
        # 兼容测试/旧调用：未经过 __init__ 的实例直接使用 site.api
        if not hasattr(self, "_profile_candidates"):
            legacy_api = getattr(getattr(self, "_site", None), "api", None)
            self._profile_candidates = [("", legacy_api, {})]
            self._profile_index = 0
            self._api = legacy_api
            self._user_config = {}
        if not self._api:
            return []
        keyword = keyword or ""
        self.last_error = ""
        template_vars = {"keyword": keyword, "page": str(page), "page_1": str(int(page) + 1)}
        mtype_name = self._mtype_name(mtype)
        profile = str(content_profile or "").strip()
        mode_key = str(metadata_registry.search_mode_for_profile(profile) or mtype_name or "")

        for index in range(self._profile_index, len(self._profile_candidates)):
            if index != self._profile_index and not self._select_profile(index):
                break
            search_config = self._api.endpoints.get("search", {}) if self._api else {}
            if not search_config:
                continue
            body, categories = self._build_search_body(search_config, mode_key, template_vars)
            if categories is not None:
                result = self._fanout_search(keyword, page, search_config, categories, page_size, template_vars)
            else:
                result = self._execute_request(search_config, body, template_vars, page_size=page_size)
            if result or not self._should_fallback():
                return result
        return []

    def _build_search_body(
        self,
        search_config: dict,
        mode_key: str,
        template_vars: dict,
    ) -> tuple[dict, list | None]:
        """按当前 profile 自己的 body/mode_mapping 构建搜索请求."""
        body_template = dict(search_config.get("body") or {})
        mode_mapping = search_config.get("mode_mapping", {})
        mtype_override: dict = {}
        if mode_key and mode_mapping:
            mapped = mode_mapping.get(mode_key)
            if mapped is not None:
                if isinstance(mapped, list):
                    return {}, mapped
                if isinstance(mapped, dict):
                    mtype_override = mapped
                else:
                    mtype_override = {"mode": str(mapped)}
            elif mode_key not in {"MOVIE", "TV"}:
                mtype_override = {"mode": mode_key.lower()}
        body = self._render_template(body_template, **template_vars)
        body.update({k: (v.format(**template_vars) if isinstance(v, str) else v) for k, v in mtype_override.items()})
        return body, None

    def _fanout_search(
        self,
        keyword,
        page,
        search_config,
        categories,
        page_size=None,
        template_vars=None,
    ):
        all_results = []
        template_vars = template_vars or {
            "keyword": keyword,
            "page": str(page),
            "page_1": str(int(page) + 1),
        }
        seen = set()
        for cat_config in categories:
            fanout_body = dict(search_config.get("body") or {})
            fanout_body.update(cat_config)
            body = self._render_template(fanout_body, **template_vars)
            for result in self._execute_request(search_config, body, template_vars, page_size=page_size):
                key = "".join(str(result.get(k) or "") for k in ("title", "enclosure", "size"))
                if key not in seen:
                    seen.add(key)
                    all_results.append(result)
        return all_results

    @staticmethod
    def _apply_page_size(container: dict, page_size: int | None) -> None:
        """按站点实际参数名覆盖每页数量（兼容 page_size/pageSize/size/limit 及 pageParam.pageSize 嵌套）"""
        if not page_size:
            return
        for key in (
            "page_size",
            "pageSize",
            "pagesize",
            "size",
            "per_page",
            "perpage",
            "limit",
            "count",
        ):
            if key in container:
                container[key] = int(page_size)
                return
        for group in ("pageParam", "pagination", "paging"):
            nested = container.get(group)
            if isinstance(nested, dict):
                for key in ("pageSize", "page_size", "size"):
                    if key in nested:
                        nested[key] = int(page_size)
                        return

    def _execute_request(self, search_config, body, template_vars, page_size=None):
        base_url = (self._api.base_url or "").rstrip("/") if self._api else ""
        method = search_config.get("method", "GET").upper()
        path = search_config.get("path", "").lstrip("/")
        url = f"{base_url}/{path}"
        # 空数组参数（如 categories: []）表示不过滤，发送前剔除——
        # 部分站点 API 对显式空数组返回 500（如 hddolby），缺省该参数才是"全部分类"
        body = {k: v for k, v in body.items() if not (isinstance(v, list) and len(v) == 0)}
        self._apply_page_size(body, page_size)
        headers = self._engine._build_headers(self._site, self._user_config, api=self._api)
        proxy = get_proxies() if self._user_config.get("proxy") else None
        proxy_url = proxy.get("http") if proxy else None
        rate_limiter = getattr(self._engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        rl_kwargs = engine_tools._get_rate_limit_kwargs(self._engine, self._site)
        params = self._render_template(dict(search_config.get("params") or {}), **template_vars)
        self._apply_page_size(params, page_size)
        try:
            client = HttpClient(
                config=HttpClientConfig(
                    proxy_url=proxy_url,
                    enable_http2=bool(self._api and self._api.http2),
                ),
                rate_limiter=rate_limiter_engine,
            )
            if self._api.auth.get("spa") if self._api else None:
                headers = engine_tools.spa_signed_headers(
                    self,
                    self._api,
                    self._user_config,
                    client,
                    headers,
                    method,
                    url,
                )
            if method == "POST":
                # 部分站点（如 Piggo）POST 搜索仍使用 query string，正文保持 {}。
                if params:
                    url = f"{url}?{urlencode(params, doseq=True)}"
                content_type = search_config.get("content_type", "application/json;charset=utf-8")
                post_headers = {**headers, "Content-Type": content_type}
                if content_type == "application/x-www-form-urlencoded":
                    res = client.post(url=url, data=body, headers=post_headers, **rl_kwargs)
                else:
                    res = client.post(
                        url=url,
                        data=JsonUtils.dumps(body, separators=(",", ":")),
                        headers=post_headers,
                        **rl_kwargs,
                    )
            else:
                res = client.get(url=url, params=params, headers=headers, **rl_kwargs)
            if not res.is_success:
                self.last_error = f"HTTP {res.status_code}"
                log.warn(f"[ApiSiteSearcher]{self._site.name} HTTP {res.status_code}, url={url}")
                return []
            resp_data = res.json()
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            log.warn(f"[ApiSiteSearcher]{self._site.name} 搜索失败, url={url}, error={e}")
            return []
        if isinstance(resp_data, dict) and resp_data.get("code") is not None:
            code = str(resp_data.get("code"))
            if code not in {"0", "200", "success"} and not resp_data.get("data"):
                message = str(resp_data.get("message") or resp_data.get("msg") or "").strip()
                self.last_error = f"API {code}: {message}".strip()
                log.warn(f"[ApiSiteSearcher]{self._site.name} 接口返回错误: {self.last_error}, url={url}")
                return []
        result = self._parse_response(resp_data, search_config)
        log.debug(f"[ApiSiteSearcher]{self._site.name} 返回 {len(result)} 条结果, url={url}")
        if len(result) == 0:
            log.debug(f"[ApiSiteSearcher]{self._site.name} raw resp: {str(resp_data)[:200]}")
        return result

    def _resolve_auth_tokens(self):
        if not self._api:
            return
        auth_type = self._api.auth.get("type", "")
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
        cookie = self._user_config.get("cookie", "")
        if cookie:
            self._auth_tokens["cookie"] = cookie
        bearer_token = self._user_config.get("bearer_token", "")
        if bearer_token:
            self._auth_tokens["bearer_token"] = bearer_token
        domain = self._user_config.get("domain") or self._site.domain or (self._api.base_url if self._api else "")
        if domain:
            parsed = urlparse(domain)
            domain_no_scheme = parsed.netloc if parsed.scheme else domain
            self._auth_tokens["domain"] = domain_no_scheme.rstrip("/")
            self._auth_tokens["base_url"] = (self._api.base_url or self._user_config.get("domain") or domain).rstrip(
                "/"
            )

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
                    self._render_template(v, **kwargs)
                    if isinstance(v, dict)
                    else v.format(**kwargs)
                    if isinstance(v, str)
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
        torrents_key = response_config.get("torrents_key", "")
        if torrents_key and isinstance(items, list):
            flattened = []
            for group in items:
                sub = group.get(torrents_key, []) if isinstance(group, dict) else []
                if isinstance(sub, list):
                    flattened.extend(sub)
            items = flattened
        results = []
        for item in items:
            result = {}
            for field, config in mapping.items():
                result[field] = self._map_field(item, config)
            self._post_process_labels(result, item)
            self._fill_page_url(result)
            results.append(result)
            log.info(
                f"[ApiSiteSearcher]{self._site.name} item: title={result.get('title')!r}, "
                f"description={result.get('description')!r}"
            )
        return results

    def _fill_page_url(self, result: dict) -> None:
        """SPA 列表有时不返回 page_url；用站点 detail_page_url + id 补齐."""
        if result.get("page_url"):
            return
        item_id = result.get("id")
        detail_template = getattr(self._site, "detail_page_url", "") or ""
        if not item_id or not detail_template:
            return
        try:
            detail = detail_template.format(tid=item_id)
        except (KeyError, ValueError):
            return
        if detail.startswith("http"):
            result["page_url"] = detail
            return
        domain = str(getattr(self._site, "domain", "") or "").strip()
        if not domain:
            return
        base = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
        result["page_url"] = f"{base.rstrip('/')}/{detail.lstrip('/')}"

    def _post_process_labels(self, result, raw_item):
        if "labelsNew" in raw_item:
            new_labels = raw_item.get("labelsNew") or []
            old_label = raw_item.get("labels", "0")
            label_map = {
                "1": "DIY",
                "2": "国配",
                "4": "中字",
                "3": "DIY|国配",
                "5": "DIY|中字",
                "6": "国配|中字",
                "7": "DIY|国配|中字",
            }
            parts = []
            if old_label and str(old_label) != "0":
                parts.append(label_map.get(str(old_label), ""))
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
            if ftype == "labels":
                parts: list[str] = []
                for spec in config.get("sources") or []:
                    if not isinstance(spec, dict):
                        continue
                    values = self._get_nested(item, str(spec.get("source") or "").split("."))
                    if isinstance(values, dict):
                        values = [values]
                    elif not isinstance(values, list):
                        values = [values] if values is not None else []
                    label_map = spec.get("map") or {}
                    name_key = str(spec.get("key") or "name")
                    for value in values:
                        if isinstance(value, dict):
                            mapped = label_map.get(str(value.get("id")))
                            label = mapped or value.get(name_key) or value.get("label")
                        else:
                            label = label_map.get(str(value), value)
                        if label and label not in parts:
                            parts.append(str(label))
                text_source = str(config.get("text") or "")
                text_value = str(self._get_nested(item, text_source.split(".")) or "") if text_source else ""
                for pattern, label in (config.get("text_tags") or {}).items():
                    if text_value and re.search(str(pattern), text_value, re.I) and label not in parts:
                        parts.append(str(label))
                return "|".join(parts)
            if ftype == "template":
                template = config.get("value", "")
                field_vals = dict(self._auth_tokens) if hasattr(self, "_auth_tokens") else {}
                for fk, fsource in (config.get("fields") or {}).items():
                    val = field_vals.get(fsource) or self._get_nested(item, fsource.split("."))
                    field_vals[fk] = str(val or "")
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
                    val = _TRANSFORMS[transform](val, config)
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
