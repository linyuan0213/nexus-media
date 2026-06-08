# ADR-012: 自动签到插件重构方案

## Status

Proposed

## Date

2026-06-06

## Context

`autosignin` 负责 21 个 PT 站点的每日签到/登录保号，当前实现存在以下问题：

- 21 个 Python 文件，14 个只是重复同一套 GET/POST + 文本匹配
- `ctx` 命名冲突（插件上下文 vs 站点数据上下文）
- 方法内导入依赖（`handlers/base.py` 的 `_http_client`）
- 实际 bug：`signer.py` 重试正则 `r"[(.*?)]"` 因 `[]` 被解释为字符类而失效；`notify=False` 时被误报为"任务失败"
- `SiteEngine` 依赖未移除（`plugin.py` 的 `_signin_base`）
- `freefarm.py` 直接使用 `requests.Session`，绕过 HttpClient
- 认证来源混乱：当前 handler 只读 `cookie`，但数据库有 `COOKIE` / `API_KEY` / `BEARER_TOKEN` 三个字段；`headers` 仅作为请求头补充；API Key 的 header 名称（如 `x-api-key`）来自站点 JSON 定义的 `api.auth.header_name`
- 0 测试覆盖

---

## 决策

采用**"默认复用 + 按需覆盖 + 三层分发"**的架构：

1. **默认复用**：签到认证默认从数据库 `COOKIE` / `API_KEY` / `BEARER_TOKEN` 读取，按 `auth_type` 自动映射，零配置
2. **按需覆盖**：当签到凭据与站点访问凭据来源不同时（如 rousi 签到用 `headers.x-sign-token`），通过 `auth_source` 指定独立来源
3. **自定义 Handler**：问答、OCR、滑块、图片匹配等无法配置化的特殊流程
4. **声明式配置覆盖**：`site_configs.json` 为需要精确控制的站点定义 method / auth_type / auth_source / markers
5. **通用匹配兜底**：无精确配置的站点统一走 `GenericSigninHandler`

---

## 关键设计

### 1. 默认复用映射

```
auth_type          → 默认数据库字段
─────────────────────────────────
cookie_parsed      → site_info["cookie"]
cookie_raw         → site_info["cookie"]
bearer             → site_info["bearer_token"]
apikey             → site_info["api_key"]
none               → 无认证
```

绝大多数站点 `auth_source=None`，直接复用数据库字段，无需额外配置。

### 2. 按需覆盖

当 `auth_source` 不为 `None` 时，**忽略默认映射**，按配置独立获取：

```python
# 从 headers 解析（支持去除前缀如 "Bearer "）
auth_source={"type": "header", "name": "x-sign-token", "strip_prefix": "Bearer "}

# 从 LocalStorage 获取（自动触发 site.local_storage_sync）
auth_source={"type": "local_storage", "domain": "rousi.pro", "key": "token"}
```

### 3. 认证包装

提取到原始凭据值后，按 `auth_type` 包装：

| auth_type | 输入 | 输出 |
|-----------|------|------|
| `cookie_parsed` | cookie 字符串 | `CookieAuth._parse_cookies()` → dict |
| `cookie_raw` | cookie 字符串 | `CookieAuth()` → httpx auth |
| `bearer` | token 字符串 | `BearerAuth()` → httpx auth |
| `apikey` | api_key 字符串 | 附加到请求头（key 来自站点 JSON 的 `api.auth.header_name`，默认 `X-Api-Key`） |
| `none` | — | 无认证 |

### 4. 三层分发

```
site_info.signurl
    → registry.get(domain)
        → 命中自定义 handler？           → 自定义 handler（问答/OCR/滑块/图片匹配）
        → 命中声明式配置？               → DeclarativeSigninHandler
        → 均未命中？                     → GenericSigninHandler（默认 cookie 认证）
```

---

## 详细实现

### 一、凭据解析模块

```python
# autosignin/backend/credentials.py
import json
from abc import ABC, abstractmethod
from typing import Optional

from app.plugin_framework.hook_system import HookSystem


class CredentialSource(ABC):
    @abstractmethod
    def extract(self, site_info: dict) -> Optional[str]:
        ...


class HeaderSource(CredentialSource):
    def __init__(self, name: str, strip_prefix: str = ""):
        self.name = name.lower()
        self.strip_prefix = strip_prefix

    def extract(self, site_info: dict) -> Optional[str]:
        headers = site_info.get("headers")
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                return None
        if not isinstance(headers, dict):
            return None
        for key, value in headers.items():
            if key.lower() == self.name:
                if self.strip_prefix and isinstance(value, str) and value.startswith(self.strip_prefix):
                    return value[len(self.strip_prefix):]
                return value
        return None


class LocalStorageSource(CredentialSource):
    def __init__(self, domain: str, key: str):
        self.domain = domain
        self.key = key

    def extract(self, site_info: dict) -> Optional[str]:
        from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter
        local_storage = CookiecloudAdapter().get_local_storage(self.domain)
        if local_storage:
            return local_storage.get(self.key)
        return None


class CredentialResolver:
    """凭据解析器。"""

    def __init__(self, site_info: dict):
        self.site_info = site_info

    def resolve(self, auth_source: dict | None) -> tuple[Optional[str], bool]:
        """返回 (token_value, need_sync)。"""
        if auth_source is None:
            return None, False
        source = self._build_source(auth_source)
        if isinstance(source, LocalStorageSource):
            return None, True
        return source.extract(self.site_info), False

    def resolve_after_sync(self, auth_source: dict | None) -> Optional[str]:
        if auth_source is None:
            return None
        return self._build_source(auth_source).extract(self.site_info)

    @staticmethod
    def sync_local_storage():
        HookSystem().emit("site.local_storage_sync", {})
        import time
        time.sleep(10)

    def _build_source(self, cfg: dict) -> CredentialSource:
        stype = cfg["type"]
        if stype == "header":
            return HeaderSource(cfg["name"], cfg.get("strip_prefix", ""))
        if stype == "local_storage":
            return LocalStorageSource(cfg["domain"], cfg["key"])
        raise ValueError(f"Unknown credential source type: {stype}")
```

### 二、上下文与结果模型

```python
# autosignin/backend/handlers/base.py
from dataclasses import dataclass, field
from typing import Optional

from app.utils.config_tools import get_proxies


@dataclass
class SiteSigninContext:
    """从 site_info 提取的标准化上下文，站点模块是 URL/凭据唯一来源。"""

    site: str
    site_url: str
    cookie: Optional[str]
    api_key: Optional[str]
    bearer_token: Optional[str]
    ua: Optional[str]
    proxy_url: Optional[str]
    headers: Optional[dict] = None
    is_chrome: bool = False
    auth_config: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_site_info(cls, site_info: dict) -> "SiteSigninContext":
        proxy = get_proxies() if site_info.get("proxy") else None
        proxy_url = (
            proxy.get("http")
            if isinstance(proxy, dict)
            else (proxy if isinstance(proxy, str) else None)
        )
        return cls(
            site=site_info.get("name", ""),
            site_url=site_info.get("signurl", ""),
            cookie=site_info.get("cookie"),
            api_key=site_info.get("api_key"),
            bearer_token=site_info.get("bearer_token"),
            ua=site_info.get("ua"),
            proxy_url=proxy_url,
            headers=site_info.get("headers"),
            is_chrome=bool(site_info.get("chrome", False)),
            auth_config=site_info.get("auth_config", {}),
            raw=site_info,
        )
```

```python
class SigninResult:
    SUCCESS = "签到成功"
    ALREADY = "已签到"
    LOGIN_OK = "登录成功"
    COOKIE_EXPIRED = "cookie失效"
    SITE_UNREACHABLE = "请检查站点连通性"
    REQUEST_FAILED = "签到接口请求失败"
    CHROME_OK = "仿真签到成功"

    def __init__(self, ok: bool, msg: str):
        self.ok = ok
        self.msg = msg

    @classmethod
    def success(cls, site: str) -> "SigninResult":
        return cls(True, f"[{site}]{cls.SUCCESS}")

    @classmethod
    def already(cls, site: str) -> "SigninResult":
        return cls(True, f"[{site}]今日{cls.ALREADY}")

    @classmethod
    def fail(cls, site: str, reason: str) -> "SigninResult":
        return cls(False, f"[{site}]签到失败，{reason}")

    @classmethod
    def custom(cls, ok: bool, msg: str) -> "SigninResult":
        return cls(ok, msg)
```

### 三、基类改造

```python
from abc import ABC, abstractmethod
from typing import Optional

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.context import PluginContext


class SiteSigninHandler(ABC):
    """站点签到处理器基类。"""

    site_url: str = ""

    def __init__(self, plugin_ctx: PluginContext, rate_limiter=None):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter

    @abstractmethod
    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        ...

    def _http_client(self, ctx: SiteSigninContext, **kwargs) -> HttpClient:
        return HttpClient(
            config=HttpClientConfig(proxy_url=ctx.proxy_url, **kwargs),
            rate_limiter=self._rate_limiter,
        )

    def _check_cookie(self, html_text: str, site: str) -> Optional[SigninResult]:
        if "login.php" in html_text:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)
        return None
```

### 四、通用匹配兜底处理器

```python
# autosignin/backend/handlers/_generic.py
import re

from app.infrastructure.http.auth import CookieAuth

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


DEFAULT_SUCCESS_MARKERS = [
    "签到成功",
    "此次签到您获得",
    "获得.*魔力值",
    "获得.*积分",
    "已获取",
]

DEFAULT_ALREADY_MARKERS = [
    "今日已签到",
    "今日已签",
    "已经签到",
    "请不要重复签到",
    "签到已得",
    "重复签到",
    "今天已经签过到了",
]


class GenericSigninHandler(SiteSigninHandler):
    """通用匹配兜底处理器。默认使用数据库 cookie 认证。"""

    site_url = "__generic__"

    def __init__(
        self,
        plugin_ctx: PluginContext,
        rate_limiter,
        success_markers: list[str] | None = None,
        already_markers: list[str] | None = None,
    ):
        super().__init__(plugin_ctx, rate_limiter)
        self._success_markers = success_markers or DEFAULT_SUCCESS_MARKERS
        self._already_markers = already_markers or DEFAULT_ALREADY_MARKERS

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        if not ctx.site_url:
            return SigninResult.custom(True, "")

        client = self._http_client(ctx)
        auth = CookieAuth(ctx.cookie) if ctx.cookie else None
        headers = self._build_headers(ctx)

        try:
            res = client.get(url=ctx.site_url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(res.text, ctx.site):
            return cookie_result

        text = res.text
        if self._match_markers(text, self._success_markers):
            return SigninResult.success(ctx.site)
        if self._match_markers(text, self._already_markers):
            return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")

    def _build_headers(self, ctx: SiteSigninContext) -> dict:
        headers: dict = {}
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        return headers

    @staticmethod
    def _match_markers(text: str, markers: list[str]) -> bool:
        for marker in markers:
            if re.search(marker, text):
                return True
        return False
```

### 五、声明式配置处理器

```python
# autosignin/backend/handlers/_declarative.py
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.http.auth import BearerAuth, CookieAuth
from app.utils import StringUtils

from ..credentials import CredentialResolver
from .base import SigninResult, SiteSigninContext, SiteSigninHandler


@dataclass
class DeclarativeSiteConfig:
    site_url: str
    method: str = "get"
    path: str = ""
    data: dict | None = None
    headers: dict | None = None
    auth_type: str = "cookie_parsed"
    auth_source: dict | None = None   # None 表示使用默认数据库字段映射
    success_markers: list[str] = field(default_factory=list)
    already_markers: list[str] = field(default_factory=list)
    cookie_check: bool = True
    response_type: str = "html"
    json_success_path: str = ""
    json_success_value: Any = None


class DeclarativeSigninHandler(SiteSigninHandler):
    def __init__(self, plugin_ctx, rate_limiter, config: DeclarativeSiteConfig):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    @property
    def site_url(self) -> str:
        return self._config.site_url

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        auth, extra_headers = self._resolve_auth(ctx)
        if isinstance(auth, SigninResult):
            return auth

        client = self._http_client(ctx)
        url = self._build_url(ctx)
        headers = self._build_headers(ctx, extra_headers)

        try:
            if self._config.method == "post":
                res = client.post(url=url, data=self._config.data, headers=headers, auth=auth)
            else:
                res = client.get(url=url, headers=headers, auth=auth)
        except Exception:
            return SigninResult.fail(ctx.site, SigninResult.SITE_UNREACHABLE)

        if self._config.cookie_check:
            if cookie_result := self._check_cookie(res.text, ctx.site):
                return cookie_result

        if self._config.response_type == "json":
            return self._check_json_response(res, ctx)

        text = res.text
        for marker in self._config.success_markers:
            if re.search(marker, text):
                return SigninResult.success(ctx.site)
        for marker in self._config.already_markers:
            if re.search(marker, text):
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"签到接口返回 {text[:200]}")

    def _resolve_auth(self, ctx: SiteSigninContext):
        """解析认证凭据。"""
        resolver = CredentialResolver(ctx.raw)

        # 1. 获取原始凭据值
        if self._config.auth_source is None:
            # 默认来源：auth_type 与数据库字段直接映射
            token = self._default_db_field(ctx)
        else:
            token, need_sync = resolver.resolve(self._config.auth_source)
            if need_sync:
                CredentialResolver.sync_local_storage()
                token = resolver.resolve_after_sync(self._config.auth_source)

        # 2. 包装为 HttpClient 可用形式
        return self._wrap_auth(ctx, token)

    def _default_db_field(self, ctx: SiteSigninContext) -> str | None:
        if self._config.auth_type in ("cookie_parsed", "cookie_raw"):
            return ctx.cookie
        if self._config.auth_type == "bearer":
            return ctx.bearer_token
        if self._config.auth_type == "apikey":
            return ctx.api_key
        return None

    def _wrap_auth(self, ctx: SiteSigninContext, token: str | None):
        if self._config.auth_type in ("cookie_parsed", "cookie_raw"):
            if not token:
                return SigninResult.fail(ctx.site, SigninResult.COOKIE_EXPIRED), {}
            if self._config.auth_type == "cookie_parsed":
                return CookieAuth._parse_cookies(token), {}
            return CookieAuth(token), {}

        if self._config.auth_type == "bearer":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 bearer_token"), {}
            return BearerAuth(token), {}

        if self._config.auth_type == "apikey":
            if not token:
                return SigninResult.fail(ctx.site, "未配置 api_key"), {}
            header_name = ctx.auth_config.get("header_name") or "X-Api-Key"
            return None, {header_name: token}

        return None, {}

    def _build_url(self, ctx: SiteSigninContext) -> str:
        if not self._config.path:
            return ctx.site_url
        base = StringUtils.get_base_url(ctx.site_url).rstrip("/")
        return f"{base}/{self._config.path.lstrip('/')}"

    def _build_headers(self, ctx: SiteSigninContext, extra: dict) -> dict:
        headers: dict = {}
        if self._config.headers and isinstance(self._config.headers, dict):
            headers.update(self._config.headers)
        if ctx.headers and isinstance(ctx.headers, dict):
            headers.update(ctx.headers)
        if ctx.ua:
            headers.setdefault("User-Agent", ctx.ua)
        headers.update(extra)
        return headers

    def _check_json_response(self, res, ctx: SiteSigninContext) -> SigninResult:
        try:
            import json
            data = json.loads(res.text)
        except Exception:
            return SigninResult.fail(ctx.site, "解析 JSON 响应失败")

        actual = data.get(self._config.json_success_path)
        if actual == self._config.json_success_value:
            return SigninResult.success(ctx.site)

        text = res.text
        for marker in self._config.success_markers:
            if marker in text:
                return SigninResult.success(ctx.site)
        for marker in self._config.already_markers:
            if marker in text:
                return SigninResult.already(ctx.site)

        return SigninResult.fail(ctx.site, f"接口返回 {res.text[:200]}")
```

### 六、站点配置存储

```python
# autosignin/backend/site_config_store.py
import json

from app.plugin_framework.context import PluginContext

from .handlers._declarative import DeclarativeSiteConfig


DEFAULT_SITES: list[DeclarativeSiteConfig] = [
    # rousi：auth_type=bearer，但签到 token 不是数据库 BEARER_TOKEN，
    # 而是来自 headers.x-sign-token，因此 auth_source 覆盖默认映射
    DeclarativeSiteConfig(
        site_url="rousi.pro",
        method="post",
        auth_type="bearer",
        auth_source={"type": "header", "name": "x-sign-token", "strip_prefix": "Bearer "},
        headers={"content-type": "application/json"},
        response_type="json",
        json_success_path="code",
        json_success_value=0,
        already_markers=["已签到"],
    ),
    # hdarea：POST 表单，使用默认 cookie 认证
    DeclarativeSiteConfig(
        site_url="hdarea.club",
        method="post",
        data={"action": "sign_in"},
        success_markers=["此次签到您获得"],
        already_markers=["请不要重复签到哦"],
    ),
    # yemapt / zhuque / btschool：cookie_raw 认证（默认从数据库 cookie 读取）
    DeclarativeSiteConfig(
        site_url="yemapt.org",
        method="get",
        auth_type="cookie_raw",
    ),
    DeclarativeSiteConfig(
        site_url="zhuque.io",
        method="get",
        auth_type="cookie_raw",
    ),
    DeclarativeSiteConfig(
        site_url="btschool.club",
        method="get",
        auth_type="cookie_raw",
    ),
]


class SiteConfigStore:
    _FILENAME = "site_configs.json"

    def __init__(self, plugin_ctx: PluginContext):
        self._ctx = plugin_ctx

    def load(self) -> list[DeclarativeSiteConfig]:
        content = self._ctx.read_data(self._FILENAME)
        if not content:
            return list(DEFAULT_SITES)
        try:
            raw = json.loads(content)
            return [DeclarativeSiteConfig(**item) for item in raw]
        except Exception:
            self._ctx.warn(f"读取 {self._FILENAME} 失败，使用默认配置")
            return list(DEFAULT_SITES)

    def save_defaults(self):
        data = [cfg.__dict__ for cfg in DEFAULT_SITES]
        self._ctx.write_data(self._FILENAME, json.dumps(data, ensure_ascii=False, indent=2))
```

### 七、注册表

```python
# autosignin/backend/registry.py
from typing import Any, Callable

from app.utils.submodule_loader import SubmoduleLoader
from app.utils import StringUtils

from .handlers.base import SiteSigninHandler
from .handlers._declarative import DeclarativeSigninHandler
from .handlers._generic import GenericSigninHandler


HandlerFactory = Callable[[], SiteSigninHandler]


class HandlerRegistry:
    def __init__(self, plugin_ctx, rate_limiter, site_configs: list):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter
        self._site_configs = {cfg.site_url: cfg for cfg in site_configs}
        self._handlers: dict[str, HandlerFactory] = {}

    def load(self):
        self._handlers.clear()

        custom_classes = SubmoduleLoader.import_submodules(
            "app.plugin_framework.builtin_plugins.autosignin.backend.handlers",
            filter_func=lambda _, obj: bool(getattr(obj, "site_url", ""))
            and obj.site_url not in ("__fallback__", "__generic__"),
        )
        for cls in custom_classes:
            self._handlers[cls.site_url] = lambda c=cls: c(
                self._plugin_ctx, self._rate_limiter
            )

        for site_url, cfg in self._site_configs.items():
            if site_url not in self._handlers:
                self._handlers[site_url] = lambda c=cfg: DeclarativeSigninHandler(
                    self._plugin_ctx, self._rate_limiter, c
                )

    def get(self, signurl: str) -> HandlerFactory | None:
        if not signurl:
            return None
        domain = StringUtils.get_url_domain(signurl)
        return self._handlers.get(domain)

    def get_generic(self) -> HandlerFactory:
        return lambda: GenericSigninHandler(self._plugin_ctx, self._rate_limiter)

    def __len__(self) -> int:
        return len(self._handlers)
```

### 八、签到引擎

```python
# autosignin/backend/signer.py
class SigninEngine:
    def __init__(self, ctx, registry, simulator):
        self.ctx = ctx
        self._registry = registry
        self._simulator = simulator

    def _signin_site(self, site_info: dict) -> str:
        from .handlers.base import SiteSigninContext

        site_ctx = SiteSigninContext.from_site_info(site_info)
        factory = self._registry.get(site_ctx.site_url)

        handler = None
        if factory:
            handler = factory()

        if not handler and site_ctx.is_chrome:
            return self._simulator.signin(site_info, self.ctx)

        if not handler:
            handler = self._registry.get_generic()()

        try:
            result = handler.signin(site_ctx)
            return result.msg
        except Exception as e:
            return f"[{site_ctx.site}]签到失败：{str(e)}"
```

修复重试正则：

```python
site_names = re.findall(r"\[(.*?)\]", s)
```

修复 notify 逻辑（删除 `else: self.ctx.error(...)`）。

### 九、自定义 Handler 保留清单

```text
handlers/
├── base.py              # SiteSigninContext / SigninResult / SiteSigninHandler
├── _generic.py          # GenericSigninHandler
├── _declarative.py      # DeclarativeSiteConfig / DeclarativeSigninHandler
├── _types.py            # BakatestQaHandler / OcrCaptchaHandler
├── 52pt.py              # BakatestQaHandler
├── chdbits.py           # BakatestQaHandler
├── ptchdbits.py         # BakatestQaHandler
├── freefarm.py          # 滑块链（HttpClient）
├── hdsky.py             # OcrCaptchaHandler
├── mteam.py             # LocalStorage + Chrome
├── opencd.py            # OcrCaptchaHandler
└── tjupt.py             # 图片匹配验证码
```

### 十、站点模块补充

```python
# src/app/sites/sites.py
site_def = SiteEngine.get_instance().get_by_url(str(site_signurl or site_rssurl or ""))
auth_config = {}
if site_def and site_def.api and site_def.api.auth:
    auth_config = {
        "type": site_def.api.auth.type,
        "header_name": getattr(site_def.api.auth, "header_name", None),
    }

site_info = {
    ...
    "auth_config": auth_config,
    ...
}
```

---

## 目录结构

```text
autosignin/backend/
├── __init__.py
├── credentials.py           # 凭据解析器（HeaderSource / LocalStorageSource）
├── plugin.py                # 主插件类
├── registry.py              # 处理器注册表
├── scheduler.py             # 定时调度 + 历史
├── signer.py                # 签到执行引擎
├── simulator.py             # Chrome 仿真
├── site_config_store.py     # 默认配置 + site_configs.json 读写
└── handlers/
    ├── __init__.py
    ├── base.py              # SiteSigninContext / SigninResult / SiteSigninHandler
    ├── _generic.py          # GenericSigninHandler
    ├── _declarative.py      # DeclarativeSiteConfig / DeclarativeSigninHandler
    ├── _types.py            # BakatestQaHandler / OcrCaptchaHandler
    ├── 52pt.py
    ├── chdbits.py
    ├── ptchdbits.py
    ├── freefarm.py
    ├── hdsky.py
    ├── mteam.py
    ├── opencd.py
    └── tjupt.py
```

---

## 测试策略

```text
tests/unit/plugin_framework/builtin_plugins/autosignin/
├── __init__.py
├── conftest.py
├── test_credentials.py          # HeaderSource / LocalStorageSource
├── test_base.py                 # SiteSigninContext, SigninResult
├── test_generic_handler.py      # 通用匹配
├── test_declarative_handler.py  # auth_source 覆盖 / 默认字段映射 / JSON 响应
├── test_registry.py             # 三层分发优先级
├── test_signer.py               # 重试正则修复、notify 逻辑
├── test_site_config_store.py    # 默认配置
└── test_custom_handlers.py      # BakatestQaHandler / OcrCaptchaHandler
```

---

## 影响范围

| 区域 | 变化 |
|------|------|
| `credentials.py` | 新增 |
| `handlers/base.py` | 改造基类 |
| `handlers/_generic.py` | 新增 |
| `handlers/_declarative.py` | 新增，支持 auth_source 覆盖 |
| `handlers/{12个简单站点}.py` | 删除 |
| `handlers/freefarm.py` | 改用 `HttpClient` |
| `site_config_store.py` | 新增 |
| `registry.py` | 三层分发 |
| `plugin.py` | 删除 `_signin_base`，删除 `SiteEngine` |
| `signer.py` | 修复正则与 notify |
| `src/app/sites/sites.py` | 补充 `auth_config` |
| 测试 | 新增 9 个文件 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 通用匹配误报 | 默认 markers 覆盖常见 PT 站点用语；不准的站点用声明式配置覆盖 |
| `site_configs.json` 格式错误 | 回退到默认配置 |
| LocalStorage 同步延迟 | 固定 sleep 10s，与现有行为一致 |
| 新增特殊站点 | 仍可用 Python 自定义 handler |
| 21 个站点回归 | 分 3 批：基类 + bugfix → 声明式迁移 → 自定义 handler 回归 |

---

## 代码库交叉验证

| 引用 | 实际 API | 状态 |
|------|----------|------|
| `StringUtils.get_url_domain(url)` | `src/app/utils/string_utils.py:226` | 已验证 |
| `SubmoduleLoader.import_submodules()` | `src/app/utils/submodule_loader.py:19-23` | 已验证 |
| `container.rate_limit_engine()` | `src/app/di/container.py:266` | 已验证 |
| `Sites.get_sites()` 返回 `signurl` | `src/app/sites/sites.py:97` | 已验证 |
| `CookiecloudAdapter.get_local_storage()` | `src/app/infrastructure/cache_system/cookiecloud_adapter.py` | 已验证 |
| `site_def.api.auth.header_name` | `config/sites/api/mteam.json:15` | 已验证 |

---

## 相关资源

- [ADR-008: 站点速率限制器重构](./ADR-008-site-rate-limiter-refactor.md)
- [ADR-010: HTTP Client httpx 迁移](./ADR-010-http-client-httpx.md)
