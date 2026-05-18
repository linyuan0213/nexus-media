# Nexus Media 前端框架选型与集成设计文档

> **版本**：v1.0
> **日期**：2026-04-22
> **范围**：前端技术选型、项目结构设计、API 对接方案、迁移策略

---

## 1. 框架选型结论

**推荐方案：Vben Admin v5.6.0（Vue3 + Vite + Ant Design Vue + Pinia）**

### 1.1 候选框架对比

| 维度 | **Vben Admin** ⭐ | vue-pure-admin | SoybeanAdmin |
|------|-------------------|----------------|--------------|
| UI 组件库 | Ant Design Vue 4.x | Element Plus 2.x | Naive UI 2.x |
| GitHub Stars | ~30k（最活跃） | ~18k | ~12k |
| 最新版本 | v5.6.0 | v6.x | v1.x |
| 社区维护 | 非常活跃，迭代快 | 活跃 | 一般 |
| 文档完善度 | 最佳，中文文档齐全 | 良好 | 一般 |
| 权限/路由 | 动态路由 + RBAC 最成熟 | 较完善 | 基础支持 |
| 主题系统 | 深色/浅色/自定义最强 | 良好 | 良好 |
| 多标签页 | 内置完善 | 内置 | 基础 |
| Mock 系统 | 与 FastAPI OpenAPI 配合好 | 有 | 有 |
| TypeScript | 严格，类型安全 | 支持 | 严格 |
| 中后台场景 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

### 1.2 选型理由

1. **FastAPI 生态最匹配**：Vben 的 Mock 系统可与 FastAPI 的 OpenAPI Schema 无缝对接，支持基于 Swagger 文档自动生成 TypeScript 类型。
2. **中后台功能最完整**：Nexus Media 需要大量表格展示、表单配置、卡片布局、权限控制、任务调度面板等场景，Vben 开箱即用。
3. **长期维护成本最低**：30k+ Stars，Ant Design Vue 阿里生态，组件库稳定性经大规模生产验证。
4. **RBAC 对接最顺畅**：现有 [`api/routers/rbac.py`](../api/routers/rbac.py:1) 已实现基于角色的权限控制，Vben 的动态路由 + 菜单权限可直接对接后端 RBAC 接口。
5. **主题定制能力强**：NAS 用户偏好深色模式，Vben 内置完善的主题切换和自定义能力。

---

## 2. 项目结构设计

### 2.1 目录布局

```text
nexus-media/
├── api/                          # FastAPI 后端（现有，保持不变）
│   ├── main.py                   # FastAPI 应用入口
│   ├── routers/                  # API 路由
│   └── deps.py                   # 依赖注入
├── web/                          # Web 相关资源
│   ├── static/                   # 现有静态资源（过渡阶段保留）
│   ├── templates/                # 现有 Jinja2 模板（过渡阶段保留）
│   ├── controllers/              # Flask Controllers（逐步废弃）
│   └── frontend/                 # ⭐ 新建：Vben Admin 前端项目
│       ├── apps/
│       │   └── nexus-media/        # 主应用
│       │       ├── src/
│       │       │   ├── api/      # 后端 API 接口封装
│       │       │   ├── views/    # 页面视图
│       │       │   ├── router/   # 路由配置
│       │       │   ├── store/    # Pinia 状态管理
│       │       │   └── types/    # TypeScript 类型定义
│       │       ├── package.json
│       │       └── vite.config.ts
│       ├── packages/             # 共享包（UI组件、工具函数等）
│       ├── pnpm-workspace.yaml   # Monorepo 工作区配置
│       └── README.md
├── docs/                         # 文档
├── tests/                        # 测试
└── pyproject.toml                # Python 依赖
```

### 2.2 Monorepo 结构说明

Vben Admin v5 采用 pnpm workspace monorepo 结构：

- `apps/nexus-media/` — 主应用，Nexus Media 的业务代码
- `packages/@vben/` — Vben 官方共享包（UI组件、请求封装、权限工具等）
- `packages/@vben-core/` — 核心工具包

---

## 3. API 对接方案

### 3.1 基础配置

FastAPI 后端已配置 CORS：

```python
# api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # 开发阶段允许所有，生产环境限制域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3.2 请求代理配置

开发环境通过 Vite `proxy` 转发 API 请求到 FastAPI：

```typescript
// apps/nexus-media/vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:3000',  // FastAPI 开发服务器地址
      changeOrigin: true,
      // 不需要 rewrite，后端路由本身就是 /api/xxx
    },
    '/static': {
      target: 'http://localhost:3000',
      changeOrigin: true,
    },
  },
}
```

### 3.3 API 模块划分（对齐后端路由）

| 前端 API 模块 | 后端路由前缀 | 说明 |
|-------------|-----------|------|
| `api/system` | `/api/system` | 系统设置、日志、备份 |
| `api/site` | `/api/site` | 站点管理、签到、统计 |
| `api/download` | `/api/download` | 下载器、任务管理 |
| `api/rss` | `/api/rss` | RSS 订阅、历史 |
| `api/sync` | `/api/sync` | 目录同步 |
| `api/brush` | `/api/brush` | 刷流任务 |
| `api/filter` | `/api/filter` | 过滤规则 |
| `api/scheduler` | `/api/scheduler` | 定时任务、调度器 |
| `api/plugin` | `/api/plugin` | 插件管理 |
| `api/userrss` | `/api/userrss` | 自定义 RSS |
| `api/words` | `/api/words` | 识别词、自定义识别 |
| `api/media` | `/api/media` | 媒体库、TMDB 搜索 |
| `api/rbac` | `/api/rbac` | 用户、角色、权限、菜单 |
| `api/pages` | `/api/pages/...` | 页面数据（各模块页面配置） |

### 3.4 认证方案

沿用后端现有 Session 认证：

1. 用户通过 `/api/rbac/login` 登录
2. 后端返回 Session Cookie
3. 前端请求携带 `credentials: 'include'`
4. 后端 `get_current_user` 依赖从 Session 提取用户信息

```typescript
// 请求封装示例
import { requestClient } from '@vben/request';

export async function login(data: LoginParams) {
  return requestClient.post('/api/rbac/login', data, {
    withCredentials: true,
  });
}
```

---

## 4. 路由与权限映射

### 4.1 前端路由结构（对齐现有功能模块）

```text
/
├── /login                    # 登录页
├── /dashboard                # 仪表盘（总览）
├── /media                    # 媒体库
│   ├── /search               # 媒体搜索
│   ├── /library              # 媒体库管理
│   └── /discovery            # 发现页
├── /download                 # 下载管理
│   ├── /downloading          # 正在下载
│   ├── /history              # 下载历史
│   └── /downloader           # 下载器设置
├── /site                     # 站点管理
│   ├── /list                 # 站点列表
│   ├── /statistics           # 站点统计
│   └── /signin               # 签到管理
├── /rss                      # RSS 订阅
│   ├── /movie                # 电影订阅
│   ├── /tv                   # 剧集订阅
│   ├── /user                 # 自定义 RSS
│   ├── /parser               # RSS 解析器
│   ├── /calendar             # 订阅日历
│   └── /history              # 订阅历史
├── /sync                     # 目录同步
├── /brush                    # 刷流任务
├── /filter                   # 过滤规则
│   └── /rule                 # 规则配置
├── /words                    # 识别词管理
├── /scheduler                # 定时任务
│   └── /jobs                 # 任务列表
├── /plugin                   # 插件中心
│   ├── /market               # 插件市场
│   └── /installed            # 已安装插件
├── /service                  # 服务管理
│   ├── /indexer              # 索引器
│   ├── /mediaserver          # 媒体服务器
│   └── /notification         # 消息通知
├── /system                   # 系统设置
│   ├── /basic                # 基础设置
│   ├── /security             # 安全设置
│   ├── /backup               # 备份恢复
│   ├── /logs                 # 系统日志
│   └── /users                # 用户管理
└── /rename                   # 整理重命名
    ├── /history              # 识别历史
    ├── /mediafile            # 文件管理
    └── /unidentification     # 未识别列表
```

### 4.2 权限码映射（对接后端 RBAC）

前端路由权限码与后端 `permission_code` 字段保持一致，采用 `模块:操作` 格式：

| 权限码 | 说明 | 对应后端接口 |
|-------|------|-----------|
| `media:view` | 查看媒体库 | `/api/media/*` GET |
| `media:search` | 媒体搜索 | `/api/media/search` |
| `download:manage` | 管理下载任务 | `/api/download/*` POST/PUT/DELETE |
| `site:manage` | 管理站点 | `/api/site/*` POST/PUT/DELETE |
| `rss:manage` | 管理订阅 | `/api/rss/*` POST/PUT/DELETE |
| `system:admin` | 系统管理员 | `/api/system/*` |
| `rbac:admin` | 权限管理 | `/api/rbac/*` |

### 4.3 动态菜单对接

后端 `api/rbac.py` 已提供菜单管理接口：

- `GET /api/rbac/menus` — 获取当前用户可见菜单
- 返回字段包含 `menu_name`, `path`, `icon`, `component`, `permission_code`, `children`

前端通过 `getUserMenusApi()` 获取菜单树，动态生成路由和侧边栏。

---

## 5. 页面组件映射（旧模板 → 新前端）

### 5.1 核心页面迁移对照

| 旧模板（Jinja2） | 新前端页面 | 主要组件 |
|----------------|----------|---------|
| `templates/index.html` | `/dashboard` | StatisticCard, QuickActions, RecentActivity |
| `templates/login.html` | `/login` | LoginForm（Vben内置） |
| `templates/search.html` | `/media/search` | SearchInput, MediaCardGrid, FilterPanel |
| `templates/download/downloading.html` | `/download/downloading` | TaskTable, ProgressBar |
| `templates/setting/basic.html` | `/system/basic` | ConfigForm, SaveButton |
| `templates/setting/downloader.html` | `/download/downloader` | DownloaderConfigForm |
| `templates/rss/movie_rss.html` | `/rss/movie` | RSSTable, AddModal |
| `templates/rss/tv_rss.html` | `/rss/tv` | RSSTable, SeasonSelector |
| `templates/scheduler.html` | `/scheduler/jobs` | CronJobTable, JobLogDrawer |
| `templates/service.html` | `/service` | ServiceCardGrid |
| `templates/navigation.html` | 全局 Layout | SidebarMenu, Breadcrumb, TabBar |
| `templates/rename/history.html` | `/rename/history` | DataTable, FilterBar |

### 5.2 复用现有 Web Components

现有 Lit-based Web Components（`web/static/components/`）可在过渡阶段通过自定义元素方式嵌入新前端：

```vue
<!-- 在 Vben 页面中嵌入现有组件 -->
<template>
  <div>
    <CardNormal :data="mediaData" />
    <CustomChips :items="tags" />
  </div>
</template>

<script setup>
// 注册现有自定义元素
import '/static/components/card/normal/index.js';
import '/static/components/custom/chips/index.js';
</script>
```

---

## 6. 构建与部署方案

### 6.1 开发模式

```bash
# 1. 启动 FastAPI 后端
cd /home/linyuan/python/nexus-media
export NEXUS_MEDIA_CONFIG=/home/linyuan/python/config/config.yaml
uv run python run_fastapi.py

# 2. 启动前端开发服务器（另一个终端）
cd web/frontend/apps/nexus-media
pnpm dev          # 默认端口 5555，代理 /api 到 3000
```

### 6.2 生产构建

```bash
cd web/frontend
pnpm build        # 构建产物输出到 apps/nexus-media/dist/
```

构建产物（`dist/` 目录）通过 FastAPI `StaticFiles` 挂载为 SPA：

```python
# api/main.py（扩展）
from fastapi.responses import FileResponse

# 挂载前端构建产物
app.mount("/app", StaticFiles(directory="web/frontend/apps/nexus-media/dist", html=True), name="frontend")

# 兜底路由：所有非 API 请求返回 index.html（SPA 路由）
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    return FileResponse("web/frontend/apps/nexus-media/dist/index.html")
```

### 6.3 与现有 Flask 共存策略（绞杀式迁移）

```
阶段 1（当前）：
  - Flask 服务 Jinja2 页面（/page/...）
  - FastAPI 服务 API（/api/...）
  - 前端开发服务器独立运行（:5555）

阶段 2（部分页面迁移）：
  - 新前端页面通过 /app/ 路径访问
  - 旧页面逐步重定向到新前端
  - Flask 仅保留未迁移页面

阶段 3（完全迁移）：
  - Flask 仅保留遗留 API 兼容层
  - 所有页面由 Vben Admin 提供
  - FastAPI 作为唯一服务端框架
```

---

## 7. 状态管理设计

### 7.1 Pinia Store 划分

```typescript
// store/modules/
├── user.ts              # 用户信息、登录状态、权限
├── app.ts               # 应用配置（主题、语言、布局）
├── media.ts             # 媒体搜索、媒体库数据
├── download.ts          # 下载任务、下载器状态
├── site.ts              # 站点列表、站点统计
├── rss.ts               # RSS 订阅数据
├── scheduler.ts         # 定时任务状态
├── plugin.ts            # 插件列表、插件配置
├── notification.ts      # 全局消息通知
└── tabView.ts           # 多标签页状态（Vben内置）
```

### 7.2 WebSocket 实时推送

Nexus Media 现有 WebSocket（`websockets` 库）用于推送下载进度、任务状态等。前端通过 Vben 的 `useWebSocket` 封装对接：

```typescript
// 实时下载进度
const { data, send } = useWebSocket('ws://localhost:3000/ws/download');

watch(data, (msg) => {
  if (msg.type === 'download_progress') {
    downloadStore.updateProgress(msg.hash, msg.progress);
  }
});
```

---

## 8. 测试策略

### 8.1 前端测试

- **单元测试**：Vitest + Vue Test Utils，测试 Composables 和纯函数
- **E2E 测试**：Playwright，覆盖核心用户流程（登录 → 搜索 → 下载）
- **构建测试**：CI 中执行 `pnpm build`，确保无构建错误

### 8.2 前后端集成测试

```python
# tests/frontend/test_build.py
import subprocess
import pytest


def test_frontend_build():
    """确保前端项目可以成功构建"""
    result = subprocess.run(
        ["pnpm", "build"],
        cwd="web/frontend",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"前端构建失败: {result.stderr}"
```

---

## 9. 实施计划

| 阶段 | 任务 | 预计工期 |
|-----|------|---------|
| P0 | 初始化 Vben Admin 项目、配置代理、对接登录 | 2 天 |
| P1 | 实现 Dashboard、媒体搜索、下载管理核心页面 | 1 周 |
| P2 | 实现站点管理、RSS 订阅、系统设置页面 | 1 周 |
| P3 | 实现刷流、过滤规则、插件中心页面 | 3 天 |
| P4 | 实现权限管理、用户管理页面 | 2 天 |
| P5 | 迁移剩余页面、WebSocket 对接、E2E 测试 | 3 天 |
| P6 | 性能优化、主题定制、PWA 支持 | 2 天 |

---

## 10. 风险与应对

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| Vben 版本升级 Breaking Change | 中 | 锁定版本到 v5.6.0，升级前充分测试 |
| 旧 Web Components 兼容性 | 低 | 过渡阶段通过自定义元素嵌入，逐步重写为 Vue 组件 |
| FastAPI Session 跨域问题 | 中 | 确保 CORS `allow_credentials=True` 且前端 `withCredentials: true` |
| 构建产物体积过大 | 中 | 启用代码分割、按需加载、Gzip/Brotli 压缩 |
| 团队学习成本 | 低 | Ant Design Vue 文档完善，组件使用门槛低 |

---

## 附录：关键技术栈版本

| 技术 | 版本 | 说明 |
|-----|------|------|
| Vue | 3.4.x | 组合式 API |
| Vite | 5.x | 构建工具 |
| Ant Design Vue | 4.x | UI 组件库 |
| Pinia | 2.x | 状态管理 |
| Vue Router | 4.x | 路由管理 |
| TypeScript | 5.x | 类型系统 |
| Tailwind CSS | 3.x | 原子化 CSS |
| pnpm | 10.x | 包管理器 |
