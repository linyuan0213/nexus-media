# NAS-Tools 前端重构计划（v2.0）

## 一、项目背景

### 1.1 旧版前端（web/templates/）
- **技术栈**：Jinja2 模板 + Tabler CSS + jQuery + Lit Web Components
- **页面数量**：约 32 个页面模板
- **图标系统**：`macro/svg.html` 中内嵌 100+ SVG Tabler Icons（已废弃，改用 Lucide）
- **样式系统**：Tabler CSS 框架（`tabler.min.css` / `tabler-vendors.min.css` / `style.css`）
- **交互方式**：jQuery + 原生 JavaScript，ajax_post 调用后端 API
- **组件化**：少量 Lit 自定义组件（`custom-img`、`normal-card`、`plugin-modal` 等）

### 1.2 新版前端（web/frontend/apps/nas-tools/）
- **技术栈**：Vue 3 + Vite + TypeScript + Naive UI + Pinia + Vue Router
- **框架底座**：Vben Admin v5.6.0
- **当前状态**：基础框架已搭建，API 模块已适配后端 FastAPI，但页面内容较简陋
- **图标系统**：Lucide Icons（通过 `@vben/icons`），废弃旧版 Tabler Icons SVG macro
- **图片资源**：已迁移 `web/static/img/*` → `web/frontend/apps/nas-tools/public/static/img/`

### 1.3 后端 API
- FastAPI 路由已全部迁移至 `/api/*`
- 响应格式已统一为 `{code, data, message}`
- 所有读取接口已改为 POST 方法（除 `/api/auth/me`、`/api/rbac/codes` 等个别接口外）

---

## 二、重构目标

1. **视觉还原**：新版页面视觉风格对齐旧版 Tabler 风格（卡片、表格、按钮、颜色、圆角等）
2. **功能对等**：所有旧版页面功能在新版中完整实现，交互体验不低于旧版
3. **图标统一**：全面使用 Lucide Icons，废弃 `macro/svg.html` 中的 Tabler Icons
4. **响应式**：保留旧版的移动端适配能力（底部菜单、折叠卡片等）
5. **交互优化**：保留旧版关键交互（模态框、下拉菜单、消息中心、WebSocket 实时推送）
6. **RBAC 完整**：用户管理、角色管理、菜单管理必须完整实现

---

## 三、旧版模板清单与新版映射

### 3.1 认证与布局
| 旧版模板 | 新版路径 | 优先级 | 状态 |
|---------|---------|--------|------|
| `login.html` | `/login` (Vben 内置) | P0 | ✅ 已有，需换肤 |
| `navigation.html` | `layouts/basic.vue` | P0 | ⚠️ 需重构消息中心/底部菜单 |

### 3.2 核心页面
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `index.html` (媒体库首页) | `/` 或 `/library` | `/api/media/library/*` | P0 |
| `search.html` | `/media/search` | `/api/media/search` | P0 |
| `download/downloading.html` | `/download/downloading` | `/api/download/tasks` | P0 |
| `download/torrent_remove.html` | `/download/downloader` | `/api/download/downloaders` | P1 |

### 3.3 发现/内容
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `discovery/recommend.html` | `/media/discovery` | `/api/media/recommend` | P0 |
| `discovery/ranking.html` | `/media/discovery?type=ranking` | `/api/media/recommend` | P1 |
| `discovery/mediainfo.html` | `/media/detail/:id` | `/api/media/detail` | P1 |
| `discovery/person.html` | `/media/person/:id` | `/api/media/person` | P2 |

### 3.4 RSS 订阅
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `rss/movie_rss.html` | `/rss/movie` | `/api/rss/movie/list` | P0 |
| `rss/tv_rss.html` | `/rss/tv` | `/api/rss/tv/list` | P0 |
| `rss/rss_history.html` | `/rss/history` | `/api/rss/history` | P1 |
| `rss/user_rss.html` | `/rss/user` | `/api/userrss/tasks` | P1 |
| `rss/rss_parser.html` | `/rss/parser` | `/api/userrss/parsers` | P2 |
| `rss/rss_calendar.html` | `/rss/calendar` | `/api/rss/calendar/ical` | P2 |

### 3.5 站点管理
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `site/site.html` (站点列表) | `/site/list` | `/api/site/sites` | P0 |
| `site/sitelist.html` | 合并至 `/site/list` | - | - |
| `site/statistics.html` | `/site/statistics` | `/api/site/sites/statistics` | P1 |
| `site/brushtask.html` | `/brush` | `/api/brush/tasks` | P1 |
| `site/resources.html` | `/site/resources` | `/api/site/sites/resources` | P2 |

### 3.6 设置/系统（高频）
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `setting/basic.html` | `/system/basic` | `/api/system/status` | P0 |
| `setting/downloader.html` | `/download/downloader` | `/api/download/downloaders` | P0 |
| `setting/download_setting.html` | `/download/settings` | `/api/download/settings` | P1 |
| `setting/indexer.html` | `/service/indexer` | `/api/system/indexers/config` | P1 |
| `setting/mediaserver.html` | `/service/mediaserver` | `/api/system/mediaservers/config` | P1 |
| `setting/notification.html` | `/service/notification` | `/api/system/message_clients` | P1 |
| `setting/library.html` | `/system/basic` (合并) | `/api/media/library/*` | P1 |

### 3.7 RBAC 管理（必须完整实现）
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `setting/users.html` (用户管理) | `/system/users` | `/api/rbac/users` | P0 |
| `setting/roles.html` (角色管理) | `/system/roles` | `/api/rbac/roles` | P0 |
| `setting/menus.html` (菜单管理) | `/system/menus` | `/api/rbac/menus` | P0 |

### 3.8 工具/其他
| 旧版模板 | 新版路径 | 后端 API | 优先级 |
|---------|---------|---------|--------|
| `setting/plugin.html` | `/plugin/market` + `/plugin/installed` | `/api/plugin/plugins` | P0 |
| `setting/filterrule.html` | `/filter/rule` | `/api/filter/rules` | P1 |
| `setting/customwords.html` | `/words` | `/api/words/words` | P1 |
| `setting/directorysync.html` | `/sync` | `/api/sync/paths` | P1 |
| `scheduler.html` | `/scheduler/jobs` | `/api/scheduler/jobs` | P1 |
| `rename/history.html` | `/rename/history` | `/api/media/transfer/history` | P2 |
| `rename/mediafile.html` | `/rename/mediafile` | `/api/sync/rename` | P2 |
| `rename/unidentification.html` | `/rename/unidentification` | `/api/media/unknown` | P2 |
| `rename/tmdbblacklist.html` | `/system/basic` (合并) | `/api/system/tmdb_blacklist` | P2 |
| `service.html` | `/service/*` | `/api/system/*` | P2 |

---

## 四、图标迁移方案（Lucide）

### 4.1 原则
- **全面废弃** `macro/svg.html` 中的 Tabler Icons
- **统一使用** Lucide Icons（通过 `@vben/icons` 或 `lucide-vue-next`）
- 建立图标名称映射表，确保旧版图标在新版中有对应

### 4.2 高频图标映射（Tabler → Lucide）
| Tabler 名称 | Lucide 名称 | 用途 |
|------------|------------|------|
| `plus` | `Plus` | 新增按钮 |
| `refresh` | `RefreshCw` | 刷新 |
| `edit` | `Pencil` | 编辑 |
| `x` | `X` | 删除/关闭 |
| `eye` | `Eye` | 查看详情 |
| `dots-vertical` | `MoreVertical` | 更多操作 |
| `trash` | `Trash2` | 删除 |
| `user` | `User` | 用户 |
| `users` | `Users` | 用户组 |
| `home` | `Home` | 首页 |
| `chart-bar` | `BarChart3` | 排行榜 |
| `layout-2` | `LayoutGrid` | 服务 |
| `movie` | `Film` | 电影 |
| `device-tv` | `Tv` | 电视剧 |
| `search` | `Search` | 搜索 |
| `rss` | `Rss` | 订阅 |
| `bell` | `Bell` | 通知 |
| `history` | `History` | 历史 |
| `settings` | `Settings` | 设置 |
| `menu-2` | `Menu` | 菜单 |
| `grip-vertical` | `GripVertical` | 拖动排序 |
| `chevron-right` | `ChevronRight` | 展开 |
| `chevron-down` | `ChevronDown` | 折叠 |
| `activity-heartbeat` | `Activity` | 站点测试 |
| `pie` | `PieChart` | 统计 |
| `apps` | `LayoutGrid` | 应用市场 |
| `bolt` | `Zap` | 立即执行 |
| `alert-triangle` | `AlertTriangle` | 警告 |
| `info-circle` | `Info` | 信息 |
| `check` | `Check` | 成功 |
| `player-play` | `Play` | 播放 |
| `link` | `Link` | 链接 |
| `calendar` | `Calendar` | 日历 |
| `repeat` | `Repeat` | 循环 |
| `calendar-clock` | `CalendarClock` | 定时 |
| `help-circle` | `HelpCircle` | 帮助 |
| `file-info` | `FileText` | 文件信息 |

### 4.3 图标组件封装
```vue
<!-- src/components/icons/Icon.vue -->
<template>
  <component :is="iconComponent" v-bind="$attrs" />
</template>
<script setup lang="ts">
import * as icons from 'lucide-vue-next';
const props = defineProps<{ name: string }>();
const iconComponent = computed(() => (icons as any)[props.name] || icons.Circle);
</script>
```

---

## 五、样式迁移方案

### 5.1 颜色体系（Tabler → Naive UI 主题覆盖）
在 `src/styles/tabler-theme.css` 中定义：
```css
:root {
  --tblr-primary: #206bc4;
  --tblr-primary-rgb: 32, 107, 196;
  --tblr-success: #2fb344;
  --tblr-danger: #d63939;
  --tblr-warning: #f76707;
  --tblr-info: #4299e1;
  --tblr-cyan: #17a2b8;
  --tblr-teal: #0ca678;
  --tblr-lime: #74b816;
  --tblr-orange: #f76707;
  --tblr-purple: #ae3ec9;
  --tblr-pink: #d6336c;
  --tblr-card-border-radius: 4px;
  --tblr-card-border-color: rgba(98, 105, 118, 0.16);
  --tblr-page-header-bg: #f8f9fa;
}
```

### 5.2 公共组件样式类
```css
/* 页面标题栏 */
.page-header {
  @apply mb-4 flex items-center justify-between;
}

/* 页面内容区 */
.page-body {
  @apply py-4;
}

/* 卡片网格 - 媒体卡片 */
.grid-media-card {
  @apply grid gap-3;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
}

/* 卡片网格 - 信息卡片 */
.grid-info-card {
  @apply grid gap-3;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}

/* 卡片网格 - 普通卡片 */
.grid-normal-card {
  @apply grid gap-3;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

/* 模态框背景模糊 */
.modal-blur {
  backdrop-filter: blur(4px);
}
```

### 5.3 Naive UI 主题覆盖
在 `src/styles/naive-theme.ts` 中覆盖：
```ts
export const tablerThemeOverrides = {
  common: {
    primaryColor: '#206bc4',
    primaryColorHover: '#1b5aa0',
    primaryColorPressed: '#164a82',
    borderRadius: '4px',
  },
  Card: {
    borderRadius: '4px',
    borderColor: 'rgba(98, 105, 118, 0.16)',
  },
  Button: {
    borderRadius: '4px',
  },
  Table: {
    borderRadius: '4px',
  },
};
```

---

## 六、组件抽象计划

### 6.1 布局级组件
| 组件名 | 来源 | 用途 | 文件 |
|--------|------|------|------|
| `PageHeader` | `page-header d-print-none` | 页面标题 + 副标题 + 操作按钮 | `components/page/PageHeader.vue` |
| `PageBody` | `page-body` | 内容容器 | `components/page/PageBody.vue` |
| `CardGrid` | `grid-*-card` | 响应式网格容器 | `components/page/CardGrid.vue` |
| `BottomMenuBar` | `main-bottom-menubar` | 移动端底部导航 | `components/layout/BottomMenuBar.vue` |
| `MessageCenter` | `offcanvasEnd` | 消息中心抽屉 | `components/layout/MessageCenter.vue` |
| `ConfirmModal` | `system-confirm-modal` | 危险操作确认 | `components/modal/ConfirmModal.vue` |
| `ProgressModal` | `modal-process` | 进度条弹窗 | `components/modal/ProgressModal.vue` |
| `EmptyState` | `OOPS.empty` | 空状态 | `components/empty/EmptyState.vue` |
| `NoDataState` | `OOPS.nodatafound` | 无数据状态 | `components/empty/NoDataState.vue` |

### 6.2 业务组件
| 组件名 | 来源 | 用途 | 文件 |
|--------|------|------|------|
| `MediaCard` | `normal-card` (Lit) | 媒体海报卡片（海报+标题+年份+评分） | `components/media/MediaCard.vue` |
| `MediaCardSkeleton` | `normal-card-placeholder` | 媒体卡片加载占位 | `components/media/MediaCardSkeleton.vue` |
| `TorrentCard` | `download/downloading.html` | 下载任务卡片（海报+标题+进度+速度） | `components/download/TorrentCard.vue` |
| `SiteCard` | `site/site.html` | 站点信息卡片（图标+名称+标签+操作） | `components/site/SiteCard.vue` |
| `RssCard` | `rss/movie_rss.html` | 订阅条目卡片（海报+标题+进度+状态） | `components/rss/RssCard.vue` |
| `PluginCard` | `setting/plugin.html` | 插件卡片（图标+名称+描述+状态） | `components/plugin/PluginCard.vue` |
| `SchedulerJobRow` | `scheduler.html` | 定时任务表格行 | `components/scheduler/SchedulerJobRow.vue` |
| `UserTableRow` | `setting/users.html` | 用户表格行 | `components/rbac/UserTableRow.vue` |
| `RoleTableRow` | `setting/roles.html` | 角色表格行 | `components/rbac/RoleTableRow.vue` |
| `MenuTree` | `setting/menus.html` | 菜单树（拖动排序） | `components/rbac/MenuTree.vue` |
| `MenuTreeItem` | `setting/menus.html` | 菜单树单项 | `components/rbac/MenuTreeItem.vue` |
| `FilterRuleRow` | `setting/filterrule.html` | 过滤规则行 | `components/filter/FilterRuleRow.vue` |
| `WordGroupCard` | `setting/customwords.html` | 识别词组卡片 | `components/words/WordGroupCard.vue` |
| `SyncTaskRow` | `setting/directorysync.html` | 同步任务行 | `components/sync/SyncTaskRow.vue` |

---

## 七、页面重构详细说明

### 7.1 登录页（`login.html` → `login.vue`）
**旧版特征**：
- 毛玻璃背景（`backdrop-filter: blur(1rem)`）
- 背景图片支持（base64 编码）
- 图片左下角描述卡片
- Tabler 表单样式（`input-icon`、`form-control`）

**新版实现**：
- 复用 Vben `AuthenticationLogin` 组件
- 覆盖样式实现毛玻璃效果
- 保留背景图片 + 图片描述功能
- 对接 `/api/auth/login`（form-data 格式）

### 7.2 媒体库首页（`index.html` → `views/library/index.vue`）
**旧版特征**：
- 页面标题栏 + 操作按钮（同步、统计、播放记录）
- 媒体服务器库列表（卡片网格，`grid-normal-card`）
- 正在观看区域（带进度条）
- 最新入库区域（海报网格，`grid-media-card`）
- 媒体同步模态框（进度条 + 库选择）
- 播放历史模态框

**新版实现**：
- `PageHeader` + 操作按钮组
- `CardGrid` 展示媒体库
- `MediaCard` 展示正在观看/最新入库
- `ProgressModal` 用于同步进度
- 对接 `/api/media/library/*`

### 7.3 正在下载（`download/downloading.html` → `views/download/downloading/index.vue`）
**旧版特征**：
- 页面标题 + "新增下载"下拉菜单（种子文件/种子链接）
- 种子卡片列表（`grid-info-card`）
- 每张卡片：海报、标题、速度、进度条
- 操作菜单：开始、暂停、删除
- 定时刷新（2秒轮询 `/api/download/tasks/info`）

**新版实现**：
- `PageHeader` + `NDropdown` 新增下载
- `TorrentCard` 列表
- `useIntervalFn` 实现定时刷新
- 对接 `/api/download/tasks`、`/api/download/tasks/start`、`/api/download/tasks/stop`、`/api/download/tasks/remove`

### 7.4 搜索页（`search.html` → `views/media/search/index.vue`）
**旧版特征**：
- 搜索输入框 + 过滤条件
- 搜索结果卡片网格
- 点击卡片显示下载模态框

**新版实现**：
- `NInput` + `NSelect` 过滤
- `MediaCard` 网格展示结果
- `NModal` 下载配置弹窗
- 对接 `/api/media/search`

### 7.5 推荐/发现（`discovery/recommend.html` → `views/media/discovery/index.vue`）
**旧版特征**：
- 动态标题 + 副标题
- 过滤下拉菜单
- 无限滚动加载（`grid-media-card`）
- `normal-card` Lit 组件展示媒体
- 占位卡片加载动画

**新版实现**：
- `PageHeader` + `NDropdown` 过滤
- `MediaCard` + `MediaCardSkeleton`
- `useInfiniteScroll` 实现无限滚动
- 对接 `/api/media/recommend`

### 7.6 电影/剧集订阅（`rss/movie_rss.html` / `tv_rss.html`）
**旧版特征**：
- 订阅卡片列表（海报+标题+年份+进度）
- 操作：编辑、删除、搜索、查看历史
- 添加订阅模态框

**新版实现**：
- `RssCard` 列表
- 操作按钮组
- `NModal` 编辑/添加
- 对接 `/api/rss/movie/list`、`/api/rss/tv/list`

### 7.7 站点管理（`site/site.html` → `views/site/list/index.vue`）
**旧版特征**：
- 页面标题 + 新增站点/站点测试按钮
- PT/BT 类型切换 Tab
- 站点卡片（`grid-info-card`）：图标、名称、地址、Cookie、RSS、标签、操作
- 新增/编辑站点模态框（大表单）

**新版实现**：
- `PageHeader` + 按钮组
- `NTabs` 类型切换
- `SiteCard` 列表
- `NModal` + `NForm` 大表单
- 对接 `/api/site/sites`

### 7.8 刷流任务（`site/brushtask.html` → `views/brush/index.vue`）
**旧版特征**：
- 任务卡片/表格
- 状态标签、运行统计
- 添加/编辑任务模态框

**新版实现**：
- `NDataTable` 或卡片列表
- `NTag` 状态
- `NModal` 表单
- 对接 `/api/brush/tasks`

### 7.9 定时任务（`scheduler.html` → `views/scheduler/jobs/index.vue`）
**旧版特征**：
- 表格展示：任务名称、触发器、下次执行、状态、统计、操作
- 触发器类型标签（interval/cron/date）
- 统计进度条（成功/失败比例）
- 编辑模态框：触发器类型切换、间隔时间、Cron、指定时间

**新版实现**：
- `NDataTable` 展示任务
- `NTag` 触发器类型
- `NProgress` 统计条
- `NModal` + `NForm` + 条件渲染表单
- 对接 `/api/scheduler/jobs`、`/api/scheduler/jobs/update`

### 7.10 用户管理（`setting/users.html` → `views/system/users/index.vue`）
**旧版特征**：
- 页面标题 + 新增用户按钮（权限控制）
- 用户表格：头像、昵称、用户名、邮箱、角色标签、状态、最后登录、操作
- 操作：编辑、重置密码、删除（权限控制）
- 新增/编辑用户模态框：用户名、昵称、密码、邮箱、角色多选、状态单选
- 重置密码模态框

**新版实现**：
- `PageHeader` + `NButton`（`v-permission`）
- `NDataTable` 用户列表
- `NAvatar` + `NTag` 角色
- `NModal` + `NForm` + `NCheckboxGroup` 角色选择
- `NModal` 重置密码
- 对接 `/api/rbac/users`

### 7.11 角色管理（`setting/roles.html` → `views/system/roles/index.vue`）
**旧版特征**：
- 页面标题 + 新增角色按钮
- 角色表格：头像、名称、代码、级别、权限数量、用户数量、状态、操作
- 操作：编辑、删除
- 新增/编辑角色模态框（`modal-xl`）：
  - 基本信息：名称、代码、描述、级别、状态
  - 权限配置：按模块分组的多选标签（`form-selectgroup-pills`）
  - 菜单配置：菜单多选卡片

**新版实现**：
- `PageHeader` + `NButton`
- `NDataTable` 角色列表
- `NModal`（大）+ `NTabs`：基本信息 / 权限 / 菜单
- `NCheckboxGroup` 权限多选
- `NCheckboxGroup` 菜单多选
- 对接 `/api/rbac/roles`

### 7.12 菜单管理（`setting/menus.html` → `views/system/menus/index.vue`）
**旧版特征**：
- 左右分栏：左侧菜单树（可拖动排序），右侧详情/编辑
- 菜单树：拖动柄、展开/折叠图标、Lucide 图标、菜单名称、子菜单数量
- 放置区域：拖出成为顶级、拖入成为子菜单、同级排序
- 空状态：选择菜单查看详情
- 新增/编辑模态框：名称、代码、父菜单、路径、Lucide 图标、组件、排序、状态等

**新版实现**：
- `NGrid` 左右分栏（`col-8` + `col-16`）
- `MenuTree` + `MenuTreeItem`（基于 `vue-draggable-plus` 实现拖动）
- 放置区域高亮
- `NCard` 详情/编辑区
- `NModal` 新增/编辑
- 对接 `/api/rbac/menus`、`/api/rbac/menus/sort`

### 7.13 插件中心（`setting/plugin.html` → `views/plugin/*`）
**旧版特征**：
- 已安装插件：卡片网格（`grid-normal-card`），卡片封面+图标+名称+状态
- 插件市场：`modal-xl` 弹窗，卡片网格，显示安装状态+统计
- 插件配置：`plugin-modal` Lit 组件，动态表单
- 插件页面：`modal-lg` 弹窗，动态内容

**新版实现**：
- `PluginCard` 网格
- `NModal`（xl）插件市场
- 动态表单渲染组件（根据 `fields` 配置渲染 `NFormItem`）
- `NModal` 插件页面
- 对接 `/api/plugin/plugins`、`/api/plugin/plugins/apps`

### 7.14 其他设置页面
- **下载器设置** (`setting/downloader.html`)：表单列表，测试连接按钮
- **下载设置** (`setting/download_setting.html`)：表单列表
- **索引器设置** (`setting/indexer.html`)：配置表单
- **媒体服务器** (`setting/mediaserver.html`)：配置表单 + 测试
- **消息通知** (`setting/notification.html`)：消息客户端列表 + 配置
- **过滤规则** (`setting/filterrule.html`)：规则组 + 规则表格
- **识别词** (`setting/customwords.html`)：词组卡片 + 词列表
- **目录同步** (`setting/directorysync.html`)：同步路径表格

---

## 八、执行计划（按迭代）

### Iteration 1：基础设施（1-2 天）
- [x] 迁移图片资源 `web/static/img/*` → `public/static/img/`
- [ ] 创建 `tabler-theme.css` 变量文件
- [ ] 创建 `naive-theme.ts` 主题覆盖
- [ ] 创建 `Icon.vue` Lucide 图标封装
- [ ] 创建 `PageHeader`、`PageBody`、`CardGrid` 布局组件
- [ ] 创建 `EmptyState`、`NoDataState` 空状态组件

### Iteration 2：核心页面 - 媒体/下载/搜索（3-4 天）
- [ ] 重构登录页（毛玻璃背景）
- [ ] 重构媒体库首页（库列表 + 正在观看 + 最新入库）
- [ ] 重构正在下载页（TorrentCard + 定时刷新）
- [ ] 重构搜索页（输入 + 过滤 + 结果网格）
- [ ] 重构推荐/发现页（无限滚动 + MediaCard）

### Iteration 3：订阅/站点（2-3 天）
- [ ] 重构电影/剧集订阅页
- [ ] 重构 RSS 历史/自定义 RSS
- [ ] 重构站点列表页（PT/BT 切换 + 大表单模态框）
- [ ] 重构刷流任务页

### Iteration 4：RBAC 管理（2-3 天）
- [ ] 重构用户管理页（表格 + 模态框 + 重置密码）
- [ ] 重构角色管理页（表格 + 大模态框 + 权限/菜单配置）
- [ ] 重构菜单管理页（拖动树 + 左右分栏 + 模态框）

### Iteration 5：系统/设置（2-3 天）
- [ ] 重构基础设置页
- [ ] 重构下载器/下载设置页
- [ ] 重构索引器/媒体服务器/消息通知页
- [ ] 重构定时任务页（触发器类型切换 + 统计进度条）

### Iteration 6：插件/工具（2 天）
- [ ] 重构插件中心（已安装 + 市场 + 动态配置表单）
- [ ] 重构过滤规则页
- [ ] 重构识别词页
- [ ] 重构目录同步页
- [ ] 重构转移历史/手动识别页

### Iteration 7：布局/交互优化（2 天）
- [ ] 重构消息中心（WebSocket + 抽屉）
- [ ] 重构移动端底部菜单
- [ ] 重构全局进度模态框
- [ ] 全局确认弹窗封装

### Iteration 8：联调/优化（2 天）
- [ ] 全页面 API 联调
- [ ] 移动端响应式测试
- [ ] 消息中心 WebSocket 测试
- [ ] 性能优化（懒加载、虚拟列表）
- [ ] TypeScript 编译检查
- [ ] Vite 生产构建验证

---

## 九、技术细节

### 9.1 API 调用规范
```ts
// 读取数据 - POST + 空对象
const data = await requestClient.post('/api/download/tasks', {});

// 读取数据 - POST + 参数
const data = await requestClient.post('/api/media/recommend', { type, page });

// 写入数据 - POST + payload
await requestClient.post('/api/download/tasks/start', { id });

// 特殊 GET 接口
const codes = await requestClient.get('/api/rbac/codes');
```

### 9.2 WebSocket 消息中心
```ts
// src/composables/useMessageCenter.ts
export function useMessageCenter() {
  const ws = new WebSocket(`ws://${location.host}/message?token=${token}`);
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // 处理消息
  };
}
```

### 9.3 权限指令
```vue
<!-- 按钮级权限控制 -->
<button v-permission="'user:create'">新增用户</button>
<button v-permission="'user:delete'">删除</button>
```

### 9.4 图片加载容错
```vue
<img :src="item.poster || '/static/img/no-image.png'" @error="e => e.target.src = '/static/img/no-image.png'" />
```

---

## 十、风险与对策

| 风险 | 对策 |
|------|------|
| 旧版 jQuery 插件难以迁移 | 用 Vue 原生/Naive UI 组件替代，复杂交互用原生 JS 封装 |
| Tabler CSS 与 Tailwind 冲突 | Tabler 风格用 CSS 变量隔离，避免类名冲突；优先使用 Naive UI 组件 |
| 旧版 Lit 组件行为复杂 | 分析 Lit 组件源码，用 Vue 组件等效实现；特别是 `plugin-modal`、`normal-card` |
| 后端 API 返回字段不一致 | 前端 Store 中统一做字段映射（ snake_case → camelCase ） |
| 页面数量多，工期长 | 按优先级分批交付，核心页面优先（P0 > P1 > P2） |
| 菜单管理拖动排序复杂 | 使用 `vue-draggable-plus` 库实现，参考旧版 `menus.html` 放置区域逻辑 |
| 插件动态表单渲染 | 创建 `DynamicForm.vue` 组件，根据 `fields` 配置自动渲染表单元素 |

---

## 十一、成功标准

1. 所有旧版模板页面在新版中有对应实现（32/32）
2. 新版页面视觉风格与旧版 Tabler 风格一致度 ≥ 90%
3. Lucide 图标全面替换旧版 SVG macro，无图标 404
4. 图片资源（`static/img/*`）正常加载，无 404
5. 核心功能（搜索/下载/订阅/站点/RBAC）API 联调通过
6. RBAC 三件套（用户/角色/菜单）功能完整，包括拖动排序
7. 插件中心支持动态表单配置
8. 移动端底部菜单、消息中心、模态框交互正常
9. Vite 生产构建成功，无 TypeScript 错误
10. 所有接口使用 POST 方法，与后端路由对齐

---

## 十二、附录：旧版模板完整清单

### macro 文件
- `macro/svg.html` - **废弃**，改用 Lucide
- `macro/head.html` - **废弃**，Vite 处理
- `macro/oops.html` - 替换为 `EmptyState`、`NoDataState` 组件
- `macro/form.html` - 替换为 Naive UI Form 组件

### 页面模板（按目录）
```
web/templates/
├── 404.html              → Vben 内置 fallback
├── 500.html              → Vben 内置 fallback
├── index.html            → views/library/index.vue
├── logging.html          → views/system/logs/index.vue
├── login.html            → views/_core/authentication/login.vue
├── navigation.html       → layouts/basic.vue
├── openapp.html          → 暂不支持/简化
├── scheduler.html        → views/scheduler/jobs/index.vue
├── search.html           → views/media/search/index.vue
├── service.html          → views/service/*
├── test.html             → 废弃
├── discovery/
│   ├── mediainfo.html    → views/media/discovery/index.vue (详情)
│   ├── person.html       → views/media/discovery/index.vue (人物)
│   ├── ranking.html      → views/media/discovery/index.vue (排行榜)
│   └── recommend.html    → views/media/discovery/index.vue
├── download/
│   ├── downloading.html  → views/download/downloading/index.vue
│   └── torrent_remove.html → views/download/downloader/index.vue
├── rename/
│   ├── history.html      → views/rename/history/index.vue
│   ├── mediafile.html    → views/rename/mediafile/index.vue
│   ├── tmdbblacklist.html → views/system/basic/index.vue
│   └── unidentification.html → views/rename/unidentification/index.vue
├── rss/
│   ├── movie_rss.html    → views/rss/movie/index.vue
│   ├── rss_calendar.html → views/rss/calendar/index.vue
│   ├── rss_history.html  → views/rss/history/index.vue
│   ├── rss_parser.html   → views/rss/parser/index.vue
│   ├── tv_rss.html       → views/rss/tv/index.vue
│   └── user_rss.html     → views/rss/user/index.vue
├── setting/
│   ├── basic.html        → views/system/basic/index.vue
│   ├── customwords.html  → views/words/index.vue
│   ├── directorysync.html → views/sync/index.vue
│   ├── download_setting.html → views/download/settings/index.vue
│   ├── downloader.html   → views/download/downloader/index.vue
│   ├── filterrule.html   → views/filter/rule/index.vue
│   ├── indexer.html      → views/service/indexer/index.vue
│   ├── library.html      → views/system/basic/index.vue
│   ├── mediaserver.html  → views/service/mediaserver/index.vue
│   ├── menus.html        → views/system/menus/index.vue
│   ├── notification.html → views/service/notification/index.vue
│   ├── plugin.html       → views/plugin/installed/index.vue + market
│   ├── roles.html        → views/system/roles/index.vue
│   └── users.html        → views/system/users/index.vue
└── site/
    ├── brushtask.html    → views/brush/index.vue
    ├── resources.html    → views/site/resources/index.vue
    ├── site.html         → views/site/list/index.vue
    ├── sitelist.html     → 合并至 site/list
    └── statistics.html   → views/site/statistics/index.vue
```

---

**计划制定时间**：2026-04-25
**预估总工期**：约 18-22 个工作日（按迭代执行）
**负责人**：前端重构小组
