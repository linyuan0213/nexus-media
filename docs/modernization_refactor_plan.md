# Nexus Media 现代化重构计划

> **版本**：v1.0  
> **日期**：2026-04-16  
> **范围**：Web 层（`web/`）、应用层（`app/services/`）、领域层（`app/domain/`）、基础设施层（`app/db/repositories/`）

---

## 1. 背景与目标

### 1.1 现状问题

Nexus Media 在早期采用典型的 **Flask + Jinja2 后端渲染** 模式快速迭代，导致以下技术债务：

1. **God Class 问题**：`web/action.py` 通过 Mixin 继承组合了一个包含 200+ 命令的巨型 `_actions` 字典，职责混乱、难以测试。
2. **API 双轨制**：Web 前端走 `/api/web/...`（Blueprint），外部 API 走 `/api/v1/...`（flask-restx），两者大量重复薄 wrapper。
3. **无显式分层**：Controller 直接调用全局单例（`Downloader()`、`Sites()`），业务逻辑、数据访问、路由处理混杂在一起。
4. **裸 dict 传参**：没有统一的请求/响应 Schema，字段类型和校验全靠运行时猜测。
5. **测试困难**：单元测试需要大量 monkey-patch 全局单例，集成测试覆盖成本高。

### 1.2 重构目标

建立 **"分层清晰、依赖向内、接口统一、测试友好、最终可迁移到 FastAPI"** 的现代化架构：

- **Controller 变薄**：只做路由、认证、序列化、异常拦截。
- **Service 层独立**：业务用例可脱离 Web 框架上下文进行单元测试。
- **DTO/Schema 显式化**：请求和响应都有明确的 Pydantic 模型，与 FastAPI 原生兼容。
- **Repository 完整化**：数据库访问收口到 Repository，领域层不依赖具体 ORM 或框架。
- **API 统一**：Web 和 APIv1 共享同一套 Service，消灭双写重复。
- **为 FastAPI 奠基**：P0~P2 的所有设计都服务于最终把表现层从 Flask 迁移到 FastAPI。

---

## 2. 目标架构（Clean Architecture）

```text
                    当前过渡态
┌─────────────────────────────────────────────────────┐
│  Presentation（表现层）                              │
│  • Web Controllers (Flask Blueprint)   /api/web/... │
│  • APIv1 Resources (flask-restx)       /api/v1/...  │
│  • CLI / Message Bot / Scheduler                    │
├─────────────────────────────────────────────────────┤
│  Application（应用层）                               │
│  • Services / UseCases                              │
│  • DTOs (Pydantic)                                  │
├─────────────────────────────────────────────────────┤
│  Domain（领域层）                                    │
│  • Entities / Value Objects                         │
│  • Domain Services                                  │
│  • Repository Interfaces (Protocol)                 │
├─────────────────────────────────────────────────────┤
│  Infrastructure（基础设施层）                        │
│  • ORM / DB Repositories                            │
│  • External Clients (TMDB, PT Sites, Downloader)    │
│  • FileSystem / Cache / Message Queue               │
└─────────────────────────────────────────────────────┘
                              ↓ 最终迁移
                    目标态 (FastAPI)
┌─────────────────────────────────────────────────────┐
│  Presentation（表现层）                              │
│  • FastAPI APIRouter                    /api/...    │
│  • Jinja2 模板渲染（保留）              /page/...    │
│  • CLI / Message Bot / Scheduler                    │
├─────────────────────────────────────────────────────┤
│  Application（应用层）                               │
│  • Services / UseCases   (P0~P2 产物，零改动复用)    │
│  • DTOs (Pydantic)       (FastAPI 原生兼容)          │
├─────────────────────────────────────────────────────┤
│  Domain（领域层）                                    │
│  • Entities / Value Objects                         │
│  • Domain Services                                  │
│  • Repository Interfaces                            │
├─────────────────────────────────────────────────────┤
│  Infrastructure（基础设施层）                        │
│  • ORM / async DB Repositories                      │
│  • External Async Clients                           │
│  • FileSystem / Cache / Message Queue               │
└─────────────────────────────────────────────────────┘
```

**核心原则**：

1. **依赖向内**：外层可以调用内层，内层不 import 外层（Controller → Service → Domain）。
2. **接口隔离**：Repository 先定义接口，再由基础设施实现。
3. **单一职责**：Controller 不编排业务，Service 不直接操作 HTTP 请求。
4. **DTO 防腐**：请求参数和返回体都用显式 Schema，拒绝裸 dict 裸 tuple 满天飞。

---

## 3. 当前差距分析

| 维度 | 现代化标准 | Nexus Media 现状 | 最终目标 (P3) |
| :--- | :--- | :--- | :--- |
| **分层** | Controller → Service → Domain → Repo | 200+ 命令混在 `WebAction`，Controller 即业务层 | FastAPI Router → Service → Domain → async Repo |
| **依赖方向** | 内层不依赖外层 | `web/controllers/download.py` 直接 `import app.downloader.Downloader` 单例 | 严格向内依赖，领域层零框架耦合 |
| **DTO/Schema** | Pydantic / Marshmallow 显式校验 | 裸 `dict` 通过 `@parse_json_data` 注入 | Pydantic 原生集成，自动校验与文档生成 |
| **Repository** | 接口 + 实现分离 | `app/db/repositories` 已起步，但大量代码仍直接调用 `DbHelper().xxx` | async Repository，ORM 可替换为 async SQLAlchemy |
| **API 统一** | 一套 API，多入口复用 | Web (`/api/web/xxx`) 和 APIv1 (`/api/v1/xxx`) 大量重复薄 wrapper | 统一 FastAPI Router，Web 与 OpenAPI 同构 |
| **测试** | Service/Domain 可单元测试 | 需要 monkey-patch 全局单例，集成测试为主 | Service/Domain 纯同步/异步可测，Controller 由框架保障 |
| **异步** | FastAPI / async SQLAlchemy | Flask sync，高 IO 场景阻塞 | 全链路 async/await，外部 IO 非阻塞 |

---

## 4. 分阶段重构方案

### P0：接口收敛 + 消灭 God Class（1~2 周）

**目标**：先把后端从"巨型 `_actions` 字典"拆成可维护的 REST 路由，并让 Web 与 APIv1 共享同一套 Controller。

#### 已完成
- [x] `WebAction` 拆分为 13 个独立 Flask Blueprint Controller（`web/controllers/`）。
- [x] 前端 `CMD_URL_MAP` 移除，`ajax_post` 直接调用 `/api/web/...` URL。
- [x] 修复重构后的运行时问题（415、404、TypeError、JSONDecodeError、RecursionError 等）。

#### 待完成
- [ ] **APIv1 复用 Controller**：将 `web/apiv1.py` 中直接调用业务逻辑的 Resource 改为 `from web.controllers.xxx import func`，消除重复 wrapper。
- [ ] **认证统一**：提取 `@any_auth` 装饰器（同时兼容 Session 和 Token），让 Controller 函数可被 Web 和 APIv1 无差别调用。
- [ ] **聚合接口瘦身**：`apiv1.py` 只保留跨 domain 组装数据的编排型接口（如大盘数据），单领域接口全部下沉到各自 Controller。

#### 交付物示例
```python
# web/controllers/download.py
@download_bp.route('/pt_start', methods=['POST'])
@any_auth
@parse_json_data
def pt_start(data):
    ...
    return success(...)

# web/apiv1.py
@download.route('/start')
class DownloadStart(ClientResource):
    def post(self):
        from web.controllers.download import pt_start
        return pt_start(self.parser.parse_args())
```

---

### P1：提取 Service 层 + DTO 化（3~4 周）

**目标**：让 Controller 变薄，业务逻辑下沉到可独立测试的 Service。

#### 任务清单
1. **新建 `app/services/` 目录**
   按领域拆分 Service：
   - `download_service.py` — 下载任务、下载器管理
   - `rss_service.py` — 订阅、自定义 RSS
   - `sync_service.py` — 文件整理、目录同步
   - `site_service.py` — 站点配置、站点统计
   - `brush_service.py`、`filter_service.py`、`media_service.py` 等

2. **新建 `app/schemas/` 目录（Pydantic）**
   定义显式的请求和响应模型：
   ```python
   from pydantic import BaseModel

   class PtStartRequest(BaseModel):
       id: str

   class PtStartResponse(BaseModel):
       code: int
       retcode: str
       id: str | None
   ```

3. **Service 设计规范**
   - Service 是纯函数/类，接收 DTO，返回 DTO。
   - 不依赖 `request`、`current_user`、`g` 等 Flask 全局对象。
   - 需要用户上下文时，通过显式参数传入（如 `user_id: int`）。
   - 需要外部依赖时，通过构造函数注入（如 `def __init__(self, site_repo: ISiteRepository)`）。

4. **Controller 职责限定**
   Controller 只负责：
   1. 认证 / 鉴权
   2. `request.get_json()` → Pydantic DTO
   3. 调用 Service
   4. Service 返回 → `jsonify()` / `web.core.response.success()`

#### 交付物结构
```text
app/
├── services/
│   ├── __init__.py
│   ├── download_service.py
│   ├── rss_service.py
│   ├── sync_service.py
│   └── ...
├── schemas/
│   ├── __init__.py
│   ├── download.py
│   ├── rss.py
│   └── ...
```

---

### P2：Repository 完整化 + 领域层独立（6~8 周）

**目标**：彻底隔离数据库和外部依赖，让核心逻辑可脱离 Flask/SQLAlchemy 进行单元测试。

#### 任务清单
1. **新建 `app/domain/` 目录**
   - `entities/`：核心领域对象（如 `SiteEntity`、`TorrentEntity`）。
   - `interfaces/`：Repository 接口（Python `Protocol`）。
   - `services/`：跨实体的领域服务。

2. **Repository 接口化**
   所有数据库访问收口到 `app/db/repositories/`，并对接口编程：
   ```python
   # app/domain/interfaces/site_repo.py
   from typing import Protocol
   from app.domain.entities.site import SiteEntity

   class ISiteRepository(Protocol):
       def get_by_id(self, site_id: int) -> SiteEntity | None: ...
       def list_all(self) -> list[SiteEntity]: ...
       def update(self, site: SiteEntity) -> None: ...
   ```

3. **ORM 实现隔离**
   `app/db/repositories/site_repo.py` 使用 SQLAlchemy 实现 `ISiteRepository`，但在转换层把 ORM model 映射为 `SiteEntity`。

4. **依赖注入**
   Service 层不再 `from app.downloader import Downloader`，而是通过构造函数注入：
   ```python
   class DownloadService:
       def __init__(self, repo: ISiteRepository, downloader: IDownloaderClient):
           self._repo = repo
           self._downloader = downloader
   ```

5. **全局单例渐进解耦**
   现有 `Downloader()`、`Sites()` 等单例暂不删除，但新建 Service 一律通过注入使用，为后续替换为工厂/IOC 容器做准备。

#### 交付物结构
```text
app/
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── site.py
│   │   └── torrent.py
│   ├── interfaces/
│   │   ├── site_repo.py
│   │   └── downloader_client.py
│   └── services/
│       └── torrent_aggregator.py
├── db/
│   └── repositories/
│       ├── site_repo.py
│       └── torrent_repo.py
```

---

### P3：迁移到 FastAPI（4~6 周）

**目标**：在 P0~P2 已完成分层解耦的基础上，将表现层从 Flask 迁移到 FastAPI，实现框架现代化。

#### 前置条件
- P1 的 `app/services/` 和 `app/schemas/` 已覆盖全部高频接口。
- P2 的 Repository 已接口化，且领域层不依赖 Flask。
- 全量测试用例通过。

#### 任务清单
1. **新建 `api/` 目录（FastAPI 入口）**
   ```text
   api/
   ├── __init__.py
   ├── deps.py           # 依赖注入：当前用户、数据库会话、配置对象
   └── routers/
       ├── __init__.py
       ├── download.py   # 对应原 web/controllers/download.py
       ├── rss.py
       ├── site.py
       └── ...
   ```

2. **FastAPI Router 替代 Flask Blueprint**
   - 每个 Router 直接复用 `app/services/` 和 `app/schemas/`：
     ```python
     from fastapi import APIRouter, Depends
     from app.schemas.download import PtStartRequest, PtStartResponse
     from app.services.download_service import DownloadService
     from api.deps import get_current_user

     router = APIRouter(prefix="/download", tags=["download"])

     @router.post("/pt_start", response_model=PtStartResponse)
     def pt_start(req: PtStartRequest, user=Depends(get_current_user)):
         svc = DownloadService()
         return svc.start(req.id)
     ```
   - 旧 `web/controllers/` 和 `web/apiv1.py` 并行保留，通过环境变量或 Nginx 路由逐步切流。

3. **模板渲染保留**
   - 继续使用 `fastapi.templating.Jinja2Templates`，原 `web/templates/` 目录几乎零改动迁移。
   - 页面路由统一放到 `api/routers/pages.py`，返回 `TemplateResponse`。

4. **认证统一迁移（JWT + Session 双轨）**

   P3 阶段引入 JWT（JSON Web Token）作为标准认证方式，同时兼容现有 Flask Session，实现双轨制平滑过渡。

   #### 4.1 JWT 认证方案设计

   **架构原则**：
   - **Access Token + Refresh Token 双令牌机制**：Access Token 短有效期（15 分钟），Refresh Token 长有效期（7 天）存储于 HttpOnly Cookie
   - **无状态认证**：服务端不存储 Token 状态，JWT 自包含用户身份信息
   - **向后兼容**：Flask Session 登录态在绞杀期内继续有效

   **Token 结构设计**：

   ```python
   # app/schemas/auth.py
   from pydantic import BaseModel
   from datetime import datetime
   from typing import Optional, List

   class TokenPayload(BaseModel):
       """JWT Payload 结构"""
       sub: str                    # 用户唯一标识（username 或 user_id）
       user_id: int                # 用户 ID
       username: str               # 用户名
       level: int                  # 用户等级
       permissions: List[str]      # 权限列表
       iat: datetime               # 签发时间
       exp: datetime               # 过期时间
       jti: str                    # Token 唯一标识（用于撤销）

   class TokenPair(BaseModel):
       """登录返回的 Token 对"""
       access_token: str
       refresh_token: str
       token_type: str = "bearer"
       expires_in: int             # Access Token 有效期（秒）

   class UserContext(BaseModel):
       """从 Token 解析的用户上下文"""
       user_id: int
       username: str
       level: int
       permissions: List[str]
       is_superadmin: bool
   ```

   **核心实现**：

   ```python
   # app/services/auth_service.py
   from datetime import datetime, timedelta
   from jose import JWTError, jwt
   from passlib.context import CryptContext
   from app.schemas.auth import TokenPayload, TokenPair, UserContext

   SECRET_KEY = "your-secret-key"  # 应从配置读取
   ALGORITHM = "HS256"
   ACCESS_TOKEN_EXPIRE_MINUTES = 15
   REFRESH_TOKEN_EXPIRE_DAYS = 7

   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

   class AuthService:
       def __init__(self, user_repo, rbac_service):
           self._user_repo = user_repo
           self._rbac = rbac_service

       def authenticate(self, username: str, password: str) -> Optional[UserContext]:
           """验证用户名密码，返回用户上下文"""
           user = self._user_repo.get_by_username(username)
           if not user or not pwd_context.verify(password, user.password_hash):
               return None
           return UserContext(
               user_id=user.id,
               username=user.username,
               level=user.level,
               permissions=self._rbac.get_user_permissions(user.id),
               is_superadmin=user.is_superadmin
           )

       def create_token_pair(self, user_ctx: UserContext) -> TokenPair:
           """创建 Access + Refresh Token 对"""
           now = datetime.utcnow()
           
           # Access Token
           access_payload = TokenPayload(
               sub=str(user_ctx.user_id),
               user_id=user_ctx.user_id,
               username=user_ctx.username,
               level=user_ctx.level,
               permissions=user_ctx.permissions,
               iat=now,
               exp=now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
               jti=str(uuid.uuid4())
           )
           access_token = jwt.encode(
               access_payload.dict(), SECRET_KEY, algorithm=ALGORITHM
           )
           
           # Refresh Token（仅含 sub 和 jti，用于换取新 Access Token）
           refresh_payload = {
               "sub": str(user_ctx.user_id),
               "jti": str(uuid.uuid4()),
               "iat": now,
               "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
               "type": "refresh"
           }
           refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)
           
           return TokenPair(
               access_token=access_token,
               refresh_token=refresh_token,
               expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
           )

       def refresh_access_token(self, refresh_token: str) -> Optional[TokenPair]:
           """使用 Refresh Token 换取新的 Token 对"""
           try:
               payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
               if payload.get("type") != "refresh":
                   return None
               user_id = int(payload.get("sub"))
               user = self._user_repo.get_by_id(user_id)
               if not user:
                   return None
               ctx = UserContext(
                   user_id=user.id,
                   username=user.username,
                   level=user.level,
                   permissions=self._rbac.get_user_permissions(user.id),
                   is_superadmin=user.is_superadmin
               )
               return self.create_token_pair(ctx)
           except JWTError:
               return None

       def verify_token(self, token: str) -> Optional[UserContext]:
           """验证 Access Token，返回用户上下文"""
           try:
               payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
               if payload.get("type") == "refresh":
                   return None  # Refresh Token 不能用于认证
               return UserContext(
                   user_id=payload.get("user_id"),
                   username=payload.get("username"),
                   level=payload.get("level"),
                   permissions=payload.get("permissions", []),
                   is_superadmin=payload.get("is_superadmin", False)
               )
           except JWTError:
               return None

       def revoke_token(self, jti: str) -> None:
           """撤销 Token（将 jti 加入黑名单，通常配合 Redis 使用）"""
           # 可选实现：配合 Redis 存储撤销列表
           pass
   ```

   **FastAPI 集成**：

   ```python
   # api/deps.py
   from fastapi import Request, HTTPException, status, Depends
   from fastapi.security import OAuth2PasswordBearer, HTTPBearer
   from app.services.auth_service import AuthService, verify_token
   from app.schemas.auth import UserContext

   oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
   http_bearer = HTTPBearer(auto_error=False)

   async def get_current_user(
       request: Request,
       token: str = Depends(oauth2_scheme)
   ) -> UserContext:
       """
       统一认证入口，优先 JWT，兼容 Session
       """
       # 1. 尝试 JWT 认证
       if token:
           user_ctx = verify_token(token)
           if user_ctx:
               return user_ctx
       
       # 2. 兼容 Flask Session（绞杀期）
       session_user = request.session.get("user")
       if session_user:
           return UserContext(
               user_id=session_user.get("id"),
               username=session_user.get("username"),
               level=session_user.get("level", 0),
               permissions=session_user.get("permissions", []),
               is_superadmin=session_user.get("is_superadmin", False)
           )
       
       raise HTTPException(
           status_code=status.HTTP_401_UNAUTHORIZED,
           detail="Not authenticated",
           headers={"WWW-Authenticate": "Bearer"},
       )

   async def get_current_user_optional(
       request: Request,
       token: str = Depends(oauth2_scheme)
   ) -> Optional[UserContext]:
       """可选认证，用于登录页等场景"""
       try:
           return await get_current_user(request, token)
       except HTTPException:
           return None

   async def require_permission(permission: str):
       """权限检查装饰器工厂"""
       def checker(user: UserContext = Depends(get_current_user)):
           if permission not in user.permissions and not user.is_superadmin:
               raise HTTPException(
                   status_code=status.HTTP_403_FORBIDDEN,
                   detail=f"Permission denied: {permission}"
               )
           return user
       return checker
   ```

   **认证路由**：

   ```python
   # api/routers/auth.py
   from fastapi import APIRouter, Response, Request, HTTPException
   from fastapi.security import OAuth2PasswordRequestForm
   from app.schemas.auth import TokenPair
   from app.services.auth_service import AuthService
   from api.deps import get_current_user

   router = APIRouter(prefix="/auth", tags=["authentication"])

   @router.post("/login", response_model=TokenPair)
   async def login(
       response: Response,
       form_data: OAuth2PasswordRequestForm = Depends()
   ):
       """用户登录，返回 JWT Token 对"""
       auth_svc = AuthService()
       user_ctx = auth_svc.authenticate(form_data.username, form_data.password)
       if not user_ctx:
           raise HTTPException(status_code=401, detail="Invalid credentials")
       
       tokens = auth_svc.create_token_pair(user_ctx)
       
       # 将 Refresh Token 写入 HttpOnly Cookie
       response.set_cookie(
           key="refresh_token",
           value=tokens.refresh_token,
           httponly=True,
           secure=True,  # 生产环境启用
           samesite="lax",
           max_age=7 * 24 * 3600  # 7 天
       )
       
       return tokens

   @router.post("/refresh", response_model=TokenPair)
   async def refresh_token(request: Request, response: Response):
       """使用 Refresh Token 换取新 Token"""
       refresh_token = request.cookies.get("refresh_token")
       if not refresh_token:
           raise HTTPException(status_code=401, detail="No refresh token")
       
       auth_svc = AuthService()
       tokens = auth_svc.refresh_access_token(refresh_token)
       if not tokens:
           raise HTTPException(status_code=401, detail="Invalid refresh token")
       
       # 同时刷新 Refresh Token（轮换机制）
       response.set_cookie(
           key="refresh_token",
           value=tokens.refresh_token,
           httponly=True,
           secure=True,
           samesite="lax",
           max_age=7 * 24 * 3600
       )
       
       return tokens

   @router.post("/logout")
   async def logout(response: Response, user=Depends(get_current_user)):
       """登出，清除 Cookie"""
       response.delete_cookie("refresh_token")
       # 可选：将 Access Token 的 jti 加入黑名单
       return {"message": "Logged out"}

   @router.get("/me")
   async def get_current_user_info(user=Depends(get_current_user)):
       """获取当前用户信息"""
       return user
   ```

   **前端适配**：

   ```javascript
   // web/static/js/auth.js - JWT 管理工具
   class JWTManager {
       constructor() {
           this.accessToken = localStorage.getItem('access_token');
           this.refreshPromise = null;
       }

       getAccessToken() {
           return this.accessToken;
       }

       setTokens(accessToken, expiresIn) {
           this.accessToken = accessToken;
           localStorage.setItem('access_token', accessToken);
           // 记录过期时间
           const expiresAt = Date.now() + expiresIn * 1000;
           localStorage.setItem('token_expires_at', expiresAt);
       }

       clearTokens() {
           this.accessToken = null;
           localStorage.removeItem('access_token');
           localStorage.removeItem('token_expires_at');
       }

       isTokenExpired() {
           const expiresAt = localStorage.getItem('token_expires_at');
           if (!expiresAt) return true;
           // 提前 30 秒过期，留出刷新时间
           return Date.now() > parseInt(expiresAt) - 30000;
       }

       async refreshToken() {
           if (this.refreshPromise) return this.refreshPromise;
           
           this.refreshPromise = fetch('/api/auth/refresh', {
               method: 'POST',
               credentials: 'include'  // 携带 HttpOnly Cookie
           })
           .then(res => {
               if (!res.ok) throw new Error('Refresh failed');
               return res.json();
           })
           .then(data => {
               this.setTokens(data.access_token, data.expires_in);
               return data.access_token;
           })
           .finally(() => {
               this.refreshPromise = null;
           });
           
           return this.refreshPromise;
       }

       async getValidToken() {
           if (!this.accessToken || this.isTokenExpired()) {
               return await this.refreshToken();
           }
           return this.accessToken;
       }
   }

   // ajax_post 适配 JWT
   async function ajax_post(cmd, params, handler, async = true, show_progress = true) {
       const jwt = await window.jwtManager.getValidToken();
       
       return $.ajax({
           url: cmd,
           type: 'POST',
           data: JSON.stringify(params),
           contentType: 'application/json',
           headers: jwt ? { 'Authorization': `Bearer ${jwt}` } : {},
           // ... 其他配置
       });
   }
   ```

   #### 4.2 Session 兼容策略（绞杀期）

   | 场景 | 认证方式 | 说明 |
   | :--- | :--- | :--- |
   | 网页端（已迁移到 FastAPI） | JWT + Cookie | 登录后获取 JWT，Access Token 存内存，Refresh Token 存 HttpOnly Cookie |
   | 网页端（未迁移 Flask 页面） | Session | 保持原有 Flask Session 机制 |
   | 第三方 API 调用 | JWT Token | 通过 `/api/auth/login` 获取 Token 后使用 |
   | Webhook（微信/Slack 等） | 无需认证或 IP 白名单 | 保持现有机制 |

   #### 4.3 Token 安全策略

   1. **存储安全**：
      - Access Token：JavaScript 变量（内存），不持久化存储
      - Refresh Token：HttpOnly Cookie，防止 XSS 窃取
   
   2. **传输安全**：
      - 生产环境强制 HTTPS
      - Token 通过 `Authorization: Bearer <token>` 头部传输
   
   3. **失效处理**：
      - Token 过期：前端自动调用 `/api/auth/refresh` 续期
      - 用户禁用/删除：配合 Redis 黑名单机制（可选 P4 实现）
      - 敏感操作（修改密码）：强制重新登录，清除所有 Token
   
   4. **Token 轮换**：
      - 每次使用 Refresh Token 时，同时颁发新的 Refresh Token
      - 旧 Refresh Token 失效，防止重放攻击

5. **异步化基础设施**
   - 外部 HTTP 客户端（TMDB、PT 站点）逐步替换为 `httpx.AsyncClient`。
   - Repository 可选引入 `sqlalchemy.ext.asyncio`，若风险过高可先保持 sync 在线程池中运行。

6. **绞杀式切换**
   - 按领域逐个迁移：先 `system` → `site` → `download` → `rss`。
   - 每迁移一个领域，前端对应 `ajax_post` URL 从 `/api/web/...` 切到 `/api/...`，回滚策略为改 Nginx 配置即可。

#### 交付物结构
```text
nexus-media/
├── api/                      # FastAPI 应用
│   ├── main.py               # FastAPI()
│   ├── deps.py
│   └── routers/
│       ├── download.py
│       ├── site.py
│       ├── rss.py
│       └── pages.py          # Jinja2 模板路由
├── app/
│   ├── services/             # P1 产物，零改动复用
│   ├── schemas/              # P1 产物，FastAPI 原生兼容
│   ├── domain/               # P2 产物，零改动复用
│   └── db/repositories/      # P2 产物，可选 async 化
├── web/                      # 旧 Flask（绞杀期内并行）
│   ├── main.py
│   ├── controllers/
│   └── apiv1.py
```

---

## 5. 迁移原则与风险控制

### 5.1 Strangler Fig（绞杀者模式）

不一次性重写全部代码。每次只选一个领域（如下载 `download` 或订阅 `rss`）完整走通 P0 → P1 → P2，验证无误后再推广到下一个领域。

### 5.2 保持外部契约不变

- 所有 `/api/web/...` 和 `/api/v1/...` URL 路径不变。
- 请求参数、响应体结构不变。
- 前端模板（Jinja2）和外部调用者（如第三方脚本）零感知。

### 5.3 测试先行

- 每提取一个 Service，必须配套 `tests/services/test_xxx_service.py`。
- 每新增一个 Repository 接口实现，必须配套 `tests/db/test_xxx_repository.py`。
- 运行 `uv run pytest tests/` 确保全量回归通过。

### 5.4 避免过度工程

- **P0~P2 阶段**：不引入微服务、不做全量异步改造，在 Flask 现有框架内做分层优化，降低迁移风险。
- **P3 阶段**：只在分层已经清晰的前提下迁移框架，确保 FastAPI 只是“换壳”，而不是“重写业务逻辑”。

---

## 6. 建议实施顺序

| 阶段 | 优先级 | 建议试点领域 | 原因 |
| :--- | :--- | :--- | :--- |
| P0 | 最高 | 全部 13 个 Controller | 已完成大部分，先收尾 APIv1 收敛和认证统一 |
| P1 | 高 | `download` → `rss` → `site` | 这 3 个领域命令最多、逻辑最复杂，Service 化收益最大 |
| P1 | 中 | `sync` → `brush` → `filter` | 次之 |
| P2 | 低 | 从 `site` 和 `download` 开始 | 这两个领域数据库交互最密集，Repository 化价值最高 |
| P3 | 最终 | `system` → `site` → `download` → `rss` | 从简单到复杂，逐步切流验证 FastAPI 稳定性 |

---

## 7. 附录：关键文件路径

| 用途 | 当前路径 | P0~P2 目标路径 | P3 (FastAPI) 目标路径 |
| :--- | :--- | :--- | :--- |
| Web 路由 | `web/controllers/*.py` | 保持不变，仅变薄 | `api/routers/*.py`（逐步替换） |
| APIv1 路由 | `web/apiv1.py` | 保留入口，单领域下沉到 Controller | 合并进 `api/routers/*.py` |
| 页面路由 | `web/main.py` (Jinja2) | 保持不变 | `api/routers/pages.py`（Jinja2Templates） |
| Service 层 | 无 | `app/services/*.py` | `app/services/*.py`（零改动复用） |
| DTO/Schema | 无 | `app/schemas/*.py` | `app/schemas/*.py`（零改动复用） |
| 领域实体 | 无 | `app/domain/entities/*.py` | `app/domain/entities/*.py`（零改动复用） |
| Repository 接口 | 无 | `app/domain/interfaces/*.py` | `app/domain/interfaces/*.py`（零改动复用） |
| Repository 实现 | `app/db/repositories/*.py` | `app/db/repositories/*.py`（补齐剩余领域） | `app/db/repositories/*.py`（可选 async 化） |
| FastAPI 入口 | 无 | 无 | `api/main.py` |

---

## 8. 结语

本次重构的核心是先**在现有 Flask 体系内建立清晰的分层边界**（P0~P2），让 Nexus Media 从"快速堆功能"演进为"可持续维护"的项目。P0 完成后，项目已经具备现代化雏形；P1 和 P2 则是按领域逐步打磨的过程。

当 Service、Schema、Domain、Repository 四层边界清晰后，**P3 的 FastAPI 迁移将只是表现层的"薄壳替换"**，而非伤筋动骨的全量重写。建议始终采用**小步快跑、领域试点、测试先行、绞杀切换**的节奏推进，在保障功能稳定的前提下完成技术栈现代化。

---

## 9. P4：基础设施现代化 + 剩余跨层依赖清理（4~6 周）

**目标**：在 P3 FastAPI 表现层迁移完成后，彻底清理路由层对底层单例/基础设施的直接依赖，使依赖关系严格向内收敛（Router → Service → Domain → Repo）。

### 9.1 当前遗留的跨层依赖

P3 完成后，以下直接引用仍散落在 `api/routers/pages/` 和 `api/routers/` 中：

| 被引用对象 | 当前位置 | 问题 | P4 替换方案 |
| :--- | :--- | :--- | :--- |
| `app.indexer.Indexer` | `pages/discovery.py`、`pages/site.py`、`pages/setting.py` | 路由层直接触碰基础设施 | 封装为 `IndexerService`，路由只调 Service |
| `app.sites.Sites` / `SiteUserInfo` | `pages/site.py`、`pages/sync.py` | 同上 | 已封装为 `SiteService`，需彻底替换残留调用 |
| `web.backend.user.User` | `pages/base.py`、`pages/discovery.py`、`pages/sync.py`、`pages/setting.py` | 表现层依赖旧的 Flask 用户封装 | 提取 `UserContextService`，通过 `api.deps` 注入 FastAPI 兼容的用户 DTO |
| `web.backend.web_utils.WebUtils` | `pages/site.py`、`pages/sync.py` | 工具类被路由层直接调用 | 将 `get_page_range` 等方法下沉到 `app.utils.pagination` 或对应 Service |
| `config.Config` | 多处 | 全局单例配置 | 引入 `app.services.config_service.ConfigService`，支持注入与 mock |
| `app.message.Message` | `pages/setting.py` | 全局单例 | 封装为 `MessageService` |

### 9.2 任务清单

#### 1. 引入依赖注入容器（DI Container）

不引入重量级框架，使用轻量级手动工厂 + `api.deps` 统一收口：

```python
# api/deps.py（扩展）
from app.services.indexer_service import IndexerService
from app.services.site_service import SiteService
from app.services.config_service import ConfigService

def get_indexer_service() -> IndexerService:
    return IndexerService()

def get_site_service() -> SiteService:
    return SiteService()

def get_config_service() -> ConfigService:
    return ConfigService()
```

路由层统一通过 `Depends` 注入：

```python
# api/routers/pages/discovery.py
@router.get("/search")
def search_page(
    request: Request,
    svc: IndexerService = Depends(get_indexer_service),
    user: UserDTO = Depends(get_current_user_dto),
):
    ...
```

#### 2. 用户上下文统一

- 提取 `app.schemas.user.UserDTO`（含 `id`、`username`、`level`、`menus`、`permissions`）。
- `api.deps.get_current_user_dto` 同时兼容 Session（Flask 迁移期）和 Token（FastAPI 原生）。
- 删除所有 `from web.backend.user import User` 在路由层的引用。

#### 3. 配置服务化

- 新建 `app.services.config_service.ConfigService`，封装对 `config.Config` 的读取。
- 配置变更通过 `ConfigService.update()` 统一收口，避免全局单例被任意修改。
- 单元测试时可直接替换 `ConfigService` 实例，无需 monkey-patch 全局对象。

#### 4. 工具方法下沉

- `WebUtils.get_page_range` → `app.utils.pagination.get_page_range`
- `WebUtils.bytes_to_size` → `app.utils.formatting.bytes_to_size`
- 删除 `web.backend.web_utils` 在路由层的所有 import。

#### 5. 清理遗留 Flask 控制器

- 当所有前端 URL 已切到 `/api/...` 后，逐步删除 `web/controllers/*.py`。
- `web/main.py` 中仅保留尚未迁移的 Webhook（微信、Telegram、Slack 等）和静态文件服务。
- 最终目标：`web/` 目录只保留模板、静态资源和 Webhook 兼容层。

### 9.3 交付标准

- `grep -r "from app.indexer import" api/routers/` 返回空
- `grep -r "from web.backend" api/routers/` 返回空
- `grep -r "from config import Config" api/routers/` 返回空（仅允许在 Service 层使用）
- 全量测试通过：`uv run pytest tests/` 无失败

---

## 10. P5：架构治理 + 长期演进（6~8 周）

**目标**：在分层清晰、依赖内收的基础上，引入事件驱动、可观测性和性能优化，使 Nexus Media 具备企业级可维护性和扩展性。

### 10.1 领域事件与事件总线

当前跨领域调用存在隐式耦合（如下载完成后需要通知媒体库刷新）。P5 引入事件驱动解耦：

```python
# app/domain/events/download_events.py
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class TorrentDownloadedEvent:
    torrent_id: str
    title: str
    downloader: str
    save_path: str
    occurred_at: datetime
```

事件发布与订阅：

```python
# app/services/event_bus.py
class EventBus:
    def subscribe(self, event_type: type, handler: Callable): ...
    def publish(self, event: DomainEvent): ...

# 使用示例
bus = EventBus()
bus.subscribe(TorrentDownloadedEvent, MediaLibraryRefreshHandler())

# 下载完成后发布事件
bus.publish(TorrentDownloadedEvent(torrent_id="...", ...))
```

好处：
- 新增功能（如"下载完成发送通知"）只需新增事件处理器，不修改下载 Service。
- 支持异步事件处理，避免下载流程被阻塞。

### 10.2 可观测性建设

#### 1. 结构化日志（已完成基础，P5 深化）

- 统一使用 `structlog` 或 `loguru`，所有日志输出 JSON 格式。
- 每个请求生成 `trace_id`，在 Service → Repository → 外部调用全链路传递。

```python
# 日志示例
{
  "timestamp": "2026-04-22T10:00:00Z",
  "trace_id": "abc123",
  "level": "INFO",
  "service": "DownloadService",
  "method": "start",
  "torrent_id": "xxx",
  "duration_ms": 45
}
```

#### 2. 指标采集（Prometheus）

- 在 FastAPI 中集成 `prometheus-fastapi-instrumentator`。
- 自定义业务指标：
  - `nastools_downloads_total`（下载总数）
  - `nastools_rss_checks_total`（RSS 检查总数）
  - `nastools_site_errors_total`（站点错误数）

#### 3. 健康检查与探针

- `/health`：FastAPI 自身健康（已有）
- `/health/ready`：依赖就绪检查（数据库、Redis、关键外部站点）
- `/health/live`：存活检查

### 10.3 性能优化

#### 1. 缓存层

- 引入 `app.cache` 模块，支持 Redis / 内存两级缓存。
- 热点数据缓存：
  - 站点列表（TTL 5 分钟）
  - TMDB 详情（TTL 1 小时）
  - 用户菜单（TTL 1 小时）

#### 2. 数据库连接池

- 若 Repository 已 async 化，使用 `asyncpg` + `SQLAlchemy asyncio` 连接池。
- 监控慢查询，对高频查询添加索引或物化视图。

#### 3. 并发控制

- 外部 HTTP 调用统一使用 `httpx.AsyncClient`，限制连接池大小。
- 批量操作（如多站点 RSS 检查）使用 `asyncio.gather` + 信号量控制并发数。

### 10.4 插件系统重构

当前插件直接操作 `app` 全局对象。P5 基于 Service 层重建插件契约：

```python
# app.plugins.contract.py
class PluginInterface(Protocol):
    def register(self, ctx: PluginContext) -> None: ...
    def on_event(self, event: DomainEvent) -> None: ...

class PluginContext:
    """提供给插件的受控上下文"""
    def __init__(self, config: ConfigService, event_bus: EventBus, ...): ...
```

- 插件只能访问 `PluginContext` 中暴露的能力，无法直接触碰数据库或全局单例。
- 插件生命周期由框架统一管理（加载、启用、禁用、卸载）。

### 10.5 API 文档与开发者体验

- 完善 FastAPI 自动生成的 OpenAPI 文档，所有路由都有 `summary`、`description`、`tags`。
- 提供开发者本地启动脚本：`uv run python -m api.main --reload`。
- 编写《API 开发规范》，约束新增接口的 Schema、错误码、分页格式。

### 10.6 交付标准

- 领域事件覆盖核心业务流程（下载完成、RSS 更新、站点签到等）。
- Prometheus 指标可抓取，Grafana 仪表盘可展示。
- 缓存命中率 > 80%（热点数据）。
- 插件系统文档化，提供官方示例插件。
- 全量测试通过 + 压力测试通过（模拟 100 并发 RSS 检查）。

---

## 11. 完整阶段总览

| 阶段 | 目标 | 核心产出 | 预计工期 |
| :--- | :--- | :--- | :--- |
| **P0** | 接口收敛 + 消灭 God Class | 13 个独立 Flask Blueprint Controller | 1~2 周 |
| **P1** | 提取 Service 层 + DTO 化 | `app/services/`、`app/schemas/` | 3~4 周 |
| **P2** | Repository 完整化 + 领域层独立 | `app/domain/`、`app/db/repositories/` | 6~8 周 |
| **P3** | 迁移到 FastAPI | `api/`（FastAPI Router）、前端 URL 切换 | 4~6 周 |
| **P4** | 基础设施现代化 + 依赖清理 | DI 容器、UserDTO、ConfigService、清理 `web/` | 4~6 周 |
| **P5** | 架构治理 + 长期演进 | 事件总线、Prometheus、缓存层、插件契约 | 6~8 周 |

> **总工期估算**：P0~P3 约 14~20 周（已完成），P4~P5 约 10~14 周（规划中）。
> 建议 P4 在 P3 稳定运行至少 2 周后开始，P5 可与其他功能迭代并行推进。
