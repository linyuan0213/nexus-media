# ADR-018: 自动签到插件站点驱动重构

## Status

Proposed

## Date

2026-07-15

## Context

ADR-012 已落地，自动签到插件从 21 个独立 Python 文件收敛到“自定义 Handler + 声明式配置 + 通用兜底”三层架构。但运行一段时间后出现以下问题：

1. **站点 URL 仍硬编码**：`MTeam.site_url = "kp.m-team.cc"`、`HDSky.site_url = "hdsky.me"`，`site_config_store.py` 中仍用 `site_url="rousi.pro"` 等字符串作为注册键。站点域名变更或添加镜像域名时，必须改插件代码。
2. **无 API / HTML 站点区分**：`DeclarativeSigninHandler` 的 `auth_type` 与 `response_type` 是补丁式字段，没有明确区分“API 站点走 JSON 端点”和“HTML 站点走页面或浏览器”。
3. **浏览器自动化是兜底策略**：`ChromeSigninSimulator` 只在“无 handler 且 `chrome=True`”时触发，无法作为某些站点的首选签到方式，也没有复用站点定义中的选择器。
4. **注册键是域名**：`HandlerRegistry.get(signurl)` 按 domain 查找，没有利用更稳定的 `site_id`，导致同一站点多个域名时匹配失败。

因此需要进一步重构，使签到逻辑完全由站点定义驱动，URL/认证类型从系统 `SiteEngine` 获取，签到策略作为插件自治配置。

## Decision

采用 **“站点定义驱动、插件配置自治、策略分层”** 的架构：

1. **URL 来源唯一**：所有站点 URL、认证类型、API/HTML 分类从系统 `SiteEngine` / `SiteCache` 获取，handler 不再硬编码 `site_url`。
2. **插件本地配置**：签到策略（method、path、markers、selectors）放在插件目录下的 `signin_configs/*.json`，不污染系统站点 schema。
3. **按 `site_id` 注册**：自定义 handler 与通用策略都通过 `site_id` 匹配，避免域名漂移问题。
4. **三类通用策略**：
   - `ApiSigninHandler`：API 站点，调用 JSON 端点，按 `json_success_path/value` 校验。
   - `HttpSigninHandler`：HTML 站点，直接 HTTP GET/POST，按字符串 markers 匹配。
   - `BrowserSigninHandler`：HTML 站点需浏览器自动化，使用 `BrowserSession` 点击签到元素。
5. **自定义 Handler 保留**：问答、OCR、滑块、LocalStorage 等特殊流程仍用 Python handler，但按 `site_id` 注册并从 `SiteSigninContext` 获取 URL。

## Alternatives Considered

### 1. 在 `config/sites/*.json` 中增加 `signin` 段

- **Pros**：URL 和签到配置都在同一个文件，单点维护。
- **Cons**：签到是插件级行为，污染系统站点 schema；每新增站点签到都要修改核心配置；系统 schema 变更影响面大。
- **Rejected**：站点 JSON 的核心职责是搜索/下载/用户信息，签到不应侵入。

### 2. 插件内完全独立的签到配置（含 URL）

- **Pros**：插件完全自治，不依赖系统 schema。
- **Cons**：URL、domain、api base_url 与系统站点定义重复，易产生漂移；新增站点需要同时在系统和插件里配置 URL。
- **Rejected**：URL 应以系统站点定义为准，避免双写。

### 3. 维持 ADR-012 现状

- **Pros**：无需改动。
- **Cons**：URL 硬编码、API/HTML 不区分、浏览器自动化是兜底，无法支持新站点快速接入。
- **Rejected**：不能解决当前痛点。

## Detailed Design

### 1. 插件目录新增 `signin_configs/`

```text
src/app/plugin_framework/builtin_plugins/autosignin/
├── backend/
│   ├── signin_configs/              # 新增
│   │   ├── rousi.json
│   │   ├── hdarea.json
│   │   ├── yemapt.json
│   │   ├── tnode.json
│   │   ├── btschool.json
│   │   └── ...
│   ├── handlers/
│   │   ├── base.py
│   │   ├── mteam.py                 # 改为 site_id 注册，API + HMAC 签名
│   │   ├── hdsky.py
│   │   ├── chdbits.py
│   │   ├── _api.py                  # 新增
│   │   ├── _http.py                 # 新增（原 _generic）
│   │   └── _browser.py              # 新增（原 simulator）
│   ├── signin_config_store.py       # 新增/替代 site_config_store.py
│   ├── registry.py
│   ├── signer.py
│   └── simulator.py                 # 删除，合并到 _browser.py
```

### 2. 插件本地签到配置格式

按 `site_id` 索引，策略字段与站点类型解耦。自定义 handler 不需要配置。

```json
// signin_configs/hdarea.json
{
  "site_id": "HDarea",
  "type": "http",
  "method": "post",
  "path": "attendance.php",
  "data": {"action": "sign_in"},
  "success_markers": ["此次签到您获得"],
  "already_markers": ["请不要重复签到"]
}
```

```json
// signin_configs/rousi.json
{
  "site_id": "rousi",
  "type": "api",
  "endpoint": {
    "method": "POST",
    "path": "/",
    "body": {}
  },
  "auth": "bearer",
  "auth_source": {"type": "header", "name": "x-sign-token", "strip_prefix": "Bearer "},
  "headers": {"content-type": "application/json"},
  "already_markers": ["已签到"],
  "json_success_path": "code",
  "json_success_value": 0
}
```

```json
// signin_configs/yemapt.json
{
  "site_id": "yemapt",
  "type": "http",
  "auth": "cookie_raw",
  "success_markers": [],
  "already_markers": []
}
```

- `type`：`api` / `http` / `browser`。
- `auth`：可选，默认从系统站点定义推断（api_key / bearer / cookie）。
- `path`：相对于 `site_url` 或 `api.base_url` 的路径。

### 3. `SiteSigninContext` 扩展

```python
from dataclasses import dataclass, field
from typing import Literal

from app.utils.config_tools import get_proxies


@dataclass
class SiteSigninContext:
    """从 site_info 提取的标准化上下文，站点模块是 URL/凭据唯一来源。"""

    site: str
    site_id: str
    site_url: str
    cookie: str | None
    api_key: str | None
    bearer_token: str | None
    ua: str | None
    proxy_url: str | None
    api_key_header: str | None = None
    headers: dict | None = None
    is_browser: bool = False
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_site_info(cls, site_info: dict, site_engine=None) -> "SiteSigninContext":
        proxy = get_proxies() if site_info.get("proxy") else None
        proxy_url = proxy.get("http") if isinstance(proxy, dict) else None
        site_id = str(site_info.get("id", ""))
        if site_engine and (site_url := site_info.get("signurl") or site_info.get("strict_url")):
            site_def = site_engine.get_by_url(site_url)
            if site_def:
                site_id = site_def.id
        return cls(
            site=site_info.get("name", ""),
            site_id=site_id,
            site_url=site_info.get("signurl", ""),
            cookie=site_info.get("cookie"),
            api_key=site_info.get("api_key"),
            bearer_token=site_info.get("bearer_token"),
            ua=site_info.get("ua"),
            proxy_url=proxy_url,
            api_key_header=site_info.get("api_key_header"),
            headers=site_info.get("headers"),
            is_browser=bool(site_info.get("is_browser", False)),
            raw=site_info,
        )
```

### 4. `SigninConfigStore`（替代 `SiteConfigStore`）

```python
"""插件本地签到配置加载，运行时从 SiteEngine 补全 URL。"""

import os

from app.core.root_path import get_project_root
from app.utils.json_utils import JsonUtils

from app.plugin_framework.context import PluginContext


class SigninConfigStore:
    _CONFIG_DIR = os.path.join(
        get_project_root(),
        "src",
        "app",
        "plugin_framework",
        "builtin_plugins",
        "autosignin",
        "backend",
        "signin_configs",
    )
    _USER_FILE = "signin_configs.json"

    def __init__(self, plugin_ctx: PluginContext, site_engine=None):
        self._ctx = plugin_ctx
        self._site_engine = site_engine

    def load_builtin(self) -> list[dict]:
        configs: list[dict] = []
        if not os.path.isdir(self._CONFIG_DIR):
            return configs
        for fname in sorted(os.listdir(self._CONFIG_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._CONFIG_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    configs.append(JsonUtils.load(f))
            except Exception:
                self._ctx.warn(f"加载签到配置失败: {fname}")
        return configs

    def load_user(self) -> list[dict]:
        content = self._ctx.read_data(self._USER_FILE)
        if not content:
            return []
        try:
            return JsonUtils.loads(content)
        except Exception:
            self._ctx.warn(f"读取 {self._USER_FILE} 失败，使用内置配置")
            return []

    def load(self) -> list[dict]:
        """用户配置覆盖内置配置，按 site_id 合并。"""
        builtin = {cfg["site_id"]: cfg for cfg in self.load_builtin()}
        user = {cfg["site_id"]: cfg for cfg in self.load_user()}
        merged = dict(builtin)
        merged.update(user)
        return list(merged.values())
```

### 5. 自定义 Handler 按 `site_id` 注册

自定义 handler 用于无法静态配置的特殊流程（OCR、AI 问答、滑块、动态 HMAC 签名等），但不再硬编码站点 URL。

```python
# handlers/mteam.py
class MTeam(SiteSigninHandler):
    site_id = "mteam"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        # URL 从 ctx.resolve_base_url(site_engine) 获取，不再硬编码
        # 1. 从 localStorage 读取 auth / did / visitorId / webversion
        # 2. 从主站 JS 动态提取 HMAC 密钥
        # 3. 计算签名并 POST api.m-team.io/api/member/updateLastBrowse
        ...
```

### 6. `HandlerRegistry` 改造

```python
from typing import Any, Callable

from app.utils.submodule_loader import SubmoduleLoader

from .handlers.base import SiteSigninHandler
from .handlers._api import ApiSigninHandler
from .handlers._http import HttpSigninHandler
from .handlers._browser import BrowserSigninHandler

HandlerFactory = Callable[[], SiteSigninHandler]


class HandlerRegistry:
    def __init__(self, plugin_ctx, rate_limiter, site_engine, signin_configs: list[dict], agent_service=None):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter
        self._site_engine = site_engine
        self._agent_service = agent_service
        self._signin_configs = {cfg["site_id"]: cfg for cfg in signin_configs}
        self._handlers: dict[str, HandlerFactory] = {}

    def load(self):
        self._handlers.clear()

        # 1. 自定义 handler（按 site_id 注册）
        custom_classes = SubmoduleLoader.import_submodules(
            "app.plugin_framework.builtin_plugins.autosignin.backend.handlers",
            filter_func=lambda _, obj: bool(getattr(obj, "site_id", "")),
        )
        for cls in custom_classes:
            site_ids = getattr(cls, "site_ids", None) or [cls.site_id]
            for sid in site_ids:
                self._handlers[sid] = lambda c=cls: c(
                    self._plugin_ctx,
                    self._rate_limiter,
                    **self._filter_kwargs(c, {"agent_service": self._agent_service}),
                )

        # 2. 通用策略（按插件本地 signin_configs）
        for sid, cfg in self._signin_configs.items():
            if sid in self._handlers:
                continue
            strategy_type = cfg.get("type", "http")
            if strategy_type == "api":
                self._handlers[sid] = lambda c=cfg: ApiSigninHandler(self._plugin_ctx, self._rate_limiter, c)
            elif strategy_type == "browser":
                self._handlers[sid] = lambda c=cfg: BrowserSigninHandler(self._plugin_ctx, self._rate_limiter, c)
            else:
                self._handlers[sid] = lambda c=cfg: HttpSigninHandler(self._plugin_ctx, self._rate_limiter, c)

    @staticmethod
    def _filter_kwargs(handler_class: type, deps: dict[str, Any]) -> dict[str, Any]:
        try:
            import inspect
            params = inspect.signature(handler_class.__init__).parameters
        except Exception:
            return {}
        return {k: v for k, v in deps.items() if k in params}

    def get(self, site_id: str | None) -> HandlerFactory | None:
        if not site_id:
            return None
        return self._handlers.get(site_id)

    def get_generic(self) -> HandlerFactory:
        return lambda: HttpSigninHandler(self._plugin_ctx, self._rate_limiter, {})

    def __len__(self) -> int:
        return len(self._handlers)
```

### 7. 通用策略实现

#### 7.1 `ApiSigninHandler`

```python
# handlers/_api.py
from app.infrastructure.http.auth import ApiKeyAuth, BearerAuth
from app.utils import JsonUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class ApiSigninHandler(SiteSigninHandler):
    site_id = "__api__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        base_url = ctx.resolve_base_url(self._plugin_ctx.site_engine).rstrip("/")
        path = self._config.get("endpoint", {}).get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = self._config.get("endpoint", {}).get("method", "POST")
        body = self._config.get("endpoint", {}).get("body")
        headers = self._build_headers(ctx)

        auth = self._resolve_auth(ctx)
        if isinstance(auth, SigninResult):
            return auth

        client = self._http_client(ctx)
        try:
            if method.upper() == "POST":
                res = client.post(url=url, json=body, headers=headers, auth=auth)
            else:
                res = client.get(url=url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        return self._check_response(res, ctx)

    def _resolve_auth(self, ctx: SiteSigninContext):
        auth_type = self._config.get("auth")
        if auth_type == "api_key" or (auth_type is None and ctx.site_type == "api"):
            if not ctx.api_key:
                return SigninResult.fail(ctx.site, "未配置 api_key")
            header_name = ctx.api_key_header or "X-Api-Key"
            return ApiKeyAuth(ctx.api_key, header_name=header_name)
        if auth_type == "bearer":
            if not ctx.bearer_token:
                return SigninResult.fail(ctx.site, "未配置 bearer_token")
            return BearerAuth(ctx.bearer_token)
        return None

    def _check_response(self, res, ctx: SiteSigninContext) -> SigninResult:
        text = res.text
        try:
            data = JsonUtils.loads(text)
        except Exception:
            return SigninResult.fail(ctx.site, "解析 JSON 响应失败")

        success_path = self._config.get("json_success_path")
        success_value = self._config.get("json_success_value")
        if success_path and data.get(success_path) == success_value:
            return SigninResult.success(ctx.site)

        for marker in self._config.get("success_markers", []):
            if marker in text:
                return SigninResult.success(ctx.site)
        for marker in self._config.get("already_markers", []):
            if marker in text:
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"接口返回 {text[:200]}")
```

#### 7.2 `HttpSigninHandler`（原 `GenericSigninHandler`）

```python
# handlers/_http.py
from app.infrastructure.http.auth import CookieAuth

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

DEFAULT_SUCCESS_MARKERS = [
    "签到成功", "此次签到您获得", "获得.*魔力值", "获得.*积分", "已获取"
]
DEFAULT_ALREADY_MARKERS = [
    "今日已签到", "今日已签", "已经签到", "请不要重复签到",
    "签到已得", "重复签到", "今天已经签过到了"
]


class HttpSigninHandler(SiteSigninHandler):
    site_id = "__http__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config
        self._success_markers = config.get("success_markers") or DEFAULT_SUCCESS_MARKERS
        self._already_markers = config.get("already_markers") or DEFAULT_ALREADY_MARKERS

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        if not ctx.site_url:
            return SigninResult.custom(True, "")

        base_url = ctx.resolve_base_url(self._plugin_ctx.site_engine).rstrip("/")
        path = self._config.get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = self._config.get("method", "get")
        data = self._config.get("data")
        headers = self._build_headers(ctx)

        auth = CookieAuth(ctx.cookie) if ctx.cookie else None
        client = self._http_client(ctx)

        try:
            if method.upper() == "POST":
                res = client.post(url=url, data=data, headers=headers, auth=auth)
            else:
                res = client.get(url=url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(res.text, ctx.site):
            return cookie_result

        text = res.text
        for marker in self._success_markers:
            if marker in text:
                return SigninResult.success(ctx.site)
        for marker in self._already_markers:
            if marker in text:
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")
```

#### 7.3 `BrowserSigninHandler`（原 `ChromeSigninSimulator`）

```python
# handlers/_browser.py
import re
import time

from lxml import etree

from app.infrastructure.chrome import BrowserSession
from app.sites.siteconf import SiteConf
from app.sites.utils import is_logged_in
from app.utils import ExceptionUtils
from app.utils.browser_mode import get_chrome_server_url

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class BrowserSigninHandler(SiteSigninHandler):
    site_id = "__browser__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        home_url = ctx.resolve_base_url(self._plugin_ctx.site_engine)
        if "1ptba" in home_url:
            home_url = f"{home_url}/index.php"

        server_url = get_chrome_server_url()
        if not server_url:
            return SigninResult.fail(site, "Chrome 服务器未配置")

        self._plugin_ctx.info(f"开始浏览器签到：{site}")
        try:
            with BrowserSession(site_key=site, server_url=server_url) as session:
                result = session.navigate(home_url, cookie=ctx.cookie)
                html_text = result.get("html", "")
                time.sleep(10)

                if not html_text:
                    return SigninResult.fail(site, "无法打开网站")

                if self._already_signed(html_text):
                    return SigninResult.already(site)

                if not is_logged_in(html_text):
                    return SigninResult.fail(site, "登录状态异常")

                selectors = self._config.get("checkin_selectors") or SiteConf(self._plugin_ctx.site_engine).get_checkin_conf()
                xpath = self._find_checkin_xpath(html_text, selectors)
                if not xpath:
                    return SigninResult.custom(True, f"[{site}]模拟登录成功")

                session.click(f"xpath:{xpath}")
                time.sleep(15)
                html_text = session.html()

                if self._success(html_text):
                    return SigninResult.custom(True, f"[{site}]浏览器签到成功")
                if self._already_signed(html_text):
                    return SigninResult.already(site)
                if self._two_factor(html_text):
                    return SigninResult.fail(site, "需要两步验证")
                if self._error(html_text):
                    return SigninResult.fail(site, "页面显示错误")
                return SigninResult.fail(site, "浏览器签到失败，未知原因")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return SigninResult.fail(site, str(e))

    def _find_checkin_xpath(self, html_text: str, selectors: list[str]) -> str | None:
        html = etree.HTML(html_text)
        if html is None:
            return None
        for xpath in selectors:
            if html.xpath(xpath):
                return xpath
        return None

    def _already_signed(self, text: str) -> bool:
        return bool(re.search(r"已签|签到已得|今日已签|已签到|签到成功", text, re.IGNORECASE))

    def _success(self, text: str) -> bool:
        markers = self._config.get("success_markers", [])
        if markers:
            return any(re.search(m, text, re.IGNORECASE) for m in markers)
        return bool(re.search(r"已签|签到成功|获得.*积分|签到.*积分", text, re.IGNORECASE))

    def _two_factor(self, text: str) -> bool:
        return bool(re.search(r"完成两步验证|两步验证|2FA|二次验证", text, re.IGNORECASE))

    def _error(self, text: str) -> bool:
        return bool(re.search(r"错误|失败|异常|error|fail", text, re.IGNORECASE))
```

### 8. `SigninEngine` 调用流程

```python
# signer.py
class SigninEngine:
    def __init__(self, ctx, registry: HandlerRegistry, site_cache=None):
        self.ctx = ctx
        self._registry = registry
        self._site_cache = site_cache

    def _signin_site(self, site_info: dict) -> str:
        site_ctx = SiteSigninContext.from_site_info(site_info)
        factory = self._registry.get(site_ctx.site_id)

        handler = None
        if factory:
            handler = factory()

        if not handler and site_ctx.is_browser:
            browser_handler = BrowserSigninHandler(self.ctx, None, {})
            try:
                result = browser_handler.signin(site_ctx)
                return result.msg
            except Exception as e:
                return f"[{site_ctx.site}]浏览器签到失败：{str(e)}"

        if not handler:
            handler = self._registry.get_generic()()

        try:
            result = handler.signin(site_ctx)
            return result.msg
        except Exception as e:
            return f"[{site_ctx.site}]签到失败：{str(e)}"
```

## Implementation Plan

| 阶段 | 内容 | 产出 |
|---|---|---|
| 1 | 新增 `SigninConfigStore` + `signin_configs/` JSON | 插件本地配置体系 |
| 2 | 新增 `ApiSigninHandler` / `HttpSigninHandler` / `BrowserSigninHandler` | 三类通用策略 |
| 3 | 改造 `SiteSigninContext` 和 `HandlerRegistry` | 按 `site_id` 注册、URL 从 `SiteEngine` 获取 |
| 4 | 迁移自定义 handler：`MTeam`、`HDSky`、`CHDBits` 等 | 去掉 `site_url` 硬编码 |
| 5 | 删除 `simulator.py` 和旧 `site_config_store.py` | 代码精简 |
| 6 | 更新 `signer.py` 和 `plugin.py` | 适配新 registry 和 context |
| 7 | 补充测试 | `test_signin_config_store.py`、`test_registry.py`、`test_api_handler.py`、`test_http_handler.py` |
| 8 | 跑 `uv run ruff check .` 和 `uv run pyright src/ tests/` | 质量门禁 |

## Migration

- 旧 `site_configs.json` 中用户自定义的声明式配置可自动迁移到新的 `signin_configs.json` 格式：脚本读取旧配置，按 `site_url` 反查 `SiteEngine.get_by_domain()` 得到 `site_id`，重写为新的 JSON。
- 自定义 handler 的 `site_url` 字段需要改为 `site_id`。
- 旧 `GenericSigninHandler` 的默认 markers 由 `HttpSigninHandler` 继承。
- `ChromeSigninSimulator` 的能力由 `BrowserSigninHandler` 继承，配置从 `signin_configs/*.json` 读取。

## Consequences

### Positive

- URL 不再硬编码在 handler 中，站点域名变更无需改插件代码。
- 新增站点签到只需在插件目录加一个 JSON 文件，无需修改系统 schema。
- API 与 HTML 站点有明确不同的通用策略，接入成本低。
- 浏览器自动化成为一等策略，可按站点配置显式启用。
- `site_id` 注册比域名匹配更稳定，支持多域名/镜像站点。

### Negative

- 重构期间需要同步迁移现有 handler 和配置。
- 插件目录增加 `signin_configs/` 文件，文件数量变多。
- 用户自定义配置格式变化，需要一次迁移脚本。

## Risks and Mitigations

| 风险 | 缓解 |
|---|---|
| `site_id` 与系统定义不一致 | 加载时校验 `SiteEngine.get_by_id(site_id)`，不存在则 warn 跳过 |
| 通用策略误报/漏报 | 为每个站点单独提供 `signin_configs/*.json` 精确控制；兜底策略 markers 可覆盖 |
| 浏览器自动化依赖 Chrome 服务 | 保持 `get_chrome_server_url()` 检查，未配置时返回明确错误 |
| 自定义 handler 迁移遗漏 | 单元测试覆盖每个自定义 handler，确保 `site_id` 存在且能解析 URL |
| 旧 `site_configs.json` 不兼容 | 提供迁移脚本，首次加载时自动转换 |

## Related ADRs

- [ADR-012: 自动签到插件重构方案](./ADR-012-autosignin-plugin-refactor.md) — 前一次重构方案，本次 ADR 在其基础上进一步站点化。
- [ADR-010: HTTP Client httpx 迁移](./ADR-010-http-client-httpx.md) — 通用策略继续使用 `HttpClient`。
- [ADR-008: 站点速率限制器重构](./ADR-008-site-rate-limiter-refactor.md) — 通用策略继续复用 `RateLimitEngine`。
