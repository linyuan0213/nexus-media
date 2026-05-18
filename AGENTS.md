# Nexus Media 项目指南

## 项目概述
Nexus Media 自动化工具，用于媒体管理、种子索引和下载编排。
- **后端**: Python 3.x, FastAPI, SQLAlchemy, Alembic
- **前端**: Vue 3 + TypeScript + Vite + Naive UI + Tailwind CSS
- **数据库**: SQLite (默认) 或 PostgreSQL，通过 `database_factory.py` 配置
- **配置**: `config.py` (旧版单例) + `app/conf/` (新配置模块) + `config/config.yaml`

## 架构
- **后端入口**: `run.py` 或 `start-prod.sh` → `api/main.py` (FastAPI 应用)
- **前端**: 独立仓库 [nas-tools-web](https://github.com/linyuan0213/nexus-media-web)，Vue 3 + Vite + Naive UI
- **启动**: `initializer.py` 初始化数据库、调度器和服务
- **单例模式**: 几乎所有组件都使用 `app/utils/commons.py` 中的 `SingletonMeta`
- **缓存**: 自定义框架在 `app/utils/cache_system/` (Redis + 内存适配器、装饰器、事件总线)
- **插件**: `app/plugins/` — 内置 + 可安装
- **权限**: `app/db/models/rbac.py` 中的自定义 RBAC 系统
- **分层**: `app/domain/`, `app/schemas/`, `app/db/models/`, `app/db/repositories/`

## 重要约定
- 除非要求，否则不要添加注释。
- **所有 `import`/`from` 必须放在文件顶部**，严禁在函数/方法/类内部导入依赖。如遇循环依赖，必须通过重构 `__init__.py` 延迟导入或调整模块结构来解除，禁止使用函数内部导入规避。
- **所有修改必须通过 ruff 和 pyright 检查**后才能提交。运行命令：`uv run ruff check <文件>` 和 `uv run pyright <文件>`。
- 优先编辑现有文件，而不是创建新文件。
- 遵循现有代码风格；项目混合了新旧模式，新代码尽量使用新模式。
- `third_party/`、`app/media/doubanapi/`、`app/media/tmdbv3api/` 中的第三方代码 — 不要重构。

## 数据库
- 工厂: `app/db/database_factory.py`
- 迁移: `app/db/migrate.py` (Alembic 包装器)
- 添加模型时，需要添加 Alembic 迁移并更新仓库。

## 前端 (web/frontend/apps/nas-tools/)
- 技术: Vue 3 + Vite + Naive UI + Tailwind CSS + `@vben/plugins/echarts`
- 开发代理: `http://127.0.0.1:3000` → `http://127.0.0.1:3001`
- **颜色规范**: 必须使用 Vben Admin 主题 CSS 变量，如 `hsl(var(--card))`，**禁止**硬编码十六进制/RGB/Tailwind 颜色。
- **图标规范**: 使用 `@vben/icons` 的 `IconifyIcon` 组件，前缀统一为 `lucide:`。
- **移动端**: 新页面必须考虑移动端适配，使用响应式 Tailwind 类。

## 测试
- 测试文件在 `tests/`，但没有正式配置 (`pytest.ini`, `tox.ini`)。
- 文件: `tests/run.py`, `tests/test_rbac.py`, `tests/test_metainfo.py` 等。
- 测试配置在 ../config/config.yaml

## Docker
- 提供 `Dockerfile` 和 `docker-compose.yml`。
- CI 通过 `.github/workflows/build.yml` 构建并推送到 GHCR。

## 版本
- `app/version.py` 导出 `APP_VERSION`。

## Git 工作流

### 分支模型
采用简化 Git Flow，每个仓库（backend / frontend）独立管理：

| 分支 | 用途 | 保护策略 |
|------|------|----------|
| `master` | 稳定发布分支，仅接收 release 合并 | 禁止直接推送 |
| `dev` | 日常开发分支，所有功能提交至此 | 建议 PR 合并 |
| `release` | 预发布分支，从 dev 切出，仅做 bug 修复 | 禁止直接推送 |
| `feature/*` | 功能分支（可选），从 dev 切出 | 无 |

### 提交流程
1. **日常开发**：在 `dev` 分支直接提交或从 `dev` 切出 `feature/*` 分支开发，完成后合并回 `dev`。
2. **发布准备**：从 `dev` 切出 `release` 分支，进行最终测试和 bug 修复，禁止引入新功能。
3. **正式发布**：`release` 分支合并到 `master` 并打 tag，同时合并回 `dev` 保持同步。
4. **热修复**：从 `master` 切出 `hotfix/*`，修复后合并到 `master` 和 `dev`。

### 提交规范
- 使用 Conventional Commits 格式：`<type>: <中文描述>`
- 常用 type：`feat`、`fix`、`refactor`、`perf`、`test`、`docs`、`chore`
- 示例：`feat: 添加 SMB 存储后端支持`、`fix: 修复跨后端移动文件时的权限问题`

### 前后端协同
- 后端 (`backend/`) 和前端 (`frontend/`) 为两个独立 git 仓库，分别提交和发布。
- API 变更时，后端先行提交并确保接口稳定，前端再对接。
