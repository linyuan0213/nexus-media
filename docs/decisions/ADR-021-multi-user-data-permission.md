# ADR-021: 多用户数据权限与站点访问控制

## Status

Accepted（已实施，见文末「实施记录」）

## Date

2026-09-08

## Context

Nexus Media 已具备基于 RBAC 的**功能权限**体系（`require_permission("x:view|manage")`，见 `src/api/deps.py:166`），但所有业务数据全局共享，属于"单实例多账号无隔离"模型：

- **站点**：站点启用状态（`INDEXERSITECONFIG`）与凭据（`CONFIG_SITE`）全局共享，任何用户可搜索全部启用站点。搜索站点过滤在 `IndexerService._filter_indexers()`（`src/app/indexer/indexer.py:273`）无任何用户维度。
- **订阅**：`SUBSCRIBE_MOVIES` / `SUBSCRIBE_TVS` / `SUBSCRIBE_HISTORY` / `CONFIG_USER_RSS` 均无 `USER_ID`，A 用户可见可改 B 用户的订阅。
- **搜索结果**：`SEARCH_RESULT_INFO` 仅靠 `SEARCH_SESSION_ID` 间接隔离；`SearchRepository.get_search_results()`（`src/app/db/repositories/search_repository.py:185`）的 `user_id` 参数存在但未参与过滤。
- **下载历史**：`DOWNLOAD_HISTORY` 无归属字段，下载中任务列表实时取自下载器客户端，为全局视图。
- **AI 助手**：`src/app/agent/tools/handlers/` 的搜索/订阅/下载工具不透传用户上下文，是当前最大的权限绕过通道。
- 已按用户隔离的例外：`AGENT_CONVERSATION` / `AGENT_WEB_MESSAGE`（agent_memory.py）、`PUSH_SUBSCRIPTION`（push_subscription.py）。

核心需求：

1. 站点级授权：A 用户只能搜索/使用被授权的站点，其余不开放。
2. 订阅行级隔离：A/B 用户订阅互不可见，管理员（superadmin）可见全部。
3. 订阅需记录归属用户。

## Decision

### 1. 权限模型分层

```
L1 功能权限（已有）：能做什么操作     → require_permission("subscription:manage")
L2 数据归属（新增）：能看哪些数据行   → USER_ID 行级过滤
L3 资源访问（新增）：能用哪些站点     → 角色/用户站点授权表 + PUBLIC 白名单
```

**与标准模型对应**：L1 = RBAC0/1（`ROLE_LEVEL` 数值层级）；L2 = DAC 属主模型 + 应用层 RLS；L3 = 资源级 ACL（subject-resource-action）。与 GitLab/Grafana 等成熟多用户系统同构，无自创机制。RBAC2（职责分离）与 ABAC 超出本场景需求，不采用。

**默认策略开关**：`PUBLIC=1` 默认全开放是兼容单用户实例的妥协，非 fail-closed。提供系统级配置 `站点授权默认策略: open|closed`，安全敏感部署可一键切 closed（新站点默认需显式授权）。

### 1.1 共享 vs 用户独有总览

一句话规则：**"内容"全部共享，"行为与偏好"全部归属用户**。

**用户独有（行级隔离）**：

| 数据 | 说明 |
|---|---|
| 订阅四表（电影/剧集/历史/剧集进度） | 互不可见，superadmin 看全部 |
| 自定义 RSS 及任务历史 | 同上 |
| 搜索结果 | 按用户隔离 |
| 下载历史（手动） | 归属发起人；订阅触发的全局下载记 NULL，全局可见 |
| API Key | 按 `CREATED_BY` 隔离 |
| 站点授权 / 渠道绑定 | 角色级+用户级站点授权、每用户渠道绑定（三张新表） |
| AI 会话/消息、Web 消息、Web Push | 现状已隔离 |
| 站点可见性 | PUBLIC 白名单 ∪ 个人授权 |

**全局共享（无隔离）**：

| 资源 | 说明 |
|---|---|
| 站点凭据/定义 | 一站一 Cookie 全站共用（用户级凭据 = Phase 2） |
| 下载器/下载预设/存储/媒体库路径/媒体服务器 | 全局基础设施 |
| **媒体库内容本身** | 已下载内容所有人可见（明确不隔离内容） |
| 下载/洗版执行 | 全局唯一物理下载，`SUBSCRIBE_TORRENTS` 全局去重 |
| 转移历史 | 全局物理行为记录 |
| 刷流全链路 | 管理员专属，不下放 |
| 过滤规则/分类/识别词/同步路径/插件/通知渠道配置/系统字典 | 全局配置 |
| 聚合统计 | 全局（普通用户按可见站点过滤站点维度） |

### 2. 角色码与权限码分工

| 场景 | 机制 |
|---|---|
| 接口级功能权限 | 权限码（现状不变） |
| 跨用户数据全量可见（管理员） | 角色码 `superadmin` 判定（复用 `src/app/services/rbac/user_service.py:10` 的 `SUPERADMIN_ROLE_CODE` 约定，与 `src/api/routers/auth.py:138`、`src/app/db/models/rbac.py:123` 一致） |
| 站点可用性 | `RBAC_ROLE_SITES` ∪ `RBAC_USER_SITES` + `INDEXERSITECONFIG.PUBLIC` 白名单；superadmin 全量 |
| 给用户分配站点/角色 | 权限码 `site:assign` / `role:update` + `ROLE_LEVEL` 防越权 |

**不引入** `is_admin` 用户属性，**不新增** `data:all` / `site:view-all` 权限码。管理员全量可见是角色码语义，不是可授予的权限点。

### 3. UserContext 扩展

`src/app/schemas/auth.py:32` 的 `UserContext` 新增 `role_codes`：

```python
class UserContext(BaseModel):
    user_id: int
    username: str
    nickname: str | None = None
    level: int
    permissions: list[str]
    role_codes: list[str] = []   # 新增
```

- 登录/刷新签发 JWT 时（`src/app/services/auth_service.py`）payload 可附带 `role_codes` 供前端展示用，但**后端判定不信任 JWT 内嵌副本**。
- **即时生效要求**：`permissions` / `role_codes` **不信任 JWT 内嵌副本**——`require_permission` 与 `apply_owner_scope` 判定改从服务端短 TTL 缓存读取（`RBACCheckService.get_user_permissions` 扩展返回 role_codes，角色/权限变更时主动失效），JWT 只承载身份认证。否则角色被回收后到 token 过期前，superadmin 仍全量可见所有用户数据（比功能权限滞后更危险，属数据泄露面）。
- API Key 认证（`src/api/deps.py:85`）继承创建者权限时同步继承 `role_codes`。
- 旧 Token 兼容路径（deps.py:470）`role_codes` 为空列表，映射系统上下文（见 5.5）。

### 4. L3 站点访问控制

#### 4.1 站点授权表（角色 + 用户两级）

**角色级 `RBAC_ROLE_SITES`**（主）与**用户级 `RBAC_USER_SITES`**（例外补充），结构相同：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ID` | Integer PK | |
| `ROLE_ID` / `USER_ID` | Integer FK → RBAC_ROLES.ID / RBAC_USERS.ID，CASCADE | 授权对象 |
| `SITE_NAME` | String(128) | 站点名，对齐 `INDEXERSITECONFIG.SITE_NAME`；第三方索引器用 `jackett:<站点id>` / `prowlarr:<id>` 精确授权，或 `jackett:*` / `prowlarr:*` 整体授权 |
| `PERMISSIONS` | JSON | 用途粒度：`["search", "rss"]`（search=索引器搜索可用，rss=订阅 RSS 源可选；刷流不下放，无 brush 用途） |
| `GRANTED_BY` | Integer | 授权人 user_id |
| `CREATED_AT` / `UPDATED_AT` | DateTime | |

唯一索引：角色表 `(ROLE_ID, SITE_NAME)`，用户表 `(USER_ID, SITE_NAME)`。

**设计取舍**：站点可见性挂角色与现有 RBAC（权限/菜单都挂角色）一致，便于按用户组批量管理（如"普通组 3 站 / VIP 组 10 站"）；用户级表处理个体例外。**纯并集、无拒绝语义**——同一站点角色级给 `["search"]`、用户级给 `["rss"]` 合并为 `["search","rss"]`；要让某用户少一个站，就不把该站放进他的角色，而非做 deny。

#### 4.2 可见性规则

```
superadmin      → 全部站点（不查授权表）
普通用户        → (PUBLIC=1 的站点 ∪ 角色级授权 ∪ 用户级授权)，再按 PERMISSIONS 用途粒度过滤
```

**索引器站点与 RSS 站点是同一套站点实体**（同以 `SITE_NAME` 为键），按用途分别生效：

| 用途 | 控制范围 | 执行点 |
|---|---|---|
| `search` | 搜索时可用站点（索引器维度） | `_filter_indexers` 过滤（4.3） |
| `rss` | 订阅 `RSS_SITES` 可选站点、后台 RSS 刷新是否为该用户匹配 | 订阅保存校验 + 执行时兜底（4.3） |

示例：授权 `{站点X: ["search"], 站点Y: ["search","rss"]}` → 用户能搜 X、Y，但订阅 RSS 源只能选 Y。

**自定义 RSS 源**（`CONFIG_USER_RSS`）不属于站点授权体系：用户自有数据，地址用户自己填，无需授权。

复用 `INDEXERSITECONFIG.PUBLIC` 现有字段作为开放白名单：默认全部站点 `PUBLIC=1`（兼容现有单用户/全开放行为，迁移零成本），管理员将需管控的站点置 `PUBLIC=0` 后逐用户授权。

#### 4.3 拦截点

- **核心**：`IndexerService._filter_indexers()`（indexer.py:273）注入用户可见站点集合。
- `SearchContext`（`src/app/services/search_context.py:25`）已有 `user_id` 字段，从路由透传。
- 站点列表 API（`src/api/routers/site.py`）：普通用户列表按可见性过滤；`site:manage` 管理接口不受限。
- RSS 刷新匹配用户订阅时按订阅归属用户的可见站点过滤；用户订阅的 `SEARCH_SITES`/`RSS_SITES` 保存时校验 ⊂ 可见站点集合（刷流为管理员专属，走系统上下文，不参与用户过滤）。
- **执行时兜底**：保存时校验不够（管理员可事后回收授权或关闭 `PUBLIC`），后台 RSS/订阅任务**每次执行时**按当前可见站点集合重新过滤，已回收站点自动跳过并记操作日志。
- **默认站点求交**：全局默认搜索站点（`DefaultSubscribeSettingTV/MOV.search_sites`）对用户生效时 = 系统默认 ∩ 用户可见站点；交集为空时搜索直接返回空并提示联系管理员授权，不回落到全量站点。
- **缓存与失效**：两级站点授权表查询走短 TTL（≤60s）缓存，授权/回收/`PUBLIC` 变更时主动失效。站点可见性在每次执行时从 DB/缓存判定而非 JWT，授权变更即时生效（与第 3 节的权限/角色服务端缓存一致，全链路无 JWT 滞后）。
- **AI 助手**：工具 handler 强制接收 `UserContext`，搜索走站点过滤，订阅写入带 `USER_ID`——消除权限绕过通道。

#### 4.4 站点凭据

站点 Cookie/API Key 属敏感共享凭据，站点管理（`site:manage`）保持管理员专属；普通用户只能获得搜索结果，任何接口不向其暴露凭据。

### 5. L2 数据归属（行级隔离）

#### 5.1 加 `USER_ID` 列的表

| 表 | 模型位置 | 说明 |
|---|---|---|
| `SUBSCRIBE_MOVIES` | models/subscribe.py:35 | 电影订阅 |
| `SUBSCRIBE_TVS` | models/subscribe.py:81 | 剧集订阅 |
| `SUBSCRIBE_HISTORY` | models/subscribe.py:14 | 订阅历史 |
| `SUBSCRIBE_TV_EPISODES` | models/subscribe.py:118 | 订阅剧集进度，通过 RSSID 挂在订阅上，必须跟随隔离 |
| `CONFIG_USER_RSS` | models/config.py:90 | 自定义 RSS |
| `USER_RSS_TASK_HISTORY` | models/plugin.py:56 | 自定义 RSS 处理历史，跟随 `CONFIG_USER_RSS` 归属 |
| `SEARCH_RESULT_INFO` | models/search.py:14 | 搜索结果（同时启用 `get_search_results` 已有的 `user_id` 参数） |
| `DOWNLOAD_HISTORY` | models/download.py:29 | 下载历史：手动下载归属发起人；订阅触发的全局下载记 `NULL`（系统行，见 5.4） |

统一为 `USER_ID = Column(Integer, ForeignKey("RBAC_USERS.ID"), index=True, nullable=True)`。

**API Key 行级过滤**（不加列）：`API_KEY` 表已有 `CREATED_BY`（apikey.py:31），持 `user:self` 的普通用户只能查看/吊销 `CREATED_BY == 自己` 的 Key，superadmin 看全部。

**明确保持全局的例外**：

- `SUBSCRIBE_TORRENTS`（订阅已下载去重表，subscribe.py:67）：**保持纯全局、不加列**。下载器/存储/媒体库全局共享，物理下载全局唯一，"存在即跳过"语义不变；多用户进度问题由 5.4 节的记账分离解决，不靠重复下载。
- `TRANSFER_HISTORY`（转移历史）：转移是全局物理行为，一次共享下载只产生一条转移记录，无法归属单一用户；且文件入共享媒体库后内容本身对所有用户可见，隔离无隐私收益。**不加列，仅 `transfer:view`（管理员）可见**。
- 刷流相关（`SITE_BRUSH_TASK` / `SITE_BRUSH_TORRENTS` / `BRUSH_EVENT_LOG`）：刷流消耗 `CONFIG_SITE` 共享凭据账号的流量与 H&R 考核，开放给普通用户的风险不可控。**刷流整体维持 `brush:manage` 管理员专属，不做隔离也不下放**。
- 站点用户数据（`SITE_USER_INFO_STATS` / `SITE_USER_SEEDING_INFO` 等）：数据源是 `CONFIG_SITE` 全站共享凭据，属站点维度而非用户维度（见第 11 节 Phase 2）。

`NULL` 语义：**系统/后台任务自动创建的行**。订阅类 NULL 行仅 superadmin 可见；搜索/下载历史 NULL 行全局可见（兼容未归属的存量行为，且与共享媒体库语义一致——订阅触发的全局下载所有用户都受益）。

> **隔离目标声明**：本方案隔离的是"愿望单 / 进度 / 行为发起记录"，**不隔离内容可见性**——媒体库、下载器、存储全局共享，任何用户都能在媒体服务器上看到全部已下载内容。需要内容级隔离时应部署多实例，而非本方案。

#### 5.2 统一查询过滤

新增 helper（放 `src/app/db/repositories/base.py`）：

```python
SUPERADMIN_ROLE_CODE = "superadmin"  # 引用 user_service 常量

def apply_owner_scope(query, model, user: UserContext):
    if SUPERADMIN_ROLE_CODE in user.role_codes:
        return query
    return query.where(model.USER_ID == user.user_id)
```

- 所有订阅/搜索/下载历史 repository 的读查询统一过此 helper。
- 写操作（更新/删除）校验 `row.USER_ID == ctx.user_id`（superadmin 除外），越权返回 **404** 而非 403，避免资源存在性探测。
- superadmin 的列表 API 支持 `?user_id=` 参数查看指定用户数据。

#### 5.3 后台任务兼容

- RSS 定时刷新、订阅补全等后台任务按 `USER_ID` 分组执行。
- 订阅命中的搜索结果落库时带上订阅归属的 `USER_ID`。
- 订阅触发的全局下载在 `DOWNLOAD_HISTORY` 只记**一行** `USER_ID=NULL` 的系统记录（一次物理下载服务多个用户订阅，不产生重复行）；手动下载记录发起人。
- 通知事件携带 `user_id`，路由规则见 5.6。

#### 5.4 多用户订阅同一媒体的进度与去重

前提：下载器、存储空间、媒体库全部全局共享，**物理下载全局唯一**，不存在"每用户各下一份"。

进度字段（`CURRENT_EP` / `LACK` / `SUBSCRIBE_TV_EPISODES`）在用户各自的订阅行上，天然独立。需要解决的是：**纯全局去重会让后订阅的用户命中已下载种子时被跳过、进度卡死**。因此把"下载执行"与"用户记账"分离：

1. **调度分组**：同一媒体（TMDBID+季）的多个用户订阅合并为一次搜索/RSS 匹配，结果 fan-out 到每个用户的订阅行，各自过各自的过滤规则。
2. **下载判定看全局库**：命中后先查全局去重表（`SUBSCRIBE_TORRENTS`）与下载历史——
   - 内容已存在且满足该用户的过滤规则 → **零下载**，直接给该用户记"已满足"（更新自己的 `TV_EPISODES` / `CURRENT_EP` / `LACK` + 归属通知）。
   - 内容不存在 → 发起全局下载，写入全局去重表；下载完成后**所有等待该内容的用户订阅一起记账**。
   - 内容已存在但质量不满足（如库内 1080p、该用户要 4K）→ 走现有洗版机制（`OVER_EDITION`）全局升级下载一次，完成后相关用户进度全部推进。不产生第二份物理副本。
3. **`SAVE_PATH` 不构成隔离维度**：订阅保存路径始终落在全局分类目录体系内，文件入共享媒体库后对所有用户可见，不做用户目录隔离、不做 hardlink。
4. **并发去重加锁**：fan-out 记账与手动下载可能并发命中同一种子，发起下载前用现有 `DISTRIBUTEDLOCK` 按 `torrent:{enclosure_hash}` 加锁，防止全局去重表插入竞态导致重复下载。
5. **订阅唯一约束**：`SUBSCRIBE_TVS` 加 `(USER_ID, TMDBID, SEASON)` 唯一索引、`SUBSCRIBE_MOVIES` 加 `(USER_ID, TMDBID)` 唯一索引，防止同用户重复订阅；跨用户订阅同媒体合法。
6. **插件/自动化创建的订阅归属**：`doubansync`、`autosub`、`doubanrank` 等插件自动创建的订阅记 `USER_ID=NULL`（系统归属，仅 superadmin 可见）；如插件配置支持指定归属用户，按配置归属。豆瓣同步等绑定的是全站共享账号，不设为用户级功能。

即：**下载/洗版是全局系统行为，订阅行只是每个用户的"愿望单 + 进度账本"**。是否触发下载由全局库状态决定，用户维度只负责记账与通知。

#### 5.5 无用户上下文路径（后台任务 / 遗留 Token）

行级过滤引入后，所有无 `UserContext` 的调用路径必须显式处理，否则会突然"零数据零站点"：

- **系统上下文**：定义 `SYSTEM_USER_CONTEXT`（`user_id=0`，`role_codes=["superadmin"]`），后台调度、事件 handler、启动初始化统一使用。
- **APIv1 旧 Token 路径**（deps.py:470）：`role_codes=[]` 会导致过滤后无数据。该路径直接映射为 `SYSTEM_USER_CONTEXT`（旧 API 本就是管理员粒度，保持行为不变）。
- **实施时审计**：grep 所有调用订阅/搜索/下载 repository 的位置，确保每条路径要么透传真实 `UserContext`，要么显式使用系统上下文，禁止隐式缺省。

#### 5.6 通知路由

通知渠道配置（`MESSAGE_CLIENT`）全局共享，必须防止用户事件经外部渠道广播泄漏：

- **用户归属事件**（订阅命中、下载完成等带 `user_id`）：推 Web 消息通道（`AGENT_WEB_MESSAGE` 已有 USER_ID 隔离，agent_memory.py:56）；外部渠道若该用户已绑定（5.8），经绑定表取该用户的渠道目标（chat_id / 推送 Key）后**定向单发**；未绑定则仅 Web。
- **系统事件 + superadmin 归属事件**（`user_id` 为 NULL 或 superadmin）：可推全局外部渠道（配置的群/频道 chat_id）。
- 发送侧在 dispatcher 层做 `user_id → chat_id` 翻译（当前 `Telegram.send_msg` 的 `user_id` 参数语义即 chat_id，telegram.py:174）。

#### 5.7 用户删除级联

- 业务行（订阅四表、`CONFIG_USER_RSS`、`SEARCH_RESULT_INFO`、API Key、`RBAC_USER_SITES`、渠道绑定 `RBAC_USER_CHANNELS`）：`ON DELETE CASCADE`，随用户删除；`RBAC_ROLE_SITES` 随角色删除 CASCADE。
- 审计/日志类（`RBAC_OPERATION_LOG` / `RBAC_USER_LOGIN_LOG` / `DOWNLOAD_HISTORY` / `USER_RSS_TASK_HISTORY`）：`USER_ID` 置 NULL（`ON DELETE SET NULL`），保留审计痕迹。
- **存量已隔离表**：`AGENT_CONVERSATION` / `AGENT_WEB_MESSAGE` / `PUSH_SUBSCRIPTION`（现状已有 USER_ID）删除用户时须一并 CASCADE——实施时确认现有 user_service 已处理，避免删用户留孤儿数据。
- 删除用户的服务层需显式处理上述各类，并复用现有"禁止删除最后一个 superadmin"检查（user_service.py:83）。

#### 5.8 消息渠道身份绑定

现状问题：交互渠道入站是"渠道级信任"——白名单 + 直接授予全部权限码（`system/message.py:240` 的 `_TRUSTED_CHANNEL_PERMISSIONS`），无渠道身份 → 系统用户映射。多用户模型下 IM 发起的订阅无归属、权限失控。

**渠道分类**：

| 类别 | 渠道 | 身份问题 |
|---|---|---|
| 交互渠道（有入站） | Telegram、企业微信（内置）；Slack、SynologyChat（插件，走 `InteractiveCallbackMixin`） | 入站需识别"是谁" |
| 纯推送渠道（无入站） | Bark、Ntfy、Gotify、Server酱、PushPlus、PushDeer、钉钉、Chanify、IYUU、Webhook、飞书 | 入站无问题；出站定向需每用户目标 Key |
| Web 通道 | 内置 `WebMessage` | 天然系统用户身份，无需绑定 |

**新表 `RBAC_USER_CHANNELS`**（一张表统一两类渠道）：

| 字段 | 说明 |
|---|---|
| `ID` / `USER_ID` | FK → RBAC_USERS，CASCADE |
| `CHANNEL` | `telegram` / `wechat` / `slack` / `synologychat` / `bark` / `ntfy` / ... |
| `CHANNEL_USER_ID` | 渠道侧身份或推送目标（见下） |
| `STATUS` / `CREATED_AT` | |

唯一索引 `(CHANNEL, CHANNEL_USER_ID)`，一个渠道账号只能绑一个系统用户。

**`CHANNEL_USER_ID` 取值**：

| 渠道 | 取值 |
|---|---|
| Telegram | 消息 `from.id` |
| 企业微信 | 消息 `FromUserName` |
| Slack | 事件 `user` id |
| SynologyChat | webhook `user_id` |
| Bark / Ntfy / Server酱 等推送渠道 | 用户的推送 Key / Token / 设备标识 |

**两种绑定模式**：

1. **入站码绑定**（交互渠道）：Web 端 `POST /user/channel-bindings/code` 生成 6 位绑定码（TTL 10 分钟，存 TokenCache，限 5 次校验失败即失效防爆破）→ 用户在 IM 向 Bot 发送 `/bind 123456` → 校验后写入绑定表。`/unbind` 自助解绑。
2. **Web 手动登记**（纯推送渠道，无入站发不了绑定码）：用户在 Web 设置页粘贴自己的推送 Key，直接写入绑定表——顺带实现"用户级外部通知渠道"。

管理员可在用户管理页查看/强制解绑任意绑定。

**入站识别改造**（`message_webhook.py` 及各渠道回调入口）：

```
渠道身份查 RBAC_USER_CHANNELS
  ├─ 命中 → 从 RBAC 实时构造 UserContext（user_id + permissions + role_codes）
  │        → 与 Web 渠道同一链路：订阅写 USER_ID、搜索走站点过滤
  └─ 未命中 → 拒绝交互，回复绑定指引
```

**`_TRUSTED_CHANNEL_PERMISSIONS` 退役**（行为变更）：升级后未绑定的 IM 用户失去交互能力。迁移时把现有 Telegram `admin_ids` 中的 chat_id 自动绑定到第一个 superadmin，单用户实例行为不变；企业微信等其他交互渠道的存量受信 ID 同理迁移。

**会话隔离**：搜索/订阅的分页选择缓存（`MessageSearchService` 单例）键从 `(channel, chat_id)` 改为 `(channel, user_id)`，多用户不串会话。群聊中按渠道身份识别个人，未绑定成员消息忽略。

### 6. 保持全局共享、不做隔离的领域

以下为全局基础设施配置，维持 `manage` 权限管理员专属，**不加行级隔离**（隔离无意义且破坏后台任务）：

- 过滤规则 / 分类（`CONFIG_FILTER_*` / `CONFIG_CATEGORY_*`）
- 下载器实例 / 下载预设（`DOWNLOADER` / `DOWNLOAD_SETTING`）
- 媒体服务器 / 媒体库路径 / 存储后端
- 通知渠道配置（`MESSAGE_CLIENT`）、插件、识别词、同步路径、系统字典
- 转移历史（`TRANSFER_HISTORY`）、刷流全链路（见 5.1 例外说明）
- 聚合统计（`INDEXERSTATISTICS` / 站点统计）：管理员视角的全局数据；普通用户仪表盘若展示，按可见站点过滤站点维度数据

进行中下载任务列表（实时取自下载器客户端）为全局视图，仅 `download:view` 以上可见；普通用户的下载可见性通过 `DOWNLOAD_HISTORY.USER_ID` 体现。

**权限码拆分（审查发现）**：`download.py` 当前把下载器基础设施管理（`/downloaders/update|delete`、`/settings`、删种任务、清空转移黑名单）与用户下载操作（`/tasks/add|add_torrent|start|stop|remove`）全挂同一 `download:manage`。若普通用户获得"发起下载"能力即获得下载器配置管理权，属越权。

- 新增 `download:create`：普通用户发起/控制下载任务（add/start/stop/remove）。
- `download:manage` 收窄为基础设施管理（下载器配置、下载预设、删种任务），保持管理员专属。
- 搜索结果页"下载"按钮走 `download:create`；AI/IM 工具链的下载动作同样按 `download:create` 校验（system context 除外）。

**交互搜索入口权限**：`POST /search`（system.py:552）现误用 `setting:view/update`，应改为已有 `search:execute`（constants.py:33），否则开 Web 手动搜索会连带暴露设置页。搜索结果仍按 5.1 的 `SEARCH_RESULT_INFO.USER_ID` 隔离。

**资源消耗兜底**：Phase 1 所有下载都消耗共享站点账号与全局带宽/磁盘。普通用户下载能力通过 `download:create` 授予（授予即信任发起下载），但不能触及下载器/预设等基础设施；如需每用户配额、下载审批，作为后续增强单独设计，不在本 ADR 范围。

#### 6.1 共享资源保护规则（审查补充）

共享资源的消耗与故障是**全局的**，用户维度操作不得反向作用于共享资源。硬性规则：

1. **用户操作单向性**：用户维度只增（愿望单/进度/记账），共享资源只由系统收敛（去重/洗版/清理/重试）。用户删除订阅**不停**进行中的共享下载、**不删**已入库文件；用户修改质量/保存路径只影响其本人满足判定，不触发已有内容的洗版回退或删除——否则 A 删订阅会误伤 B 等待中的下载。
2. **共享站点账号请求闸门**：M 用户并发搜索会以 `搜索线程 × 站点 × 用户` 放大对共享凭据账号的请求。站点级限流器（ADR-008）必须**全局键控**（键=站点，跨用户、进程级），搜索并发闸门与 RSS 轮询在站点维度共享同一额度池；RSS 过期/站点请求失败告警属全局事件，推管理员。
3. **RSS 刷新站点级聚合**：保持现状形态（rss_feed.py:150 每站一次拉取 + 全部订阅匹配），调度入口全局唯一，用户订阅只是匹配集合，禁止按用户各触发一轮全站轮询（请求量 ×N）。
4. **全局下载闸门**：磁盘水位、下载器同时种子上限、连接数等全局闸门统一收敛到 `download:create` 服务入口，任何用户的下载都过同一闸门，防止单个用户占满共享磁盘影响全体。
5. **事件路由分流**：成功类事件按归属用户定向推送（5.6）；失败/人工介入类（转移失败、`TRANSFER_UNKNOWN`、种子红种）属共享资源故障，推系统/管理员渠道。
6. **全局默认设置快照**：用户新建订阅继承全局默认（`DefaultSubscribeSettingTV/MOV`、默认保存路径）时落库固化快照并在 UI 明示，避免管理员后续改全局配置导致存量订阅行为漂移。
7. **插件约束**：插件 handler 必须透传 `UserContext`；插件代码禁止绕过 repository 直连 ORM 读写订阅/下载/搜索数据（owner-scope 不可旁路）。该约束加入插件开发规范。
8. **站点账号数据按可见站点过滤**（已实施）：站点活跃度/历史/日统计/做种/用户统计接口对非超管按站点授权裁剪，只返回用户被授权站点的共享账号数据；`open` 策略、superadmin、`builtin:*` 通配不受限。媒体库路径、TMDB 黑名单收敛为 `library:manage`。

### 7. 其他补全项

| 项 | 方案 |
|---|---|
| API Key 数据权限 | 已继承创建者功能权限（deps.py:85），同步继承 `role_codes` 后行级过滤天然生效 |
| 用户自助 | 新增权限码 `user:self`，改自己密码/头像、管理自己的 API Key，路由校验 `user_id == ctx.user_id` |
| 角色防越权 | 授权/改角色时校验操作者角色 `ROLE_LEVEL` ≤ 目标角色 level（数字越小级别越高），防止普通 admin 授予 superadmin |
| 操作审计 | `RBAC_OPERATION_LOG` 已有 USER_ID，站点授权/回收、越权访问尝试纳入审计 |

新增权限码：`site:assign`、`user:self`、`download:create`（第 6 节）；并修正 `POST /search` 使用已有 `search:execute`。以上追加到 `DEFAULT_PERMISSIONS`（`src/app/services/rbac/init/constants.py:3`）；superadmin 角色靠现有 `all_permissions` 启动补齐机制（role_init.py:40）自动获得。

### 8. 数据库迁移

一个 Alembic 迁移包含：

1. 新建 `RBAC_ROLE_SITES`、`RBAC_USER_SITES`、`RBAC_USER_CHANNELS` 三张表。
2. 第 5.1 节各表加 `USER_ID` 列 + 索引。
3. 存量数据归属：订阅相关四张表与自定义 RSS 的存量行 `USER_ID` 置为第一个 superadmin 用户 ID；`SEARCH_RESULT_INFO` 有 24h 概率清理（search_repository.py:167）可直接清空；`DOWNLOAD_HISTORY` 存量留 NULL；现有 Telegram `admin_ids` 中的 chat_id 自动生成到第一个 superadmin 的渠道绑定（5.8）。
4. `INDEXERSITECONFIG.PUBLIC` 存量全部保持 `1`（行为不变）；新增系统配置项 `site_grant_default_policy`（open/closed，默认 open），决定新建站点时 PUBLIC 默认值。
5. 订阅唯一索引（5.4 第 5 条）：建索引前需先合并同用户重复订阅行。

**SQLite 注意**：既有表加 FK 列需用 Alembic `batch_alter_table`（SQLite 不支持 ALTER ADD CONSTRAINT），并确认连接开启 `PRAGMA foreign_keys=ON`。

**单用户实例零感知**：唯一用户为 superadmin 时所有过滤短路，行为与现状完全一致。

### 9. API 变更

| 接口 | 说明 |
|---|---|
| `GET /rbac/roles/{id}/sites` / `PUT /rbac/roles/{id}/sites` | 角色站点授权（`site:assign`） |
| `GET /rbac/users/{id}/sites` / `PUT /rbac/users/{id}/sites` | 用户站点授权（`site:assign`） |
| `GET /sites/visible` | 当前用户可见站点列表（供搜索/订阅 UI） |
| `POST /user/channel-bindings/code` | 生成渠道绑定码（`user:self`，交互渠道用） |
| `POST /user/channel-bindings` | 手动登记推送渠道 Key（`user:self`，纯推送渠道用） |
| `GET/DELETE /user/channel-bindings` | 查看/解绑自己的渠道身份（`user:self`） |
| 订阅/下载历史列表 | 增加 `?user_id=`（仅 superadmin 生效） |
| `/auth/me` | `role_codes` 已有 roles 返回，无需变更 |

### 10. 落地顺序

1. **基础**：`UserContext.role_codes` + `RBACCheckService` 服务端缓存改造（权限/角色即时生效，不依赖 JWT 副本）+ `apply_owner_scope` helper。
2. **订阅隔离**：订阅四表 + 自定义 RSS 加列，repository / API / 后台任务接入（含 5.4 调度分组与记账分离、5.5 系统上下文改造）。
3. **站点授权**：角色/用户两级授权表 + indexer 过滤 + 授权管理 API + 站点可见性接口。
4. **搜索/下载归属**：`SEARCH_RESULT_INFO` / `DOWNLOAD_HISTORY` 接入。
5. **AI 工具链 + IM 绑定**：handler 透传 `UserContext`；`RBAC_USER_CHANNELS` 与入站身份改造（5.8），通知按归属路由（5.6）。
6. **前端**：站点授权管理页、订阅/下载页"我的/全部"切换（superadmin）、搜索站点选择器按可见站点渲染、用户设置页渠道绑定码生成。

**上线门禁**：步骤 1-4 完成后才允许创建普通用户；步骤 5（AI 工具透传 + IM 绑定）完成前，普通用户不得授予 `agent:*` 权限、交互渠道保持仅绑定 superadmin——否则 `_TRUSTED_CHANNEL_PERMISSIONS` 与 agent 工具链是两个完整的权限绕过通道。步骤 6 可与后端并行。

### 11. Phase 2（后续阶段，不在本 ADR 范围）

**用户级站点凭据**：`CONFIG_SITE` 目前一站一 Cookie 全局共享，多用户实际共用管理员一个人的 PT 账号搜索/下载，做种量与 H&R 考核都挂在该账号上。若需每个用户使用自己的站点账号，则 `CONFIG_SITE` 加 `USER_ID` 做用户级凭据覆盖（用户凭据优先，缺省回落全局凭据），站点用户数据/做种统计随之按凭据归属。此项与行级隔离正交，单独设计。

## 实施记录（2026-09-10）

分支 `feature/multi-user-permission`（后端 + 前端 `nexus-media-web` 同名分支），3036 测试通过，ruff/pyright 全绿。

### 已交付

| 层 | 内容 |
|---|---|
| 基础设施 | `UserContext.role_codes`/`is_superadmin`、`system_user_context()`、`RBACSnapshotCache` 权限快照（TTL 60s + 变更主动失效，判定走服务端不信任 JWT 副本）、`data_scope.apply_owner_scope/is_owner` |
| 数据模型 | 8 张业务表加 `USER_ID`（订阅四表/自定义RSS及其历史/下载历史；搜索结果沿用既有 String(64) 列），新增 `RBAC_ROLE_SITES`/`RBAC_USER_SITES`/`RBAC_USER_CHANNELS`；Alembic 迁移 `d8e9f0a1b2c4`（含存量归属首个 superadmin、重复订阅去重、具名外键 CASCADE/SET NULL、可回滚） |
| 站点授权 | 角色级 ∪ 用户级授权（`search`/`rss` 用途粒度）、`site_grant_default_policy` 开关、索引器搜索过滤、RSS 执行时兜底、订阅保存白名单、授权管理 API + `/sites/visible`、站点统计数据按可见站点过滤 |
| 数据隔离 | 订阅/自定义RSS/搜索/下载历史全链路归属过滤与越权守卫（越权为无操作）；通知按归属用户定向（Web 隔离 + 绑定渠道单发） |
| 账号链路 | JWT 仅认证、API Key 继承创建者快照、IM 渠道绑定（绑定码/身份解析/未绑定拒绝）、系统上下文 |
| 权限码 | 新增 `site:assign`/`user:self`/`download:create`/`transfer:view`；`POST /search` 改用 `search:execute`；默认 `user` 角色移除 `site:view`/`service:view` 及站点管理/服务面板菜单 |
| 生命周期 | 删除用户/角色时 `OwnedDataCleaner` 显式清理归属数据（SQLite 未启用外键级联，服务层兜底） |

### 与设计的偏差（有意简化，功能正确）

1. **5.4 fan-out 落法更轻**：RSS 刷新本就是站点级一次拉取，"搜索一次"天然成立。实现为 matcher 收集全部命中订阅 + 下载完成后联动完成兄弟订阅；**仅联动过滤签名一致且未开洗版**的兄弟订阅（避免高要求用户被低清副本满足）。部分季集的逐集进度联动未做，兄弟订阅待下一轮匹配推进（最终一致）。
2. **任务队列仍为全局视图**：`download:view` 可见进行中下载列表（ADR 5/6 有意设计，共享下载器），保留原状。
3. **转移历史管理员专属**：原由 `library:view` 守卫导致越权可见，已改为 `transfer:view`/`library:manage`；无 owner 字段，故不支持"只看自己的"。
4. **搜索结果 USER_ID 为既有 String(64) 列**：模型与读写对齐既有类型，避免 Integer/String 漂移。
5. **Telegram 轮询不再按 `admin_ids` 拦截**：多用户由绑定层鉴权（`admin_ids` 仅存量迁移为绑定）。

### 已知残留

- 存量安装的默认角色权限不会自动同步（角色权限仅首次创建时分配）；新权限码需管理员在角色管理中手动授予，或将 `user` 角色的 `site:view`/`service:view` 手动移除。
- 钉钉个人主动推送依赖短期 sessionWebhook，主动推送不可靠（平台限制），入站命令正常。
- 前端入口（站点授权抽屉、渠道绑定页、聚合视图、按用户筛选）已实现；`?user_id=` 下载历史筛选后端就绪、前端暂无独立页面。

## Consequences

### 正面

- 站点、订阅、搜索、下载形成完整的三层权限模型，且与现有 RBAC 权限码体系正交，无侵入。
- superadmin 语义收敛到单一角色码常量，无 `is_admin` 死代码与 `*` 通配的歧义。
- 权限/角色判定走服务端缓存，授权回收即时生效（消除 JWT 内嵌权限的滞后面）。
- 单用户/全开放实例迁移后行为不变。
- AI 助手与 IM 全权信任两个权限绕过通道被堵上。

### 代价

- 8 张表加列（订阅 4 + 自定义 RSS 2 + 搜索结果 1 + 下载历史 1）+ 3 张新表（角色站点、用户站点、渠道绑定），repository 层需全面过 `apply_owner_scope`，遗漏即泄漏——需配套测试覆盖（每表至少：本人可见、他人不可见、superadmin 全量、越权写 404 四类用例）。
- 后台任务需携带归属上下文，签名有改动；无上下文路径必须显式用系统上下文（5.5）。
- 服务端权限/角色缓存引入失效与一致性成本；角色/权限变更点需统一触发失效，遗漏会导致权限不生效（向安全侧偏）。

### 风险

- 站点名作为授权键（`SITE_NAME`）在站点改名时需级联更新授权表——站点改名属低频管理操作，在站点更新服务中处理。
- 角色级站点授权收回影响整组用户，属预期语义；授权/回收操作已纳入审计（第 7 节），执行时兜底过滤（4.3）保证收回即时生效。
- 第三方索引器（Jackett/Prowlarr）站点命名与内置不一致（见 ADR-016），授权表用 `jackett:<id>` / `prowlarr:<id>` 精确授权或 `jackett:*` / `prowlarr:*` 整体授权（4.1）。
- 共享凭据下普通用户的下载/订阅行为都消耗管理员站点账号（做种、H&R）——通过功能权限码谨慎授予缓解，根本解在 Phase 2 用户级凭据。
- 并发下载竞态依赖 `DISTRIBUTEDLOCK` 按种子加锁（5.4 第 4 条），单实例部署下退化为进程内锁，可接受。
- IM 渠道"全权信任"退役（5.8）是行为变更：升级后未绑定的 TG 用户失去交互能力，需发版说明中明确提示先完成绑定。
- APIv1 旧 Token 映射系统上下文（5.5）等于全权通道：若旧 API 仍对外开放（移动端/第三方脚本），会绕过全部隔离——实施时确认其暴露面，必要时下线或限内网。
