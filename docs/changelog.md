# 版本历史

## v4.1.3 (2026-06-18)

### 下载事件 SSE 推送
- `DownloadStartedPayload` 增加 `download_id` 字段
- `DOWNLOAD_STARTED` 事件从流水线入口移至 `_stage_add` 成功后发布，避免 fetch/resolve 失败时误报
- 新增 `download_event_queue` 模块级 `queue.Queue` 作为事件通道
- handler 推送 `download.started` / `download.failed` / `download.completed` 事件到队列
- 新增 `GET /api/download/events` SSE 端点，权限 `download:view`

### 站点资源内置索引器
- `/api/download/indexers` 始终返回内置索引器站点列表，不受索引器切换影响
- `IndexerService` 新增 `get_builtin_user_indexers()` 方法

### 修复 MySQL NOT NULL 兼容性
- `CONFIG_SITE.EXCLUDE`、`SIZE` 添加 ORM 默认值，修复新增站点 500
- `SITE_USER_INFO_STATS.JOIN_AT`、`EXT_INFO` 等列添加 ORM 默认值，修复统计更新 500
- `site_service.update_site` 异常分支添加 `log.error` 和 `msg`，不再吞掉错误信息
- `site_repository.update_site_user_statistics` 中 `JOIN_AT=None` 时写入空字符串

## v4.1.2 (2026-06-16)

### 刷流修复
- 缓存线程安全：`_torrents_cache` 加 `threading.Lock` 防止并发下载重复种子
- 删种前用 `get_torrents` 确认种子离开下载器，避免边缘状态误删记录导致孤儿
- 删种失败不再标记为已删除
- 新任务不触发全量 `start_service()`，缓存在 `delete_brushtask` 未命中时回退查 DB

### 订阅修复
- RSS 自动订阅事件处理器已注册到 DI，功能恢复可用
- 删除订阅时同步清理 `SubscribeTorrents` 种子记录，重新订阅可正常下载
- `truncate_rss_episodes` 只清除非活跃订阅的剧集进度
- TOCTOU 并发防重复插入订阅
- 状态字符串统一替换为 `SubscribeState` 枚举
- 状态设为 SEARCHING 移到协调锁之后，消除异常窗口

### 测试修复
- 测试配置改用临时文件 + SQLite，不再依赖外部 MySQL 服务器

### 数据库兼容性
- 14 处 String=Integer 类型比较加 cast 适配 PostgreSQL
- MySQL ENCLOSURE 索引加前缀长度，避免 VARCHAR(8192) 超限
- `ConfigRepository.execute` 适配 SQLAlchemy 2.0 `text()`
- `drop_table` SQL 注入修复
- SQL 适配器 MySQL 双引号转反引号

### 其他修复
- `get_secret_key` 保存后 `reload` 确保同次运行不生成多个密钥
- `_brush_tasks` 先停旧 job 再 pop，消除竞态窗口
- auth router 清除重复标签，prefix 统一到 `include_router`
- 清理绞杀式迁移相关注释
- 后端 nginx 加兜底路由代理 `/docs` 等非 API 路径

### 依赖
- `python-jose` 替换为 `PyJWT[crypto]`，消除 `ecdsa` 安全告警

## v4.1.1 (2026-06-16)

### 部署修复
- **ConfigReloader 重构**：改为工厂模式重建实例，而非 reset()，tmdb_client 热重载时清除 Redis 缓存
- **settings.save 合并**：修复保存时只保留 database 节点导致其他配置（TMDB key 等）丢失
- **配置保存触发重载**：/config/update 自动调用 ConfigReloader.reload()
- **NOGROUP 根治**：RedisMessageQueue dispatch 循环幂等创建消费组
- **static 目录持久化**：跟随 NEXUS_MEDIA_DATA 落到 /data/static
- **过滤规则初始化**：首次启动从 init_filter.sql 导入默认规则，INSERT OR IGNORE 防覆盖
- **TMDB 异常降级**：get_tmdb_new_movies/tvs 捕获异常返回 []，不抛 500

## v4.1.0 (2026-06-15)

### 部署优化
- **Docker Compose 三模式部署**：支持基础模式（前端+后端+Redis+MySQL/PostgreSQL）、完整模式（+OCR+Chrome）、仅前后端模式（SQLite）
- **默认基础 MySQL 模式**：执行 `docker compose up -d` 即可启动
- **统一数据库环境变量**：Docker 与代码统一使用 `DATABASE__*` 格式读取配置
- **Redis 默认命令启动**：移除对 `./config/redis.conf` 文件挂载的依赖
- 数据库升级到 MySQL 8.4 / PostgreSQL 17-alpine

### 性能优化
- **数据库查询性能**: 消除 `site_repository` / `transfer_repository` N+1 查询；为 `SUBSCRIBE_MOVIES` / `SUBSCRIBE_TVS` / `CONFIG_USER_RSS` / `SITE_BRUSH_TORRENTS` / `TRANSFER_HISTORY` / `TRANSFER_UNKNOWN` 添加索引；`subscribe_repository` 用单次 `first()` 替代 `.all()` + 循环
- **HTTP 客户端连接池复用**: `HttpClient` / `AsyncHttpClient` 按配置复用底层 `httpx.Client` / `httpx.AsyncClient`，相同代理/头/超时/认证/SSL 配置共享连接池
- **缓存系统**: `RedisStore.hgetall` 改为单次 `hgetall`；`MemoryCacheAdapter` 仅在存在监听器时触发 `CacheEvent`，避免高频空转
- **消息队列**: `MessageQueueFactory` 单例实现线程安全，避免重复创建队列
- **下载完成监控**: `DownloadMonitor` 改为增量检查，后续轮询只拉取新增任务；qBittorrent 使用 `sync/maindata` 增量接口获取 completed 任务，减少数据传输与 per-torrent API 调用
- **图片代理**: 下载逻辑全面异步化，使用 `AsyncHttpClient` 连接池与 `asyncio.gather` 并发下载，替代 `ThreadPoolExecutor`
- **JSON 序列化**: 高频路径统一使用 `JsonUtils`（`orjson` 为主，stdlib 为 fallback）

### 问题修复
- **EventBus 注册**: 修复 DI 容器创建的 `EventBus` 与 `@on_event` handler 注册脱节的问题；`SystemLifecycleService` 现在从 DI 接收真实 `EventBus`
- **认证**: 移除 `SessionMiddleware` 与 session 认证兼容层，API 统一使用 JWT/Token 认证
- **消息通知图片**: 添加诊断日志定位图片丢失问题；修复 `_get_script_path` 依赖注入错误

### 依赖与质量
- 升级 `redis` / `cryptography` / `pydantic-ai` / `granian` / `python-multipart` / `openai` / `google-genai` / `boto3` / `beautifulsoup4` / `qbittorrent-api` / `ruff` 等依赖
- 引入 `orjson` / `uvloop`；启用 `httpx` HTTP/2
- 新增 Alembic 迁移 `e9d9eaed8d5c` 补充查询索引
- 安全扫描: `just bandit` / `just safety` 均通过
- 测试: 1195 个测试通过，覆盖率 `36%`；新增事件系统异常隔离与异步投递测试

## v4.0.0 (2026-06-09)

**4.0.0 是 Nas-Tools 的全新重构版本，涵盖后端架构、前端框架、部署运行和代码质量的全面升级。**

### 架构重构
- 项目重命名为 **Nexus Media**，全面替换旧品牌标识
- 项目结构标准化为 `src/` layout，统一 `get_project_root()` 消除硬编码路径
- 架构分层重构：消除 `helper/` 层、解除循环依赖、基础设施统一归位
- 全面重构 DI 容器，引入 `ConfigReloader` 集中热重载，消灭 `NEXUS_MEDIA_CONFIG` 硬性依赖
- 统一 Repository 适配层，移除 `MediaDb` 直接数据库操作，拆分 `engine/session/transaction` 模块
- 拆分超大服务文件：`filetransfer_service.py` / `message.py` / `scheduler_core.py` / `rss_service.py`
- 消息通知、下载器、索引器、媒体服务器模块重构为插件化扩展架构
- 缓存事件系统整合到 EventBus，移除旧 `task_queue/reliable_message_queue`
- 移除 10+ 个类的 `SingletonMeta`（`Rss` / `IyuuHelper` / `CookiecloudHelper` / `IndexerHelper` / 豆瓣相关类等）

### 新增功能
- 自动签到插件重构为**声明式配置架构**：删除 21 个旧站点硬编码实现，支持“自定义 handler > 声明式配置 > 通用匹配”三层分发
- 站点模块迁移到 **SiteCache / SiteResolver / SiteFaviconService** 领域架构，写操作后缓存自动刷新
- 新增 **分布式锁** 实现，覆盖 RSS 下载、插件安装/卸载、站点刷新、订阅搜索、删种、媒体库同步、转移等场景
- 引入 `tenacity` 替换手写重试，实现 API **速率限制器**
- 图片代理与缓存优化，支持 TMDB / 豆瓣 / Bangumi / 媒体库内网图片
- HTTP 客户端重构：中间件集成、配置修复、异步线程安全
- 日志支持 **JSON 结构化输出**，兼容 ELK；gunicorn access log 每日轮转 + 自动清理
- 服务器由 uvicorn/gunicorn 迁移至 **Granian**，统一 `run.py` 入口
- 新增 ADR-007 ~ ADR-013 架构决策记录

### 前端升级
- 前端框架升级至 **vben v5.7.0**（应用版本同步至 **4.0.0**）
- vue-router 生产环境改为 **history** 模式
- 前端目录 `views/rss/` 统一迁移为 `views/subscription/`，与后端路由对齐
- 前端 Nginx 增加 `/api/`、`/img`、`/docs`、`/openapi.json`、`/ws` 反向代理
- 修复设置按钮点击无反应、头像更新不生效、153 处 TypeScript 类型错误

### 部署与运行
- Docker 镜像升级至 **`python:3.14-slim-trixie`**，弃用 Alpine
- nginx 内部端口改为 **8080**，healthcheck 检查 nginx 而非直连 Granian
- docker-compose 增加独立 **migration** 服务，backend 设 `SKIP_MIGRATION=true`，避免 alembic 并发冲突
- 修复 SQLite 下历史迁移脚本的 `no such table`、`ALTER CONSTRAINT` 等兼容性问题
- 新增 `.dockerignore` 和运行时目录排除，缩减镜像体积
- 修复 nginx `merge_slashes` 导致 `/img` 代理 URL 双斜杠丢失

### 配置与连接
- 迁移配置到 **pydantic-settings**，建立分层异常体系，完善 OpenAPI 文档
- 新增 `RedisConfig` 配置模型，支持环境变量 `REDIS__HOST` / `REDIS__PORT` / `REDIS__PASSWORD` / `REDIS__DB`
- 修复 `settings.py` 中数值配置字段类型（`str` → `int`）导致的 pydantic 校验错误
- 新增 `.env.example` 环境变量模板，重写以对齐 pydantic-settings 字段

### 代码质量
- 新增 CI 质量门禁、pre-commit hooks、justfile 任务运行器
- 全部非测试文件完成**空安全加固**，消除 111 处 null access
- 全部 `reportArgumentType` 清零，227 处类型窄化
- 95 处 `reportIncompatibleMethodOverride` 基类/子类签名对齐
- 重构测试体系，删除不可用旧测试，新建 41 个可运行测试
- 使用 `just` 替代 Makefile，统一 `uv run` 工作流

## v3.7.0 (2025-04-01)

### 新增功能
- 支持迅雷下载器
- 支持Rousi站点（API v1接口）
- 新增自动重启插件
- 新增消息模板
- 搜索结果支持分页浏览（输入 n/p 翻页）
- 支持直接从搜索结果中选择下载

### 功能优化
- 优化数据库性能（使用连接池、WAL模式）
- 优化HTTP工具类（添加连接池和重试策略）
- 优化自动签到插件（跳过BT站点）
- 优化馒头站点仿真登录
- 优化Web界面交互体验
- 添加消息模板配置支持

### 问题修复
- 修复Aria2状态显示拼写错误
- 修复下载器返回值格式问题
- 修复authorization请求头处理问题

## v3.6.9 (2025-12-01)

### 新增功能
- 支持馒头仿真登录
- 支持自由农场签到
- 刷流支持下载付费种子

### 功能优化
- 签到流程优化
- 增加仿真签到延时
- 优化搜索速度
- 重启时重置订阅状态

### 问题修复
- 修复微信插件初始化问题
- 修复观众做种数据
- 修复飞牛图片显示问题
- 修复猫站签到
- 修复chrome服务找不到一直报错
- 修复transmission状态显示
- 修复http工具类
- 修复tags没有配置时无法添加任务

## v3.6.8 (2025-08-22)

### 新增功能
- 支持飞牛媒体服务器

### 功能优化
- 憨憨支持H&R
- 优化调度

### 问题修复
- 修复下载器标签排序问题
- cf优选插件下载路径错误
- 订阅下载重复
- 黑名单条目无法删除

## v3.6.7 (2025-06-15)

### 新增功能
- 新增PTGTK站点支持
- Server酱支持TAG和图片
- 增加TMDB黑名单功能

### 功能优化
- 优化索引器搜索速度
- TMDB缓存优化
- 站点维护增加图标LOGO

### 问题修复
- 修复订阅搜索暂停问题
- 修复HDSky生成RSS失败

## v3.6.6 (2025-05-20)

### 新增功能
- 新增RSS自动生成插件
- 自动备份插件支持WebDAV和Samba
- 支持唐门、雨、财神等新站点

### 功能优化
- Emby媒体库同步插件支持原生webhook
- 企业微信插件支持二维码扫码登录

## v3.6.5 (2025-04-10)

### 问题修复
- 修复馒头模拟登录失效
- 修复观众站点资源访问失败
- 修复Prowlarr下载失败

## v3.6.4 (2025-03-25)

### 功能优化
- 支持OpenAI自定义模型
- 支持HHCLUB备用域名

### 问题修复
- 修复天空种子列表获取问题
- 修复冰淇淋副标题显示问题

## 历史版本

完整版本历史请查看[GitHub发布页面](https://github.com/linyuan0213/nexus-media/releases)

> 注意：建议始终使用最新版本以获得最佳体验和安全更新
