# ADR-017: HttpClient 浏览器自动化透明集成

## Status
Proposed

## Date
2026-07-10

## Context

站点抓取需要绕过 Cloudflare、五秒盾、雷池等 WAF/CDN 防护。这类挑战无法用纯 HTTP 完成，必须通过真实浏览器执行 JS、过盾并提取 `cf_clearance` 等 Cookie。

项目当前存在两条互不相通的抓取路径，且已出现契约错配：

1. **纯 HTTP 路径**：`HttpClient` / `AsyncHttpClient`（`src/app/infrastructure/http/`）是统一 Facade，内置 tenacity 重试、`HttpCacheConfig` 缓存、`RateLimitEngine` 限流、中间件链路、`register_global_host_mapping` DNS 映射。全项目约 **196 处** `HttpClient(...)` 调用点。

2. **浏览器路径**：`ChromeClient`（`src/app/infrastructure/chrome/client.py`）独立于 `HttpClient` 之外，调用远端 Chrome 服务器（nexus-media-chrome）。

存在的问题：

- **契约错配**：`ChromeClient` 仍在调用 Chrome 服务器的**旧 `/tabs` API**（`POST /tabs`、`GET /tabs/{id}/html`、`POST /tabs/click/`），而 Chrome 服务器已重构为 **Session 架构**（`/sessions/{id}/navigate`、`/fetch`、`/cookies`），旧 `/tabs` 路由已移除。当前浏览器自动化调用会 404。
- **能力割裂**：196 个 `HttpClient` 调用点无法享受浏览器绕过能力。要让某个站点走浏览器，必须在业务代码里手动改用 `ChromeClient`，并自行处理 Cookie 复用、重试、限流。
- **Cookie 复用缺失**：过盾拿到的 Cookie 未能自动回灌到后续 HTTP 请求，导致每次抓取都可能重新过盾。

**目标**：让 `HttpClient` 原生支持浏览器自动化。对某站点开启浏览器自动化后，该站点的请求自动经由 Chrome 服务器过盾并复用 Cookie，而**上层 196 个调用点的代码保持不变**。

## Decision

采用 **自定义 httpx Transport（`ChromeTransport`）** 作为集成点，而非新增并行客户端。

`HttpClient` / `AsyncHttpClient` 的重试、缓存、限流、中间件、DNS 映射全部构建在 `httpx.Client(transport=...)` / `httpx.AsyncClient(transport=...)` 之上。只要替换底层 transport，`.get()` / `.post()` / `res.text` / `res.json()` / `res.status_code` 对所有调用点保持 100% 兼容。

```
                     HttpClient Facade (不变)
        retry / cache / rate-limit / middleware (不变)
                          │
              ┌───────────┴────────────┐
     browser.enabled=False       browser.enabled=True
              │                          │
     _MappedTransport            ChromeTransport  ← 新增
     (直连 httpx)                     │
                          HTTP → Chrome Server /sessions/*
                                     │
                          浏览器过盾 + Cookie 复用
```

### 1. 配置层：`HttpClientConfig` 增加浏览器字段

`src/app/infrastructure/http/config.py`：

```python
@dataclass
class BrowserModeConfig:
    """浏览器自动化模式配置."""

    enabled: bool = False
    server_url: str = ""                     # chrome_server_host
    session_key: str = "default"             # 最终会话隔离键（含站点标识 + 配置指纹）
    site_key: str = "default"                # 基础站点标识（如域名），用于与 BrowserSession 对齐
    fingerprint_profile: str = "stealth"     # default / stealth / paranoid
    user_agent: str | None = None
    proxy_url: str | None = None             # 透传给浏览器 session 的代理
    navigate_timeout: int = 30               # 过盾超时（秒）
    auto_navigate_on_challenge: bool = True  # fetch 命中挑战时自动回退 navigate
    render_html: bool = False                # True=返回浏览器渲染后 HTML；False=HTTP fetch


@dataclass
class HttpClientConfig:
    # ...existing fields...
    browser: BrowserModeConfig | None = None
```

### 2. Transport 层：新增 `ChromeTransport`

新增 `src/app/infrastructure/http/browser_transport.py`，包含同步 `ChromeTransport(httpx.BaseTransport)` 与异步 `AsyncChromeTransport(httpx.AsyncBaseTransport)` 两个类。

职责：把一个 `httpx.Request` 翻译为 Chrome 服务器调用，再组装回 `httpx.Response`。

```
handle_request(request):
  1. ensure_session()          → POST /sessions (幂等，409 视为已存在)
  2. 发起数据请求:
       POST /sessions/{key}/request
         { url, method, headers, data,
           navigate_if_challenge=auto_navigate_on_challenge,
           return_html=render_html, timeout=navigate_timeout }
       服务端内部：先 fetch → 命中挑战则自动 navigate 过盾 → 再 fetch，
       Cookie 由该 session 持有并自动复用
  3. 用返回的 status_code / headers / body（或 html）构造 httpx.Response 交还上层
```

关键点：

- **Cookie 生命周期**由 Chrome 服务器 session 管理，backend 无需自己持久化 `cf_clearance`，避免同步复杂度。
- backend 侧原有 `cookie` / `CookieAuth` 通过请求的 `cookie` 字段透传给浏览器作为初始 Cookie。
- **Cookie 合并规则**：服务端 `fetch` 与 `request` 需先合并 session 内的 Cookie 与请求传入的 Cookie，**同名键以 session Cookie 优先**（session 可能已通过 JS 刷新或获取 `cf_clearance`）。合并后的 Cookie 再发送给目标站点。
- **代理 / UA / 指纹**在创建 session 时透传；若配置变化，需生成新的 session_key（见第 3 节）。
- transport 内部对 Chrome 服务器的 HTTP 调用**使用独立、无缓存、无中间件、无限流的简化 HTTP 客户端**（直接用 `httpx.Client`/`httpx.AsyncClient`），避免递归与缓存污染。
- 交互类操作（click / input / execute）不属于 request/response 语义，**不走 transport**，继续直连 Session API。

### 2.1 响应构造：`httpx.Response` 组装要求

`ChromeTransport` 收到 Chrome 服务器返回的 JSON 后，必须组装成标准 `httpx.Response`，使上层 `.text`、`.json()`、`.status_code`、`.headers` 行为与直连一致：

```python
def build_response(request: httpx.Request, payload: dict) -> httpx.Response:
    """把 Chrome 服务器 /sessions/{id}/request 返回的 JSON 组装成 httpx.Response。"""
    data = payload.get("data", {})
    status_code = int(data.get("status_code", 0))
    headers = data.get("headers", {})
    # return_html=True 时取 html，否则取 body
    content = (data.get("html") if render_html else data.get("body")) or ""
    if isinstance(content, str):
        # 根据响应头编码；未指定时默认 utf-8
        encoding = "utf-8"
        if headers.get("content-type"):
            ct = headers["content-type"]
            if "charset=" in ct:
                encoding = ct.split("charset=")[-1].split(";")[0].strip()
        content = content.encode(encoding)
    return httpx.Response(
        status_code=status_code,
        headers=headers,
        content=content,
        request=request,
    )
```

**服务端必须保证**：
- `headers` 包含 `Content-Type`（含 `charset`）和 `Content-Length` 等关键头；`Content-Type` 决定 `res.text` 与 `res.json()` 是否正确。
- `render_html=False` 时 `body` 是原始 HTTP 响应体（未解码 bytes 或字符串）。
- `render_html=True` 时 `html` 是浏览器 DOM 序列化字符串（UTF-8），backend 在解析前做归一化（见第 5 节）。

`httpx.Response` 自带 `iter_bytes()` 支持内存内容，故 `HttpClient.stream()` 在返回非超大响应时仍可用；但浏览器 transport**不应用于下载大文件**（见第 7.3 节边界说明）。

### 3. 客户端池：`_make_key` 纳入浏览器身份，session_key 纳入配置指纹

`client.py` / `async_client.py` 的 `_ClientPool._make_key` 追加浏览器相关字段（`enabled, server_url, session_key, site_key, fingerprint_profile, user_agent, proxy_url, render_html`），保证不同 session 的浏览器客户端不被错误复用。

`_build_client` 中按开关选择 transport：

```python
if self._config.browser and self._config.browser.enabled:
    transport = ChromeTransport(self._config.browser, limits=limits)
else:
    transport = _MappedTransport(limits=limits, retries=0)
```

**session_key 必须随 UA/代理/指纹变化**：`session_key` 用于在 Chrome 服务器上隔离 session。若用户修改站点 UA、代理或指纹 profile，旧 session 不能复用，否则请求仍使用旧配置。定义：

```python
def make_session_key(site_key: str, browser: BrowserModeConfig) -> str:
    """会话隔离键包含站点标识与浏览器配置指纹，配置变化自动换新 session。"""
    config_hash = hashlib.md5(
        f"{browser.fingerprint_profile}:{browser.user_agent}:{browser.proxy_url}:{browser.render_html}".encode()
    ).hexdigest()[:8]
    return f"{site_key}:{config_hash}"
```

调用方通常传 `site_key=site_info.get("domain") or site_info.get("name")`。

这样不同站点天然隔离；同一站点配置变化（如换 UA）也会自动创建新 session，旧 session 由 Chrome 服务器 TTL 回收。

### 4. 配置解析：站点级开关（来自用户维护的站点配置）

浏览器自动化是**用户在站点维护里配置的运行时开关**，存储于 DB 的 `CONFIG_SITE.NOTE` JSON，而非静态站点定义（`config/sites/*` 的 `SiteDefinition`）。

项目**已存在同类的 `chrome` 布尔开关**，走完整链路：

```
CONFIG_SITE.NOTE (JSON)   ← 用户在站点管理 UI 配置
  └─ SiteEntity.note       (domain/entities/site.py，JSON 反序列化为 dict)
       └─ SiteCache._build_site_info()   (sites/site_cache.py)
            └─ site_info["chrome"] = bool(note.get("chrome"))
                 └─ 运行时经 site_info.get("chrome") 读取（site_userinfo.py / site_resolver.py 已在用）
```

本方案**沿用该机制**，将浏览器自动化开关作为站点运行时配置：

- **写入路径**：`SiteService.update_site()`（`services/site_service.py`）的 `switch_keys` 中已包含 `chrome`；浏览器模式直接复用 `chrome` 语义，或按需在 `switch_keys` 增补新键（如 `browser_render`），由站点管理 UI 提交。**不修改任何站点 JSON。**
- **读取路径**：`SiteCache._build_site_info()` 已输出 `site_info["chrome"]`；运行时从 `site_info`（`SiteCache.get_sites()` 的返回）取值。
- **API 站点透传**：`searcher_factory` / `engine_tools._call_endpoint` / `site_resolver` 组装 `user_config` 时，需把 `chrome` 与 `browser_render` 透传给 `ApiSiteSearcher`，否则 API 站点无法判断是否开启浏览器模式。


调用方从传入的站点运行时配置（`site_info` / `user_config`）读取开关，再构造 `BrowserModeConfig`：

```python
def build_browser_mode(
    site_info: dict,
    site_key: str,
    proxy_url: str | None = None,
) -> BrowserModeConfig | None:
    """从站点运行时配置构造浏览器模式配置。开关来自 site_info，非静态 JSON。"""
    host = settings.get("laboratory").get("chrome_server_host")
    if not host or not site_info.get("chrome"):  # 用户维护的站点级开关
        return None
    browser = BrowserModeConfig(
        enabled=True,
        server_url=host.rstrip("/"),
        session_key=site_key,  # 仅基础站点标识，内部 make_session_key 会追加配置指纹
        fingerprint_profile="stealth",
        user_agent=site_info.get("ua"),
        proxy_url=proxy_url,
        render_html=bool(site_info.get("browser_render")),  # 站点级；默认 False=原始 HTML
    )
    browser.session_key = make_session_key(site_key, browser)
    return browser
```

> 说明：是否新增独立的 `browser_emulation` 键、还是直接复用现有 `chrome` 键作为「浏览器自动化」总开关，属实现细节。二者都从**用户维护的站点配置（`NOTE` JSON → `site_info`）**流入，均不涉及静态站点 JSON。且 session 键必须随 UA/代理/指纹/渲染模式变化，避免旧 session 被错误复用。

### 5. 渲染 HTML 与原始 HTML 的差异及兼容归一化

开启浏览器自动化后，取回的 HTML 有**两种来源，内容不同**，由 `render_html` 决定：

| | `render_html=False`（默认，Session 内 HTTP fetch） | `render_html=True`（浏览器渲染 DOM） |
|---|---|---|
| 内容来源 | 过盾后用会话 Cookie 发普通 HTTP 请求 | `tab.html`，执行完 JS 后的 DOM 序列化 |
| JS 执行 | 否，拿到**服务端原始 HTML** | 是，拿到**渲染后 DOM 快照** |
| 动态内容（SPA/Ajax 列表） | 缺失 | 完整 |
| DOM 形态 | 原样标签 | 浏览器规范化（自动补 `<tbody>`、属性重排、实体解码） |
| 适用站点 | SSR 站点（多数 PT 站） | JS 前端渲染的站点 |

即：浏览器渲染的页面与 httpx 抓取的页面**通常不同**——前者是执行 JS 后的 DOM，后者是服务端原始 HTML。

#### 核心风险：浏览器自动插入 `<tbody>` 会破坏现有站点规则

现状实测（本仓库）：

- 站点解析规则用 **CSS selector（经 `_css_to_xpath` 转 XPath，`lxml` 解析）**，其中 **269 处 `> tr` 直接子选择器，遍布 90 个站点配置**（如 `table.torrents > tr`）。
- `_css_to_xpath` 把 `>` 转为**直接子轴 `/`**（`.//table[...]/tr`）。
- `lxml` 解析**原始 HTML 不会**自行补 `<tbody>`，故 `table/tr` 命中正常。
- 但**浏览器渲染后的 HTML 已含 `<tbody>`**，结构变为 `table/tbody/tr`，**直接子选择器全部失配（命中 0）**。

结论：`render_html=True` 若不做处理，会导致 90 个站点的种子列表解析集体失败。

#### 决策：兼容性由系统在解析层归一化，不转嫁给用户

**不要求用户修改任何 XPath / selector**。而是在浏览器渲染 HTML **进入解析前统一预处理**：

1. **剥离 `<tbody>`（提升其子节点到 `<table>`）**，使渲染 HTML 的表格结构与原始 HTML 同构。实测后 269 处 `> tr` 规则无需改动即可继续命中：

   ```python
   def normalize_rendered_html(doc):
       """将浏览器渲染 DOM 归一化到与服务端原始 HTML 同构（供现有规则复用）。"""
       for tb in doc.xpath("//tbody"):
           parent = tb.getparent()
           idx = list(parent).index(tb)
           for child in reversed(list(tb)):
               parent.insert(idx, child)
           parent.remove(tb)
       return doc
   ```

2. 归一化在浏览器渲染路径**统一入口**执行（`ChromeTransport` 返回 `render_html` 内容时打标，或解析层 `etree.HTML` 后按来源判断），对上层解析代码透明。
3. `render_html=False`（fetch 原始 HTML）与现有 httpx 路径**天然同构**，不触发归一化。

#### 默认策略与站点级配置

1. **默认 `render_html=False`**：多数 PT 站为 SSR，种子列表在原始 HTML 里就有，走 fetch（原始 HTML + 过盾 Cookie）即可，最大程度复用现有规则、零解析风险。
2. **`render_html` 是站点级开关**：「是否需要 JS 渲染」是站点特性，与 `browser_emulation` 一样作为**用户维护的站点配置**（`NOTE` JSON → `site_info`），由 `build_browser_mode` 从 `site_info` 读取，不在调用点写死。开启 `render_html=True` 时归一化自动兜底，仍无需改规则。
3. **API 站点不需要渲染 HTML**：API 站点（`api_searcher.py`）返回 JSON，不存在 `<tbody>` 等 DOM 差异，因此即使开启浏览器自动化，也应使用 `render_html=False`，仅用于过盾后 fetch 原始 JSON。归一化逻辑对 API 响应无影响。

```python
def build_browser_mode(site_info, site_key, proxy_url=None):
    host = settings.get("laboratory").get("chrome_server_host")
    if not host or not site_info.get("chrome"):
        return None
    browser = BrowserModeConfig(
        enabled=True,
        server_url=host.rstrip("/"),
        session_key=site_key,  # 内部会被 make_session_key 扩展
        fingerprint_profile="stealth",
        user_agent=site_info.get("ua"),
        proxy_url=proxy_url,
        render_html=bool(site_info.get("browser_render")),  # 站点级；默认 False=原始 HTML
    )
    browser.session_key = make_session_key(site_key, browser)
    return browser
```

### 6. 调用点最小改动示例

#### HTML 站点（`html_searcher.py` / `site_resolver.py` / `engine.py`）

已持有站点运行时配置 `site_info`：

```python
client = HttpClient(
    config=HttpClientConfig(
        proxy_url=proxy_url,
        timeout=30,
        browser=build_browser_mode(
            site_info=site_info, site_key=site_info.get("domain") or site_info.get("name"),
            proxy_url=proxy_url,
        ),  # 开关与 render_html 均来自站点配置；未开启返回 None，等同直连
    ),
    rate_limiter=rate_limiter_engine,
)
res = client.get(url, headers=headers, auth=auth)  # 未开启则直连，开启则走浏览器
html = res.text                                     # 上层代码不变；渲染 HTML 已归一化
```

#### API 站点（`api_searcher.py` / `engine_tools._call_endpoint`）

API 站点返回 JSON，通常不需要渲染 HTML，但可能被 WAF 拦截。同样传 `browser` 参数，**强制 `render_html=False`**：

```python
client = HttpClient(
    config=HttpClientConfig(
        proxy_url=proxy_url,
        timeout=30,
        browser=build_browser_mode(
            site_info=site_info, site_key=site_info.get("domain") or site_info.get("name"),
            proxy_url=proxy_url,
            # API 站点只过盾，不渲染；user_config 需包含 chrome 开关
            render_html=False,
        ),
    ),
    rate_limiter=rate_limiter_engine,
)
res = client.post(url, data=body, headers=headers)  # 返回 JSON，.json() 正常
resp_data = res.json()
```

实现前提：
- `ApiSiteSearcher` 需要能访问 `site_info`（或 `user_config` 里包含 `chrome` 和 `browser_render`）。
- `searcher_factory` 组装 `user_config` 时，需把 `site_info["chrome"]` 和 `site_info["browser_render"]` 透传进去；否则 `api_searcher` 无法判断是否开启浏览器模式。

> 注意：调用点仍需在构造 `HttpClient` 时传入 `browser` 配置，并非完全无改动。改动量极小（只在已有 `HttpClient` 构造处增加 `browser=` 参数），解析逻辑完全不变。

### 7. 交互式流程（签到 / 点击 / 输入 / 验证码）

签到这类流程是**多步、有状态的会话**：打开页面 → 检测是否已签 → 找签到按钮 → 点击 → 等待渲染 → 校验结果，中间可能还要输入验证码答案。这不是单次 request/response，**不能走 `ChromeTransport`**（transport 只翻译单个 `httpx.Request`）。

这类场景直连 Chrome 服务器的 **Session API**，用一个显式的会话客户端 `BrowserSession` 封装交互原语。

#### 新增 `BrowserSession`（`src/app/infrastructure/chrome/session.py`）

对 `/sessions/{id}/*` 的薄封装，内部所有对 Chrome 服务器的 HTTP 调用复用独立简化 `httpx` 客户端（避免缓存/中间件/限流）：

```python
class BrowserSession:
    """交互式浏览器会话客户端，用于签到等多步流程。"""

    def __init__(self, site_key: str, *, fingerprint="stealth",
                 user_agent=None, proxy_url=None): ...

    def __enter__(self) -> "BrowserSession":     # POST /sessions（幂等）
        # 内部通过 make_session_key(site_key, config) 生成 session_key
        ...
    def __exit__(self, *exc):                     # 可选：DELETE /sessions/{id}
        ...

    # —— 导航与读取（自动过盾，Cookie 入会话）——
    def navigate(self, url, *, cookie=None, referer=None, timeout=30) -> dict:
        # POST /sessions/{id}/navigate -> {html, cookies, challenge}
        ...
    def html(self) -> str:                        # GET  /sessions/{id}/html
        ...
    def cookies(self, domain=None) -> dict:       # GET  /sessions/{id}/cookies
        ...

    # —— 交互原语 ——
    def click(self, selector: str) -> None:       # POST /sessions/{id}/click
        ...
    def input(self, selector: str, text: str) -> None:  # POST /sessions/{id}/input
        ...
    def execute(self, script: str):               # POST /sessions/{id}/execute
        ...

    # —— 交互后复用会话 Cookie 走 HTTP 快路径 ——
    def fetch(self, url, method="GET", **kwargs) -> dict:  # POST /sessions/{id}/fetch
        ...
```

#### 签到改造示例（`ChromeSigninSimulator`）

```python
def signin(self, site_info: dict, plugin_ctx) -> str:
    site = site_info.get("name")
    home_url = StringUtils.get_base_url(site_info.get("signurl"))
    site_key = site_info.get("domain") or site
    with BrowserSession(
        site_key=site_key,                                   # 与 ChromeTransport 同一会话键
        user_agent=site_info.get("ua"),
        proxy_url=_proxy(site_info),
    ) as sess:
        result = sess.navigate(home_url, cookie=site_info.get("cookie"))  # 自动过盾
        html_text = result["html"]
        if re.search(r"已签|签到成功", html_text):
            return f"[{site}]今日已签到"
        # 找签到按钮 XPath（沿用现有 siteconf.get_checkin_conf）
        xpath = self._match_checkin_xpath(html_text)
        if not xpath:
            return f"[{site}]模拟登录成功"
        sess.click(f"xpath:{xpath}")                    # 点击签到
        html_text = sess.html()                          # 点击后重新取 HTML
        return self._judge_result(site, html_text)
```

验证码类（如 tjupt）：图像识别答案仍用 `HttpClient` 做（豆瓣/Google 识图），命中后：
- 站点走普通 HTTP 提交：直接 `HttpClient` `POST`（现状保留）；
- 若提交前有 Cloudflare，则用 `BrowserSession.navigate` 过盾后 `sess.fetch(...)` 提交，复用会话 Cookie。

#### 异步版本

后端存在 `AsyncHttpClient`（如 `image_proxy`）。浏览器交互目前多为同步签到流程，但 `BrowserSession` 应同时提供 `AsyncBrowserSession`（`async with` 版本），供异步路径调用，与 `AsyncChromeTransport` 对齐。

#### 与 transport 的分工

| 场景 | 走法 | 说明 |
|---|---|---|
| 抓 HTML / API（单次请求） | `HttpClient(browser=...)` → `ChromeTransport` | 透明，196 调用点改动极小 |
| 签到 / 登录 / 点击 / 输入 / 执行 JS | `BrowserSession`（直连 Session API） | 多步有状态流程 |
| 交互完成后再取数据 | `BrowserSession.fetch()` | 复用同一会话 Cookie，走 HTTP 快路径 |

两者**共用同一个会话隔离键**（站点域名）：签到 `BrowserSession` 过盾产生的 Cookie 存在同名 session，后续该站点的 `HttpClient(browser)` 请求可直接命中同一 session 的 Cookie，无需重复过盾。

### 8. 移除旧 `ChromeClient`（不保留兼容）

旧 `ChromeClient`（`src/app/infrastructure/chrome/client.py`）**全部移除，不做兼容层**。它仍在调用 Chrome 服务器早已移除的 `/tabs` 路由，属 404 死代码，保留兼容只会拖累维护。

- **Backend**：删除 `ChromeClient`，现有 6 处调用改写：
  - 纯抓取场景（`site_userinfo` / `site_resolver` / `autogenrss`）→ `HttpClient` 浏览器模式（`ChromeTransport`）。
  - 交互场景（`autosignin` / `tjupt` / `weworkipchange`）→ `BrowserSession`（并补充 `AsyncBrowserSession` 给异步路径）。
  - `app.infrastructure.chrome.__init__` 改为导出 `BrowserSession` / `AsyncBrowserSession`，不再导出 `ChromeClient`。
- **Chrome 服务器**：`/tabs` 路由已随 Session 重构移除，仅需清理 `README` / `PKG-INFO` 文档残留。
- **迁移策略**：按模块逐步替换，**同一模块内不保留新旧并存**；跨模块可分批提交，但每个模块内必须完整切换。如因依赖关系必须分步，可短暂保留 shim，但应在后续 PR 立即清理。

## Chrome 服务器侧改动（nexus-media-chrome）

现有 Session API 基本满足，需补齐 transport 诉求：

### 1. `POST /sessions` 幂等化

已存在会话时返回 200（当前抛 409）。建议服务端实现 `get_or_create`，或 transport 容忍 409。

### 2. 新增聚合端点 `POST /sessions/{id}/request`

把「按需 navigate 过盾 + fetch」合并为一次调用，减少 backend↔chrome 往返：

```json
// POST /sessions/{id}/request
{
    "url": "https://protected.com/api",
    "method": "GET",
    "headers": {},
    "data": null,
    "navigate_if_challenge": true,
    "return_html": false,
    "timeout": 30
}

// Response
{
    "code": 0,
    "data": {
        "status_code": 200,
        "headers": {},
        "body": "...",
        "html": "...",
        "challenge": {"detected": true, "type": "cloudflare", "solved": true},
        "cookies_used": ["cf_clearance", "session"]
    }
}
```

服务端逻辑：内部先 `fetch`，若命中挑战特征则自动 `navigate` 过盾 → 再 `fetch`，一步返回。backend transport 逻辑收敛为一次 HTTP 调用。

**挑战检测规则（服务端实现）**：

| 触发条件 | 说明 |
|---|---|
| 状态码 403 / 503 / 429 | 常见 WAF 拦截状态码 |
| 响应头含 `cf-mitigated` / `server: cloudflare` 且状态非 200 | Cloudflare 特征 |
| 响应体包含挑战标识 | 如 `Just a moment...`、`cf-turnstile-response`、`Checking your browser`、五秒盾倒计时、雷池 `safeline` 等 |
| `navigate_if_challenge=true` 且命中以上任一 | 自动走 `navigate` 过盾 |

最多执行一次 navigate 回退；若一次过盾仍失败，则返回 `challenge.solved=false`，由 backend 的 tenacity 重试策略决定是否重试。

`body` 与 `html` 字段：
- `return_html=false` 时，返回 HTTP 原始响应体 `body` 和 `headers`。
- `return_html=true` 时，先 `navigate` 到目标 URL，返回 `html`（浏览器 DOM 序列化），并附带 `status_code` 与 `headers`（用最终页面 URL 的响应头填充）。
- 服务端返回的 JSON 中 `headers` 必须包含 `Content-Type`，否则 backend 无法正确编码和解析。

### 3. 补充能力

- navigate/session 支持 `proxy`（确保 tab 级生效）。
- `/status` 返回浏览器就绪状态（已有），供 backend 探活缓存复用。
- 会话 TTL / 空闲回收：backend 长期运行会累积 session，服务端加 `last_active` + 后台清理，避免 tab 泄漏。

### 4. 清理 `/tabs` 文档残留

Chrome 服务器代码中 `/tabs` 路由**已随 Session 重构移除**（`main.py` 仅注册 `sessions_router`），仅 `README` / `PKG-INFO` 文档尚有残留。同步清理这些过时文档，避免误导。

### 5. 安全与日志脱敏

Chrome 服务器会接触站点 Cookie、请求头、响应 HTML，必须避免敏感信息泄露：

- **日志禁止打印** `Cookie`、`Authorization`、`Proxy-Authorization`、`X-Api-Key` 等请求头内容。
- **日志禁止打印**完整响应 HTML 或响应体（可记录 URL、状态码、 challenge 类型、耗时）。
- **Session 数据不落盘**：Cookie 仅保存在内存中的 session 对象，不持久化到文件或日志。
- **请求头白名单**：`/sessions/{id}/request` 透传给目标站点的 headers 应按需透传，避免把 Chrome 服务器内部头（如 `Host`）误发。
- **超时保护**：所有浏览器操作必须有硬超时，防止无头页面卡死占用资源。

### 6. 浏览器自动化使用边界

浏览器 transport **仅用于 HTML/API 抓取与过盾**，不适用于以下场景：

| 不适用场景 | 原因 | 替代方案 |
|---|---|---|
| 下载种子文件等大文件 | 二进制大文件经 Chrome 服务器中转，性能差、易超时 | 在 `HttpClient` 中显式禁用 browser 模式，用直连或已获取的 Cookie 下载 |
| 大文件上传 | 同上 | 直连 |
| 长流式响应 | 浏览器 transport 返回的是完整内存响应 | 直连 |
| WebSocket / SSE | 非 request/response 语义 | 不适用浏览器自动化 |

调用点应在发起下载前判断：如果是 `.torrent` / 大文件下载 URL，构造 `HttpClientConfig(browser=None)` 或临时关闭 `browser.enabled`。


## 数据流（站点搜索为例）

```
html_searcher.get(url)
  └─ HttpClient(browser.enabled=True, site_key=site.domain)
       └─ ChromeTransport.handle_request
            ├─ POST /sessions {id:site.domain:stealth:ua_hash:proxy_hash, ...}  (幂等，含配置指纹)
            ├─ POST /sessions/{domain_hash}/request {url, return_html:False}
            │     ├─ 浏览器已有有效 cf_clearance → 直接 HTTP 命中
            │     └─ 命中 Cloudflare → 自动 navigate 过盾 → 再取
            └─ 组装 httpx.Response(200, body=html)
  └─ res.text → 上层解析种子列表（代码不变）
```

后续同域名请求复用同一 session 的 Cookie，走快速 HTTP 路径，仅在 Cookie 失效时才重新过盾。

## 关键设计权衡

| 决策 | 选择 | 理由 |
|---|---|---|
| 集成点 | 自定义 Transport | 196 调用点改动极小（仅增加 `browser=` 参数），复用重试 / 缓存 / 限流 |
| 会话粒度 | 按站点域名 | Cookie 隔离与复用的平衡 |
| 过盾触发 | fetch 优先 + 挑战回退 navigate | 快路径优先，仅必要时启动浏览器 |
| Cookie 存储 | Chrome 服务器 session 持有 | backend 无状态，避免 `cf_clearance` 同步复杂度 |
| 交互场景 | `BrowserSession` 直连 Session API（不走 transport） | click/input/execute 是多步有状态流程，非 request/response 语义 |
| 同步 / 异步 | 双 Transport + `BrowserSession` / `AsyncBrowserSession` | 对齐现有 `HttpClient` / `AsyncHttpClient` 双栈 |

## Consequences

### 正面

- 对 196 个 `HttpClient` 调用点基本透明：只需在构造 `HttpClient` 时增加 `browser=build_browser_mode(...)`，上层 `.get()`/`.post()`/`.text`/`.json()` 解析逻辑完全不变。
- 浏览器过盾能力自动继承重试、缓存、限流、DNS 映射。
- Cookie 由 Chrome 服务器 session 统一托管复用，减少重复过盾。
- 修复当前 `ChromeClient` 与 Chrome 服务器的 `/tabs` 契约错配。

### 负面 / 风险

- 依赖外部 Chrome 服务器可用性；`chrome_server_host` 未配置时须优雅降级为直连。若已配置但服务器不可达，当前设计**不静默回退**（避免在已知有 WAF 的站点上直接请求被拉黑），应抛明确异常。
- transport 内嵌「过盾 + 重试」增加单请求延迟；需限制自动 navigate 回退次数（建议最多 1 次）。
- `render_html=True` 的渲染 HTML 与原始 HTML 结构不同（`<tbody>` 等），若归一化遗漏会导致 90 个站点的 `> tr` 规则失配；已通过解析层剥离 `<tbody>` 兜底，需单测保障。
- 大文件下载/上传不能走浏览器 transport，调用点需显式关闭。
- 长期运行需 Chrome 服务器实现会话回收，否则 tab 泄漏。
- 需前后端协同发布：Chrome 服务器先上线 `POST /sessions/{id}/request` 与幂等 `POST /sessions`，backend 再对接。

## 测试策略

每个核心模块都需要独立单测，通过 mock Chrome 服务器避免依赖真实浏览器：

| 测试对象 | 关键场景 |
|---|---|
| `ChromeTransport` / `AsyncChromeTransport` | 挑战触发 navigate 回退；已有 Cookie 直接 fetch；`httpx.Response` 编码/headers 正确；连接池 key 随配置变化；服务器不可达时抛明确异常 |
| `build_browser_mode` / `make_session_key` | 站点开关关闭返回 None；配置变化生成新 session_key；`render_html` 从 `site_info` 读取 |
| `BrowserSession` / `AsyncBrowserSession` | 创建/退出 session；`navigate` 过盾；`click`/`input`/`execute` 调用正确端点；`fetch` 复用 Cookie |
| HTML 归一化 | 渲染 HTML 含 `<tbody>` 时 `> tr` 选择器命中；含 `<thead>`/`<tfoot>` 时扁平化后命中；原始 HTML 路径不变 |
| Cookie 合并 | session Cookie 优先于请求传入 Cookie；同名键覆盖正确；不同名键合并 |
| 集成测试 | 起真实 Chrome 服务器容器，对 1 个测试站点走完整「过盾 → fetch → 解析」流程 |

## 落地顺序（增量）

1. Chrome 服务器：`POST /sessions` 幂等 + `POST /sessions/{id}/request` 聚合端点 + 会话回收。
2. Backend：`BrowserModeConfig` + `ChromeTransport`（同步先行）+ `_make_key` / `_build_client` 接入。
3. Backend：`build_browser_mode`（从 `site_info` 读取用户维护的站点开关，含 `render_html`）。
4. Backend：渲染 HTML 归一化（剥离 `<tbody>`）+ 单测覆盖 `> tr` 直接子选择器场景。
5. 试点 1 个 Cloudflare 站点（`site_resolver` / `html_searcher`）验证抓取路径（默认 `render_html=False`）。
6. 试点 1 个被 WAF 拦截的 API 站点（`api_searcher`）验证 `render_html=False` 下过盾 fetch JSON。
7. Backend：`BrowserSession` 交互客户端；迁移 `autosignin` 签到到 `BrowserSession` 验证交互路径。
8. 异步 `AsyncChromeTransport` + `AsyncHttpClient` 接入。
9. 删除旧 `ChromeClient`，6 处调用按模块逐步改写（同一模块内不保留新旧并存）：
   - 纯抓取场景 → `HttpClient` 浏览器模式（`ChromeTransport`）。
   - 交互场景 → `BrowserSession` / `AsyncBrowserSession`。
   - 清理 Chrome 服务器 `/tabs` 文档残留。
10. 补测试：transport 单测 + `BrowserSession` 单测（均 mock Chrome 服务器）+ HTML 归一化单测 + Cookie 合并单测 + 集成测试。
