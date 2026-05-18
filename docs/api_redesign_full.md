# Nexus Media API 全面重新设计文档

> **版本**: v1.0
> **日期**: 2026-04-24
> **范围**: 全部 14 个路由文件 + RBAC 数据库扩展

---

## 1. 设计原则

1. **统一响应格式**: `{ code: 0, data: ..., message: "" }`
2. **RESTful 路径**: 资源名词 + 动作，如 `/api/media/search`、`/api/download/tasks`
3. **POST 为主**: 查询类用 POST（兼容表单），数据获取用 GET
4. **菜单即路由**: RBAC 菜单表直接存储 Vben Admin 路由元数据
5. **前端不转换**: 后端返回什么，前端直接消费

---

## 2. 数据库变更 (RBAC_MENUS 表扩展)

新增字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `REDIRECT` | String(512) | NULL | 重定向路径 |
| `KEEP_ALIVE` | Integer | 0 | 页面缓存 |
| `AFFIX_TAB` | Integer | 0 | 固定标签页 |
| `HIDE_IN_MENU` | Integer | 0 | 隐藏菜单 |
| `HIDE_IN_TAB` | Integer | 0 | 隐藏标签页 |
| `HIDE_IN_BREADCRUMB` | Integer | 0 | 隐藏面包屑 |
| `ACTIVE_ICON` | String(512) | NULL | 激活图标 |
| `BADGE` | String(64) | NULL | 徽标 |
| `BADGE_TYPE` | String(32) | NULL | 徽标类型 |

---

## 3. 认证模块 (api/routers/auth.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/api/auth/login` | `/api/auth/login` | POST | 保持不变 |
| `/api/auth/refresh` | `/api/auth/refresh` | POST | 保持不变 |
| `/api/auth/logout` | `/api/auth/logout` | POST | 保持不变 |
| `/api/auth/me` | `/api/auth/me` | GET | 保持不变 |

**LoginResponse 格式**:
```json
{
  "code": 0,
  "success": true,
  "message": "登录成功",
  "data": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 900
  }
}
```

---

## 4. RBAC 模块 (api/routers/rbac.py)

### 4.1 用户管理

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/create_user` | `/users/create` | POST | 创建用户 |
| `/delete_user` | `/users/delete` | POST | 删除用户 |
| `/update_user` | `/users/update` | POST | 更新用户 |
| `/get_user` | `/users/detail` | POST | 用户详情 |
| `/get_users` | `/users` | POST | 用户列表 |
| `/reset_password` | `/users/reset_password` | POST | 重置密码 |

### 4.2 角色管理

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/create_role` | `/roles/create` | POST | 创建角色 |
| `/delete_role` | `/roles/delete` | POST | 删除角色 |
| `/update_role` | `/roles/update` | POST | 更新角色 |
| `/get_role` | `/roles/detail` | POST | 角色详情 |
| (无) | `/roles` | POST | 角色列表（新增） |

### 4.3 菜单管理

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/create_menu` | `/menus/create` | POST | 创建菜单 |
| `/delete_menu` | `/menus/delete` | POST | 删除菜单 |
| `/update_menu` | `/menus/update` | POST | 更新菜单 |
| `/update_menu_sort` | `/menus/sort` | POST | 排序 |
| `/get_menu` | `/menus/detail` | POST | 菜单详情 |
| `/get_user_menus` | `/menus` | POST | 当前用户菜单树 |
| `/get_top_menus` | `/menus/top` | POST | 顶部菜单 |

**菜单响应格式 (直接对接 Vben)**:
```json
{
  "code": 0,
  "data": [
    {
      "path": "media",
      "name": "Media",
      "component": "BasicLayout",
      "meta": { "title": "媒体库", "icon": "lucide:film", "order": 1 },
      "children": [
        {
          "path": "search",
          "name": "MediaSearch",
          "component": "/media/search/index.vue",
          "meta": { "title": "媒体搜索", "icon": "lucide:search" }
        }
      ]
    }
  ]
}
```

### 4.4 权限码

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/codes` | `/codes` | GET | 当前用户权限码列表 |

---

## 5. 系统设置 (api/routers/system.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/version` | `/status` | GET | 系统状态（含版本） |
| `/processes` | `/processes` | POST | 进程列表 |
| `/restart` | `/restart` | POST | 重启系统 |
| `/set_system_config` | `/config` | POST | 设置系统配置 |
| `/update_config` | `/config/update` | POST | 更新配置 |
| `/net_test` | `/net_test` | POST | 网络测试 |
| `/sch` | `/scheduler/run` | POST | 执行定时任务 |
| `/search` | `/search` | POST | 搜索触发 |
| `/refresh_process` | `/refresh` | POST | 刷新进程 |
| `/get_message_client` | `/message_clients` | POST | 消息客户端列表 |
| `/update_message_client` | `/message_clients/update` | POST | 更新消息客户端 |
| `/delete_message_client` | `/message_clients/delete` | POST | 删除消息客户端 |
| `/test_message_client` | `/message_clients/test` | POST | 测试消息客户端 |
| `/send_custom_message` | `/messages/send` | POST | 发送自定义消息 |
| `/send_plugin_message` | `/messages/send_plugin` | POST | 发送插件消息 |
| `/save_indexer_config` | `/indexers/config` | POST | 保存索引器配置 |
| `/save_mediaserver_config` | `/mediaservers/config` | POST | 保存媒体服务器配置 |
| `/add_tmdb_blacklist` | `/tmdb_blacklist/add` | POST | 添加黑名单 |
| `/delete_tmdb_blacklist` | `/tmdb_blacklist/delete` | POST | 删除黑名单 |
| `/clear_tmdb_blacklist` | `/tmdb_blacklist/clear` | POST | 清空黑名单 |
| `/restory_backup` | `/backup/restore` | POST | 恢复备份 |
| `/reset_db_version` | `/db/reset_version` | POST | 重置数据库版本 |
| `/user_manager` | `/users/legacy` | POST | 旧用户管理（废弃） |
| `/logout` | (删除) | - | 统一使用 `/api/auth/logout` |

---

## 6. 站点管理 (api/routers/site.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_sites` | `/sites` | POST | 站点列表 |
| `/get_site` | `/sites/detail` | POST | 站点详情 |
| `/update_site` | `/sites/update` | POST | 更新站点 |
| `/del_site` | `/sites/delete` | POST | 删除站点 |
| `/test_site` | `/sites/test` | POST | 测试站点 |
| `/check_site_attr` | `/sites/check_attr` | POST | 检查站点属性 |
| `/set_site_captcha_code` | `/sites/captcha` | POST | 设置验证码 |
| `/update_site_cookie_ua` | `/sites/cookie_ua` | POST | 更新 Cookie/UA |
| `/get_site_favicon` | `/sites/favicon` | POST | 获取站点图标 |
| `/get_site_history` | `/sites/history` | POST | 站点历史 |
| `/get_site_user_statistics` | `/sites/statistics` | POST | 站点统计 |
| `/get_site_activity` | `/sites/activity` | POST | 站点活动 |
| `/get_site_seeding_info` | `/sites/seeding` | POST | 站点做种信息 |
| `/list_site_resources` | `/sites/resources` | POST | 站点资源列表 |

---

## 7. 下载管理 (api/routers/download.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_downloaders` | `/downloaders` | POST | 下载器列表 |
| `/update_downloader` | `/downloaders/update` | POST | 更新下载器 |
| `/del_downloader` | `/downloaders/delete` | POST | 删除下载器 |
| `/check_downloader` | `/downloaders/check` | POST | 检查下载器 |
| `/test_downloader` | `/downloaders/test` | POST | 测试下载器 |
| `/get_downloading` | `/tasks` | POST | 正在下载任务 |
| `/get_download_dirs` | `/downloaders/dirs` | POST | 下载目录 |
| `/get_download_setting` | `/settings` | POST | 下载设置 |
| `/update_download_setting` | `/settings/update` | POST | 更新下载设置 |
| `/delete_download_setting` | `/settings/delete` | POST | 删除下载设置 |
| `/download` | `/tasks/add` | POST | 添加下载 |
| `/download_link` | `/tasks/add_link` | POST | 添加链接下载 |
| `/download_torrent` | `/tasks/add_torrent` | POST | 添加种子下载 |
| `/pt_info` | `/tasks/info` | POST | PT 信息 |
| `/pt_remove` | `/tasks/remove` | POST | PT 删除 |
| `/pt_start` | `/tasks/start` | POST | PT 开始 |
| `/pt_stop` | `/tasks/stop` | POST | PT 停止 |
| `/auto_remove_torrents` | `/tasks/auto_remove` | POST | 自动清理 |
| `/get_remove_torrents` | `/tasks/remove_candidates` | POST | 可清理任务 |
| `/get_torrent_remove_task` | `/tasks/remove_tasks` | POST | 清理任务列表 |
| `/update_torrent_remove_task` | `/tasks/remove_tasks/update` | POST | 更新清理任务 |
| `/delete_torrent_remove_task` | `/tasks/remove_tasks/delete` | POST | 删除清理任务 |
| `/find_hardlinks` | `/tools/hardlinks` | POST | 查找硬链接 |
| `/truncate_blacklist` | `/tools/blacklist/clear` | POST | 清空黑名单 |
| `/get_indexers` | `/indexers` | POST | 索引器列表 |
| `/get_indexer_statistics` | `/indexers/statistics` | POST | 索引器统计 |

---

## 8. 媒体库 (api/routers/media.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/search_media_infos` | `/search` | POST | 媒体搜索 |
| `/media_detail` | `/detail` | POST | 媒体详情 |
| `/get_library_mediacount` | `/library/count` | POST | 库数量统计 |
| `/get_library_playhistory` | `/library/history` | POST | 播放历史 |
| `/get_library_spacesize` | `/library/space` | POST | 空间占用 |
| `/get_downloaded` | `/library/downloaded` | POST | 已下载 |
| `/get_transfer_history` | `/transfer/history` | POST | 转移历史 |
| `/get_transfer_statistics` | `/transfer/statistics` | POST | 转移统计 |
| `/get_unknown_list` | `/unknown` | POST | 未识别列表 |
| `/get_unknown_list_by_page` | `/unknown/paged` | POST | 未识别列表(分页) |
| `/unidentification` | `/unknown/list` | POST | 未识别(旧) |
| `/get_recommend` | `/recommend` | POST | 推荐 |
| `/media_recommendations` | `/recommendations` | POST | 相关推荐 |
| `/media_similar` | `/similar` | POST | 相似媒体 |
| `/get_season_episodes` | `/season/episodes` | POST | 剧集列表 |
| `/get_tvseason_list` | `/season/list` | POST | 季列表 |
| `/movie_calendar_data` | `/calendar/movie` | POST | 电影日历 |
| `/tv_calendar_data` | `/calendar/tv` | POST | 剧集日历 |
| `/get_ical_events` | `/calendar/ical` | POST | iCal 事件 |
| `/media_person` | `/person` | POST | 影人详情 |
| `/person_medias` | `/person/medias` | POST | 影人作品 |
| `/media_info` | `/info` | POST | 媒体信息 |
| `/name_test` | `/name_test` | POST | 名称测试 |
| `/mediasync_state` | `/sync/state` | POST | 同步状态 |
| `/start_mediasync` | `/sync/start` | POST | 开始同步 |
| `/media_path_scrap` | `/scrap` | POST | 刮削路径 |
| `/save_user_script` | `/script/save` | POST | 保存脚本 |
| `/get_category_config` | `/category/config` | POST | 分类配置 |
| `/update_category_config` | `/category/config/update` | POST | 更新分类配置 |
| `/download_subtitle` | `/subtitle/download` | POST | 下载字幕 |
| `/clear_history` | `/history/clear` | POST | 清空历史 |

---

## 9. RSS 订阅 (api/routers/rss.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_movie_rss_list` | `/movie/list` | POST | 电影订阅列表 |
| `/get_movie_rss_items` | `/movie/items` | POST | 电影订阅项 |
| `/get_tv_rss_list` | `/tv/list` | POST | 剧集订阅列表 |
| `/get_tv_rss_items` | `/tv/items` | POST | 剧集订阅项 |
| `/add_rss_media` | `/add` | POST | 添加订阅 |
| `/remove_rss_media` | `/remove` | POST | 移除订阅 |
| `/rss_detail` | `/detail` | POST | 订阅详情 |
| `/get_rss_history` | `/history` | POST | 订阅历史 |
| `/delete_rss_history` | `/history/delete` | POST | 删除历史 |
| `/re_rss_history` | `/history/redo` | POST | 重新订阅 |
| `/truncate_rsshistory` | `/history/clear` | POST | 清空历史 |
| `/refresh_rss` | `/refresh` | POST | 刷新 RSS |
| `/get_default_rss_setting` | `/default_setting` | POST | 默认设置 |

---

## 10. 自定义 RSS (api/routers/userrss.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/list_rss_tasks` | `/tasks` | POST | 任务列表 |
| `/get_userrss_task` | `/tasks/detail` | POST | 任务详情 |
| `/update_userrss_task` | `/tasks/update` | POST | 更新任务 |
| `/delete_userrss_task` | `/tasks/delete` | POST | 删除任务 |
| `/check_userrss_task` | `/tasks/check` | POST | 检查任务 |
| `/run_userrss` | `/tasks/run` | POST | 执行任务 |
| `/list_rss_parsers` | `/parsers` | POST | 解析器列表 |
| `/get_rssparser` | `/parsers/detail` | POST | 解析器详情 |
| `/update_rssparser` | `/parsers/update` | POST | 更新解析器 |
| `/delete_rssparser` | `/parsers/delete` | POST | 删除解析器 |
| `/list_rss_articles` | `/articles` | POST | 文章列表 |
| `/list_rss_history` | `/articles/history` | POST | 文章历史 |
| `/rss_article_test` | `/articles/test` | POST | 测试文章 |
| `/rss_articles_check` | `/articles/check` | POST | 检查文章 |
| `/rss_articles_download` | `/articles/download` | POST | 下载文章 |

---

## 11. 定时任务 (api/routers/scheduler.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_scheduler_jobs` | `/jobs` | POST | 任务列表 |
| `/run_scheduler_job` | `/jobs/run` | POST | 立即执行 |
| `/pause_scheduler_job` | `/jobs/pause` | POST | 暂停任务 |
| `/resume_scheduler_job` | `/jobs/resume` | POST | 恢复任务 |
| `/delete_scheduler_job` | `/jobs/delete` | POST | 删除任务 |
| `/update_scheduler_job` | `/jobs/update` | POST | 更新任务 |

---

## 12. 刷流任务 (api/routers/brush.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/list_brushtasks` | `/tasks` | POST | 刷流任务列表 |
| `/add_brushtask` | `/tasks/add` | POST | 添加刷流任务 |
| `/brushtask_detail` | `/tasks/detail` | POST | 刷流任务详情 |
| `/del_brushtask` | `/tasks/delete` | POST | 删除刷流任务 |
| `/list_brushtask_torrents` | `/tasks/torrents` | POST | 刷流种子列表 |
| `/run_brushtask` | `/tasks/run` | POST | 执行刷流任务 |
| `/update_brushtask_state` | `/tasks/state` | POST | 更新刷流状态 |

---

## 13. 过滤规则 (api/routers/filter.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_filterrules` | `/rules` | POST | 规则列表 |
| `/add_filtergroup` | `/groups/add` | POST | 添加规则组 |
| `/del_filtergroup` | `/groups/delete` | POST | 删除规则组 |
| `/import_filtergroup` | `/groups/import` | POST | 导入规则组 |
| `/restore_filtergroup` | `/groups/restore` | POST | 恢复规则组 |
| `/share_filtergroup` | `/groups/share` | POST | 分享规则组 |
| `/set_default_filtergroup` | `/groups/default` | POST | 设置默认组 |
| `/add_filterrule` | `/rules/add` | POST | 添加规则 |
| `/del_filterrule` | `/rules/delete` | POST | 删除规则 |
| `/filterrule_detail` | `/rules/detail` | POST | 规则详情 |
| `/rule_test` | `/rules/test` | POST | 测试规则 |

---

## 14. 识别词 (api/routers/words.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_customwords` | `/words` | POST | 识别词列表 |
| `/get_custom_word` | `/words/detail` | POST | 识别词详情 |
| `/add_custom_word_group` | `/groups/add` | POST | 添加词组 |
| `/delete_custom_word_group` | `/groups/delete` | POST | 删除词组 |
| `/add_or_edit_custom_word` | `/words/save` | POST | 保存识别词 |
| `/delete_custom_words` | `/words/delete` | POST | 删除识别词 |
| `/get_categories` | `/categories` | POST | 分类列表 |
| `/export_custom_words` | `/words/export` | POST | 导出识别词 |
| `/import_custom_words` | `/words/import` | POST | 导入识别词 |
| `/analyse_import_custom_words_code` | `/words/analyse` | POST | 分析识别词代码 |
| `/check_custom_words` | `/words/check` | POST | 检查识别词 |

---

## 15. 目录同步 (api/routers/sync.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_sync_path` | `/paths` | POST | 同步路径列表 |
| `/add_or_edit_sync_path` | `/paths/save` | POST | 保存同步路径 |
| `/delete_sync_path` | `/paths/delete` | POST | 删除同步路径 |
| `/check_sync_path` | `/paths/check` | POST | 检查同步路径 |
| `/run_directory_sync` | `/run` | POST | 执行同步 |
| `/get_sub_path` | `/paths/sub` | POST | 获取子路径 |
| `/test_connection` | `/paths/test_connection` | POST | 测试连接 |
| `/update_directory` | `/directories/update` | POST | 更新目录 |
| `/delete_history` | `/history/delete` | POST | 删除历史 |
| `/re_identification` | `/reidentify` | POST | 重新识别 |
| `/del_unknown_path` | `/unknown/delete` | POST | 删除未知路径 |
| `/delete_files` | `/files/delete` | POST | 删除文件 |
| `/rename` | `/rename` | POST | 重命名 |
| `/rename_file` | `/rename/file` | POST | 重命名文件 |
| `/rename_udf` | `/rename/udf` | POST | 自定义重命名 |

---

## 16. 插件中心 (api/routers/plugin.py)

| 旧路径 | 新路径 | 方法 | 说明 |
|--------|--------|------|------|
| `/get_plugins_conf` | `/plugins` | POST | 插件配置列表 |
| `/get_plugin_state` | `/plugins/state` | POST | 插件状态 |
| `/get_plugin_page` | `/plugins/page` | POST | 插件页面 |
| `/get_plugin_apps` | `/plugins/apps` | POST | 插件应用 |
| `/update_plugin_config` | `/plugins/config` | POST | 更新插件配置 |
| `/install_plugin` | `/plugins/install` | POST | 安装插件 |
| `/uninstall_plugin` | `/plugins/uninstall` | POST | 卸载插件 |
| `/run_plugin_method` | `/plugins/method` | POST | 运行插件方法 |

---

## 17. 图片代理 (api/routers/image.py)

保持不变：
- `GET /img/tmdb/{size}/{img_path}`
- `GET /img/douban/{img_path}`
- `GET /img/bgm/{img_path}`
- `GET /img/library/{img_url}`
- `GET /img` (健康检查)

---

## 18. 前端 API 封装目录结构

```
src/api/
├── core/
│   ├── auth.ts      # /api/auth/*
│   ├── menu.ts      # /api/rbac/menus
│   └── user.ts      # /api/auth/me
├── modules/
│   ├── system.ts    # /api/system/*
│   ├── media.ts     # /api/media/*
│   ├── download.ts  # /api/download/*
│   ├── site.ts      # /api/site/*
│   ├── rss.ts       # /api/rss/*
│   ├── userrss.ts   # /api/userrss/*
│   ├── scheduler.ts # /api/scheduler/*
│   ├── brush.ts     # /api/brush/*
│   ├── filter.ts    # /api/filter/*
│   ├── words.ts     # /api/words/*
│   ├── sync.ts      # /api/sync/*
│   ├── plugin.ts    # /api/plugin/*
│   └── rbac.ts      # /api/rbac/*
├── request.ts       # RequestClient 封装
└── index.ts         # 统一导出
```

---

## 19. 实施步骤

1. **Step 1**: 数据库迁移（RBAC_MENUS 扩展字段）
2. **Step 2**: 重写 `api/routers/rbac.py`（菜单树直接输出 Vben 格式）
3. **Step 3**: 重写 `app/services/rbac_init.py`（初始化数据更新）
4. **Step 4**: 依次改造其他 13 个路由文件
5. **Step 5**: 同步更新前端 API 封装层
6. **Step 6**: 同步更新前端路由配置
7. **Step 7**: 测试验证
