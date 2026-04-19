# NAS-Tools 现代化重构计划

> **版本**：v1.0  
> **日期**：2026-04-16  
> **范围**：Web 层（`web/`）、应用层（`app/services/`）、领域层（`app/domain/`）、基础设施层（`app/db/repositories/`）

---

## 1. 背景与目标

### 1.1 现状问题

NAS-Tools 在早期采用典型的 **Flask + Jinja2 后端渲染** 模式快速迭代，导致以下技术债务：

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

| 维度 | 现代化标准 | NAS-Tools 现状 | 最终目标 (P3) |
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

4. **认证统一迁移**
   - Session 认证：通过 `SessionMiddleware` + `request.session` 兼容现有登录态。
   - Token 认证：使用 FastAPI 原生 `OAuth2PasswordBearer`，APIv1 Token 逻辑平移。

5. **异步化基础设施**
   - 外部 HTTP 客户端（TMDB、PT 站点）逐步替换为 `httpx.AsyncClient`。
   - Repository 可选引入 `sqlalchemy.ext.asyncio`，若风险过高可先保持 sync 在线程池中运行。

6. **绞杀式切换**
   - 按领域逐个迁移：先 `system` → `site` → `download` → `rss`。
   - 每迁移一个领域，前端对应 `ajax_post` URL 从 `/api/web/...` 切到 `/api/...`，回滚策略为改 Nginx 配置即可。

#### 交付物结构
```text
nas-tools/
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

本次重构的核心是先**在现有 Flask 体系内建立清晰的分层边界**（P0~P2），让 NAS-Tools 从"快速堆功能"演进为"可持续维护"的项目。P0 完成后，项目已经具备现代化雏形；P1 和 P2 则是按领域逐步打磨的过程。

当 Service、Schema、Domain、Repository 四层边界清晰后，**P3 的 FastAPI 迁移将只是表现层的"薄壳替换"**，而非伤筋动骨的全量重写。建议始终采用**小步快跑、领域试点、测试先行、绞杀切换**的节奏推进，在保障功能稳定的前提下完成技术栈现代化。
