# ADR-011: 站点认证配置 UX 改进

## Status

Implemented — 采用独立字段方案

## Date

2026-06-03（决策）/ 2026-06-03（实施完成）

## Context

### 当前问题

当前站点配置中，认证信息（cookie / api_key / bearer_token）全部塞进一个 `COOKIE` 字段，并通过 JSON 格式的 `headers` 字段传递额外请求头。这导致：

1. **字段语义模糊**：`COOKIE` 字段根据 `auth_type` 可能代表 cookie、api_key 或 bearer_token，新手用户难以理解
2. **headers 配置复杂**：用户需要手写 JSON 来配置 `x-api-key`、`Authorization` 等头，容易写错格式
3. **前端表单不友好**：前端只有一个 "Cookie/Headers" 大文本框，没有针对性的输入控件
4. **代码逻辑混乱**：`_build_headers()` 需要解析 `auth_type` 来判断 `COOKIE` 字段的实际含义，并回退到 `api_key` 字段

### 现有代码

```python
# engine_tools.py
if auth_type == "api_key":
    hdr = site.api.auth.get("header_name", "x-api-key")
    key = user_config.get("cookie", "") or user_config.get("api_key", "")
    if key:
        headers[hdr] = key
elif auth_type == "bearer":
    token = user_config.get("cookie", "") or user_config.get("api_key", "")
    if token and not token.startswith("Bearer "):
        token = f"Bearer {token}"
    if token:
        headers["Authorization"] = token
elif auth_type == "cookie":
    cookie = user_config.get("cookie", "")
    if cookie:
        headers["Cookie"] = cookie
```

### 数据库现状

```python
class CONFIGSITE(Base):
    COOKIE: Mapped[str] = mapped_column(Text)   # 被重载使用
    # 缺少独立的 api_key、bearer_token 字段
```

## Decision

### 目标

1. **前端表单**：将 `cookie`、`api_key`、`bearer_token` 拆分为独立输入框
2. **headers 降级为高级选项**：默认隐藏，仅专业用户手动覆盖请求头
3. **向后兼容**：现有配置不丢失，迁移期内旧逻辑继续工作
4. **代码清晰**：`_build_headers()` 直接从独立字段读取认证信息，不再回退

### 方案

#### 1. 数据库扩展（Alembic 迁移）

采用**独立字段**方案：

```python
class CONFIGSITE(Base):
    COOKIE: Mapped[str | None] = mapped_column(Text, nullable=True)
    API_KEY: Mapped[str | None] = mapped_column(Text, nullable=True)      # 新增
    BEARER_TOKEN: Mapped[str | None] = mapped_column(Text, nullable=True) # 新增
    HEADERS: Mapped[str | None] = mapped_column(Text, nullable=True)      # 高级选项
```

**设计原则**：
- 全局认证由 `auth_type` 决定，使用对应字段（cookie/api_key/bearer_token）
- 端点特定认证通过模板占位符（如 `{apikey}`、`{passkey}`）使用其他字段
- 所有字段都可以同时填写，代码按需取用

#### 混合认证场景处理

**场景示例**：某站点通用接口用 Bearer，但搜索端点需要 API Key

| 配置项 | 值 | 用途 |
|--------|-----|------|
| `auth_type` | `bearer` | 全局认证类型 |
| `BEARER_TOKEN` | `eyJhbG...` | `_build_headers()` 设置 `Authorization` |
| `API_KEY` | `abc123` | 搜索端点模板 `{apikey}` 占位符替换 |

**代码实现**：

```python
def _build_headers(engine, site, user_config):
    headers = {}
    auth = None
    auth_type = site.api.auth.get("type", "")

    # 全局认证：由 auth_type 决定
    if auth_type == "bearer":
        token = user_config.get("bearer_token", "")
        if token:
            auth = BearerAuth(token)
    elif auth_type == "cookie":
        cookie = user_config.get("cookie", "")
        if cookie:
            auth = CookieAuth(cookie)
    elif auth_type == "api_key":
        hdr = site.api.auth.get("header_name", "x-api-key")
        key = user_config.get("api_key", "")
        if key:
            headers[hdr] = key

    # 端点特定认证：通过 _resolve_auth_tokens() 收集
    # 这些令牌不设置全局头，由请求模板占位符使用
    return headers, auth

def _resolve_auth_tokens(engine, site, user_config):
    tokens = {}
    # 同时收集所有可能的认证令牌
    if user_config.get("api_key"):
        tokens["apikey"] = user_config["api_key"]
    if user_config.get("cookie"):
        tokens["cookie"] = user_config["cookie"]
    # passkey/csrf 通过动态获取
    return tokens
```

**模板使用**：

```json
{
  "path": "/api/search",
  "body": {
    "api_key": "{apikey}",
    "keyword": "{keyword}"
  }
}
```

#### 2. `_build_auth()` 重构（替代 `_build_headers()`）

拆分职责：
- `_build_auth()` — 处理全局认证（返回 `headers, auth`）
- `_resolve_auth_tokens()` — 收集所有可用令牌（供模板占位符使用）

```python
def _build_auth(engine: Any, site: Any, user_config: dict) -> tuple[dict, httpx.Auth | None]:
    """构建全局认证（每个请求通用）"""
    headers = {}
    auth = None
    auth_type = site.api.auth.get("type", "") if site.api else ""

    if auth_type == "api_key":
        hdr = site.api.auth.get("header_name", "x-api-key")
        key = user_config.get("api_key", "")
        if key:
            headers[hdr] = key
    elif auth_type == "bearer":
        token = user_config.get("bearer_token", "")
        if token:
            auth = BearerAuth(token)
    elif auth_type == "cookie":
        cookie = user_config.get("cookie", "")
        if cookie:
            auth = CookieAuth(cookie)

    # headers 高级选项作为覆盖
    custom_headers = user_config.get("headers", {}) or {}
    if isinstance(custom_headers, str):
        try:
            custom_headers = json.loads(custom_headers)
        except Exception:
            custom_headers = {}
    headers.update(custom_headers)

    headers["User-Agent"] = user_config.get("ua", "")
    return headers, auth
```

#### 3. 前端表单设计

```
站点配置
├── 基本设置
│   ├── 站点名称
│   ├── 站点地址
│   └── 代理开关
├── 认证信息
│   ├── 认证方式: [Cookie | API Key | Bearer | 无]  ← 下拉选择
│   ├── Cookie: [____________]  ← auth_type=cookie 时显示
│   ├── API Key: [____________] ← auth_type=api_key 时显示
│   ├── Bearer Token: [________] ← auth_type=bearer 时显示
│   └── ⚠️ 混合认证提示
│       "搜索/下载端点若需要额外认证，请填写下方字段"
├── 额外认证（可选）
│   ├── Cookie (备用): [____________]
│   ├── API Key (备用): [____________]
│   └── Bearer Token (备用): [________]
└── 高级选项（默认折叠）
    └── 自定义请求头 (JSON): [_______]
```

**混合认证 UX**：
- 主认证方式决定全局请求头（如 Bearer）
- 备用认证字段用于端点模板占位符（如搜索端点的 `{apikey}`）
- 提示文案说明："当前站点主认证为 Bearer，搜索接口需额外 API Key，请同时填写"

#### 4. 向后兼容策略

**迁移期（2 个版本）**：
1. `user_config` 构建时自动回退：
   ```python
   cookie = user_config.get("cookie", "")
   if not cookie and user_config.get("api_key"):
       # 旧配置回退
       cookie = user_config.get("api_key")
   ```
2. 数据库迁移脚本将旧 `COOKIE` 字段内容按 `auth_type` 迁移到新字段

**废弃期**：
- `_build_headers()` 移除回退逻辑，报错提示用户更新配置

## Consequences

### 正面影响

1. **UX 提升**：用户无需理解 JSON 格式，只需填写对应认证字段
2. **混合认证清晰**：主认证（全局）与备用认证（端点特定）分离，避免字段重载歧义
3. **安全性提升**：Bearer Token 不再暴露在 headers 文本框中，可使用密码输入框
4. **代码简化**：`auth.py` 的 `CookieAuth`/`BearerAuth`/`ApiKeyAuth` 可直接使用
5. **可维护性**：新增认证类型（如 OAuth2）只需新增字段和 `Auth` 子类

### 负面影响

1. **数据库迁移**：需要 Alembic 脚本，对已有数据做格式转换
2. **前后端协同**：需要前端仓库配合修改表单组件
3. **过渡期复杂度**：需要维护新旧两套配置的兼容逻辑

### 已决策事项

1. **采用独立字段** ✅ — `COOKIE` / `API_KEY` / `BEARER_TOKEN` 三个独立字段
2. `headers` 保留为独立 `HEADERS` 字段（Text），默认折叠，仅高级用户手动配置
3. 迁移脚本由 Alembic 执行，随版本升级自动运行

### 实施记录

| 步骤 | 状态 | 内容 | 涉及文件 |
|------|------|------|---------|
| 1 | ✅ | Alembic 迁移：新增 `API_KEY`、`BEARER_TOKEN`、`HEADERS` 字段，迁移旧数据 | `alembic/versions/f82cb58980d0...` |
| 2 | ✅ | 更新 `CONFIGSITE` 模型 | `src/app/db/models/config.py` |
| 3 | ✅ | 更新 `SiteEntity` 领域实体 | `src/app/domain/entities/site.py` |
| 4 | ✅ | 更新 Repository/Adapter | `src/app/db/repositories/site_repository.py`<br>`src/app/db/repositories/site_repo_adapter.py` |
| 5 | ✅ | 更新 Sites 类构建 user_config | `src/app/sites/sites.py` |
| 6 | ✅ | 重构 `_build_headers()` 为 `_build_auth()` | `src/app/sites/engine_tools.py`<br>`src/app/sites/engine.py`<br>`src/app/sites/api_searcher.py` |
| 7 | ✅ | 更新 API Router | `src/api/routers/site.py`<br>`src/app/services/site_service.py` |
| 8 | ✅ | 前端表单改造 | `frontend/apps/nexus-media/src/views/site/list/index.vue`<br>`frontend/apps/nexus-media/src/api/modules/site.ts`<br>`frontend/apps/nexus-media/src/store/site.ts`<br>`frontend/apps/nexus-media/src/components/subscribe/SubscribeEditModal.vue` |

### 质量验证

- `uv run ruff check .` — 通过
- `uv run pyright src/ tests/` — 0 errors
- `uv run pytest tests/` — 642 passed
- 前端 `pnpm run typecheck` — 无新增错误

## Related Decisions

- [ADR-010: HTTP Client 迁移到 httpx](ADR-010-http-client-httpx.md) — `auth.py` 已提供 `CookieAuth`/`BearerAuth`/`ApiKeyAuth`
