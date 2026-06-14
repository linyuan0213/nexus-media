# Nexus Media 项目指南

## 项目概述
Nexus Media 自动化工具，用于媒体管理、种子索引和下载编排。
- **后端**: Python 3.11+, FastAPI, SQLAlchemy, Alembic
- **前端**: 独立仓库 [nexus-media-web](https://github.com/linyuan0213/nexus-media-web)，Vue 3 + Vite + Naive UI + Tailwind CSS
- **数据库**: SQLite (默认) 或 MySQL/PostgreSQL，通过 `src/app/db/database_factory.py` 配置
- **配置**: `src/app/core/settings.py` (pydantic-settings) + `config/config.yaml.example` + `.env`
- **任务运行**: `just`（`justfile`），替代 Makefile

## 项目结构（src layout）
```
backend/
├── src/                       # 源码（PEP 517/518 src layout）
│   ├── api/                   # FastAPI 路由层
│   ├── app/                   # 核心业务层
│   ├── log/                   # 日志模块（loguru）
│   ├── version.py             # 版本（从 pyproject.toml 读取）
│   └── initializer.py         # 启动初始化
├── tests/                     # 测试
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   └── conftest.py
├── config/                    # 站点 JSON 定义、配置模板
│   └── config.yaml.example    # 提交到 git 的模板
├── alembic/                   # Alembic 迁移（env.py + versions/）
├── static/                    # 静态文件
├── docker/                    # Docker 构建文件（rootfs/）
├── scripts/                   # 工具脚本 + Alembic 迁移生成
├── justfile                   # 任务运行器
├── run.py                     # 启动入口
└── pyproject.toml
```

## 配置优先级
环境变量 > `.env` > `data/config.yaml`（可选，自动发现）
- `NEXUS_MEDIA_CONFIG` 已降级为可选，未设置时自动查找 `./data/config.yaml`
- 无配置文件时纯 `.env` + 默认值也可运行

## 架构
- **入口**: `run.py` → `src/api/main.py` (FastAPI 应用 + lifespan)
- **初始化**: `src/initializer.py` 初始化调度器、RBAC、RSS 状态；`init_event_handlers()` 在传入 DI EventBus 时只做缓存事件桥接
- **数据库迁移**: 由 Docker entrypoint 或 compose migration 服务执行 `alembic upgrade head`，不再在代码中运行
- **DI**: `src/app/di/registry.py` + `src/app/di/factories.py`（显式工厂注册表，已移除 dependency-injector）；`build_infrastructure()` 创建 EventBus 后显式调用 `register_modules()` + `auto_register()` 注册所有 `@on_event` handler
- **HTTP 客户端**: `HttpClient` / `AsyncHttpClient` 按配置复用底层 `httpx.Client` / `httpx.AsyncClient` 连接池，进程退出时由 `HttpClient.close_all()` / `AsyncHttpClient.close_all()` 统一释放
- **缓存**: `src/app/infrastructure/cache_system/` (Redis + 内存适配器、装饰器、事件总线)
- **插件**: `src/app/plugin_framework/builtin_plugins/` — 内置 + 可安装
- **权限**: `src/app/db/models/rbac.py` 中的自定义 RBAC 系统

## 重要约定
- 注释需要精简。
- **所有 `import`/`from` 必须放在文件顶部**，严禁在函数/方法/类内部导入依赖。如遇循环依赖，必须通过重构 `__init__.py` 延迟导入或调整模块结构来解除，禁止使用函数内部导入规避。
- **所有修改必须通过 ruff 和 pyright 检查**后才能提交。运行命令：`uv run ruff check .` 和 `uv run pyright src/ tests/`。
- 优先编辑现有文件，而不是创建新文件。
- 遵循现有代码风格；项目混合了新旧模式，新代码尽量使用新模式。
- `third_party/`、`src/app/media/doubanapi/`、`src/app/media/tmdbv3api/` 中的第三方代码 — 不要重构。

## 数据库
- 工厂: `src/app/db/database_factory.py`
- 迁移: `alemmic/` 目录（`alembic upgrade head`）
- 添加模型时，需要添加 Alembic 迁移并更新仓库。

## 安全扫描
- `just bandit` — 源码安全扫描
- `just safety` — 依赖漏洞扫描（pip-audit）
- `just security` — 两者

## 测试
- 测试框架: pytest，配置在 `pyproject.toml` 的 `[tool.pytest.ini_options]`
- 全局 fixtures: `tests/conftest.py`（内存数据库、mock 配置）
- 测试配置: `tests/config_test.yaml`
- 运行命令: `uv run pytest tests/ -v`
- 覆盖率: `uv run pytest tests/ -v --cov=src/app --cov=src/api --cov=src/log --cov-report=term-missing`

## 版本
- `pyproject.toml` 为版本唯一来源
- `src/version.py` 从 `pyproject.toml` 动态读取，自动加 `v` 前缀

## Git 工作流

### 分支模型
采用简化 Git Flow：

| 分支 | 用途 | 保护策略 |
|------|------|----------|
| `master` | 稳定发布分支 | 禁止直接推送 |
| `dev` | 日常开发分支 | 建议 PR 合并 |
| `release` | 预发布分支 | 禁止直接推送 |
| `feature/*` | 功能分支（可选） | 无 |

### 提交规范
- 使用 Conventional Commits 格式：`<type>: <中文描述>`
- 常用 type：`feat`、`fix`、`refactor`、`perf`、`test`、`docs`、`chore`

### 前后端协同
- 后端和前端为两个独立 git 仓库，分别提交和发布。
- API 变更时，后端先行提交并确保接口稳定，前端再对接。
