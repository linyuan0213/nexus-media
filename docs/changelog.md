# 版本历史

## v4.1.11 (2026-06-30)

### 新增
- 统一索引器站点管理：引入 `INDEXER_SITE_CONFIG` 表，内置索引器按站点级 `enabled` 过滤，支持 `BuiltinIndexerEnabled` 总开关
- 启动时自动创建公开（BT）内置站点（0Magnet / 1377x / ACG.RIP / 动漫花园 / MiKan / Nyaa），优先级 100~105
- `INDEXER_SITE_CONFIG` 新增 `DEFAULT_SETTINGS` 列（JSON），预留 BT 站点默认搜索设置
- 新增 `IndexerSiteConfigRepository`、`IndexerSiteConfigRepositoryAdapter`、`IndexerSiteConfigEntity` 等基础设施
- 站点维护页新增搜索启用开关（集成到编辑弹窗功能开关），BT 站点隐藏刷流/统计/解析开关
- 卡片底部标签栏展示所有已启用功能（含搜索/字幕/标签）

### 修复
- 搜索入库 299→74 丢失：改为 dialect 无关批量 UPSERT + session 清理，对齐 `(PAGEURL, SITE, SEARCH_SESSION_ID)` 唯一索引
- `USER_LEVEL` NULL 导致 `IntegrityError (1048)`：默认化为空字符串
- 搜索事件 `**SearchStartPayload` 解包报错：添加 `isinstance` 检查
- 自动创建 BT 站点 `signurl` 双重 `https://`：判断 domain 是否已含协议

### 清理
- 移除 `show_more_sites`（实验室→展示更多站点）后端和前端所有相关代码
- 索引器页面移除内置站点多选框，改为单一总开关
- 移除前端"默认搜索索引器"选择器
- `builtin.py` 清理未使用的 `settings`/`IndexerConf` import，补上漏掉的 `DownloadRepository`

### 前端
- 站点卡片 BT/PT 标签按引擎定义 `site_public` 显示，不随 cookie 变化

### 数据库迁移
- `c4d5e6f7a8b9`: 新增 `INDEXER_SITE_CONFIG.DOWNLOAD_SETTING` 列
- `ee2445e35880`: 新增 `INDEXER_SITE_CONFIG.DEFAULT_SETTINGS` 列，从 `UserIndexerSites` 迁移历史数据

### 新增测试
- `test_search_repository.py`: 搜索入库回归测试（299 条全量插入、去重、session 替换）
- `test_indexer_site_config_repository.py`: 索引器站点配置仓储测试
- `test_site_service_get_sites_merge.py`: 站点服务合并逻辑测试

## v4.1.10 (2026-06-29)

### 构建
- Dockerfile 支持 `UV_INDEX_URL` 构建参数，便于构建时自定义 PyPI 镜像源
- 修复 builder 阶段 `uv sync --no-install-project` 导致项目包未安装的问题

### 前端
- 重新设计我的媒体库页面，统一卡片、存储与活动列表视觉风格
- 重构基础设置页面信息架构并改为标签页布局，优化表单层级
- 统一媒体详情页视觉风格，拆分 HeroSection/CastList/FactPanel 等组件
- 优化站点列表卡片视觉设计与操作按钮可访问性
- 重构站点资源卡片与列表：精简海报占位、统一标签语义色、新增 Dolby/HDR 标签类型
- 重构站点统计图表为独立组件，对齐 dashboard/home 实现，修复 tooltip 闪烁与 StatTable 数据引用导致的重绘
- 刷流任务页面重构：改用行内开关与更多操作下拉，移除冗余“已停用”状态选项，调整规则卡片视觉
- 站点编辑弹窗为 API Key / Bearer Token 输入关闭浏览器自动填充
- 全局通知默认时长恢复组件默认，避免通知过早消失
- 资源标签使用更鲜明的语义色变量

### 数据库迁移
- 无需迁移

## v4.1.9 (2026-06-26)

### 修复
- `brushtask_interval` 字段类型错误：API 模型定义为 `int`，前端传 cron 表达式字符串 `"*/30 * * * *"` 导致 422 解析失败，改为 `int | str` + 双格式校验（≥5 分钟 / 5 位 cron）
- 错误日志不到 SSE：`LOG_BUFFER` 容量仅 200 条，启动和运行时高频日志将 error 挤出队列，增大到 2000

### 新增
- KamePT 站点配置：支持 NexusPHP HTML 模式的 KamePT（CosAV/音声/游戏 CG）

### 数据库迁移
- 无需迁移

## v4.1.8 (2026-06-24)

### 修复
- 转移事件处理器 TypeError：`DownloadCompletedPayload(**event.payload)` 对 dataclass 实例用 `**` 解包崩溃，事件总线静默吞异常导致下载完成→转移链路从未触发
- 下载监控多工厂实例缓存不同步：`DownloadCore`/`DownloaderCore`/`DownloadMonitor` 各持有独立 `DownloadClientFactory` 实例，CRUD 后只刷新前两个，`DownloadMonitor` 工厂永不过期
- 下载器 `download_dir` 不生效：`DOWNLOAD_DIR` DB 列为空时直接取空值，忽略 `config.download_dir` JSON 中的实际配置，导致 `get_download_dir_info` 匹配失败、`match_path` 全部跳过
- `only_nexus_media` 标签隔离：pipeline 未将 `PT_TAG` 注入种子标签，监控按 `NEXUS_MEDIA` 过滤时找不到已完成种子
- 磁力链接 `save_path` 始终为空：`_stage_post` 对 magnet 链接显式设 `save_dir=None`
- 图片代理 `/img?url=` 斜杠重定向死循环：前端 nginx 301 加斜杠，Starlette 307 去斜杠互斥，双路由注册消除重定向
- 订阅电影/电视剧 INSERT 失败：`KEYWORD`/`FILTER_ORDER`/`FILTER_RESTYPE` 等可选列为 `NOT NULL` 但传 `None`，仓库层统一空值默认化
- 索引器切换后订阅站点列表不更新：`/download/indexers` 固定返回内置站点，改为 `get_user_indexers()` 随当前激活索引器变化
- 过滤引擎拒绝纯音频文件匹配视频订阅（FLAC/MP3/OST 等）
- 索引器统计插入时自动清理 7 天前旧数据

### 前端
- 探索页面无限滚动卡死：首屏数据加载期 IntersectionObserver 触发被 loading guard 拦截后不再重新触发
- 订阅编辑模态框切换索引器后已保存站点未过滤，旧站点名残留

### 数据库迁移
- 无需迁移

## v4.1.7 (2026-06-23)

### 修复
- API 站点数据刷新无响应：`api_key`/`bearer_token` 贯穿整个用户信息获取调用链，修复 M-Team/Rousi/TNode 等 API 站点的站点数据刷新静默返回 0 条的问题
- Bearer Token 认证重复前缀：`_build_auth` 中 BearerAuth 构造时剥离已添加的 `Bearer ` 前缀，修复 Rousi 等 Bearer 认证站点返回 401
- Rousi 站点配置：`user_info.profile` 端点 query 参数从 URL path 移到 `params` 对象，修复方括号被 URL 编码后服务器不识别的问题
- `DOWNLOADER.DOWNLOAD_DIR` 列 `VARCHAR(255)` 过短导致下载器配置保存报错，改为 `TEXT`
- `SITE_STATISTICS_HISTORY` 和 `SITE_USER_INFO_STATS` 中无默认值列添加 `server_default`，修复 `bulk_insert_mappings` 遇 `None` 值时 MySQL NOT NULL 约束报错
- 刷流任务状态变更统一使用 `BrushTaskState` 枚举，修复 `Y/N/S` 魔法字符串不一致
- 文件转移路径解析 `get_format_dict`/`get_movie_dest_path`/`get_tv_dest_path` 的 `media_service` 参数改为可选，修复无媒体服务时路径格式化报错
- 进度跟踪器 `finish()` 方法补充设置 value=100 和完成文本
- 新增 `GET /download/torrent-remove-tasks/seed-statuses` 端点，返回种子状态中英文列表
- 删种任务种子状态输入框改为多选下拉列表，支持中文显示
- 修复 TMDB 黑名单和搜索文件两处 API 路径重复 `/api/` 前缀的问题
- 区分 `Paused`（已暂停）和 `Stopped`（已停止）的中文标签，避免下拉列表重复
- 修复识别历史统计字段大小写不匹配（`MovieNums` → `movie_nums`）导致 `reduce` 报错
- 修复下载目录分类未推送到下载器：类型匹配支持中英文，`category` 推分类 `label` 推标签
- 新增站点「拾刻」www.ptskit.org（NexusPHP）
- M-Team 添加 description 字段（概述），详情页域名改为 kp.m-team.cc
- HTML 站点解析支持用户配置的别名域名（domain_aliases）
- 修复站点 tag 字段返回字符串导致前端开关状态不正确，pipeline 改用 name 作为下载器标签
- 索引器统计启动不再清空，查询加 24 小时时间过滤，前端添加 24h 标签

### 数据库迁移
- `d5e6f7a8b9c0`：`DOWNLOADER.DOWNLOAD_DIR` 列类型调整为 `TEXT`
- `e6f7a8b9c0d1`：`SITE_STATISTICS_HISTORY.USER_LEVEL` 和 `SITE_USER_INFO_STATS.USER_LEVEL` 添加默认值 `''`
- `f6f7a8b9c0d1`：`SITE_USER_INFO_STATS` 和 `SITE_STATISTICS_HISTORY` 中无默认值的数值/字符串列批量添加 `server_default`

## v4.1.6 (2026-06-23)

### 修复
- 媒体类型识别统一使用 `MediaType.from_string`，支持 `Movie/Series/show/TV` 等别名
- fnOS 媒体库同步：`get_items` 在 API 按库过滤返回空时回退到全量获取后本地过滤，修复同步无数据
- fnOS 客户端：修复 `fetch_all_pages` 中响应数据覆盖请求 payload 的变量遮蔽问题
- 功能开关统一为布尔值：站点 note 中的 `parse/proxy/chrome/subtitle/tag/message/public` 读取写入均使用布尔值
- 修复部分更新 `rss_enable/brush_enable/statistic_enable` 时清除未传入开关的问题，改为增量更新
- 修复 `/sites/detail` 接口返回原始实体数据而非缓存计算后状态的问题

### 重构
- 新增 `SiteUseType` 枚举（RSS=D, BRUSH=S, STATISTIC=T），替代 `D/S/T` 魔法字符串
- 新增 `SwitchState` 枚举（ON=Y, OFF=N），替代 `Y/N` 魔法字符串
- 新增 `UserRssTaskUseType` 枚举（DOWNLOAD=D, SUBSCRIBE=R, SEARCH=S）
- 刷流任务状态统一使用已有的 `BrushTaskState` 枚举（RUNNING=Y, STOPPED=S, DISABLED=N）
- 删除 `SiteEntity` 中未使用的 dead code 属性
- Alembic 迁移：将 `CONFIG_SITE.NOTE` 中旧 `Y/N` 字符串开关转换为布尔值

### 前端
- 站点编辑页：note 开关直接发送布尔值，不再转 `Y/N` 字符串
- 站点类型选择器改用 `NSwitch`，form.public 改为布尔值
- 删除 `parseNoteBool` 兼容函数
- 修复 `NNotificationProvider` 的 extraneous non-props attributes 警告
## v4.1.5 (2026-06-22)

### 修复
- 媒体服务器配置保存兼容无前缀字段，修复前端保存配置时返回“配置为空”
- 豆瓣网络连通性测试改为调用真实豆瓣 API，避免直接访问根路径被误报异常
- 修复媒体服务器配置更新时 `NOTE` 为 `null` 导致 MySQL `IntegrityError` 的问题
- 内置索引器识别 API Key / Bearer Token 认证的站点（如 M-Team），不再因缺少 cookie/headers 被过滤
- 内置索引器匹配站点 `domain_aliases`，修复 M-Team 等使用别名域名配置的站点不显示的问题
- 内置索引器收集 API 站点定义，修复 API 认证站点（如 M-Team）被排除的问题
- IndexerConf 传递 `api_key`/`bearer_token` 到 API 搜索器，修复 M-Team 搜索 401
- 下载链接解析和下载流水线传递 `api_key`/`bearer_token`，修复 API 站点下载认证
- 代理配置支持 http / https / socks5 三种协议
- 下载流水线失败时补上 SSE 事件推送，种子下载失败时直接推送 SSE
- 下载历史存在判断改用 `downloader+download_id` 唯一键，修复任务列表重复和重复插入
- 种子文件名优先取 `filename*=` 头，避免中文 ISO-8859-1 编码报错
- torrent URL 下载时设置 `media_info.enclosure`，避免 `ENCLOSURE` 为 null 报错
- 下载任务列表按 `downloader+download_id` 去重，不再显示重复记录
- 站点维护功能开关支持独立 `rss_enable/brush_enable/statistic_enable` 布尔字段

## v4.1.4 (2026-06-21)

### 修复
- 网络连通性测试耗时为 0：`NetTestService` 改为在 HTTP 请求完成后计算耗时，并改用 `total_seconds()` 避免超过 1 秒时数值错误
- 消息客户端模板保存失败：`MESSAGE_CLIENT.TEMPLATES` 列从 `VARCHAR(255)` 改为 `TEXT`，兼容长 JSON 模板
- FnOS 媒体服务器配置项错误：配置表单从错误的 `Api Key` 改为正确的 `用户名 / 密码`，并添加迁移将已有 `api_key` 值迁移到 `username`

### 数据库迁移
- `89c719931b5f`：`MESSAGE_CLIENT.TEMPLATES` 列类型调整为 `TEXT`
- `1ee439ce9b6d`：FnOS 媒体服务器配置 `api_key` 迁移为 `username`

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
