# Nexus Media WebAction 层重构设计文档

## 1. 设计目标

1. **彻底废弃 Mixin 组合模式**：当前 `web/actions/` 下的 12 个 Mixin 通过多重继承拼成一个拥有 200+ 命令映射的巨型类 `WebAction`，导致类职责混乱、单测困难、命名冲突风险高。  
2. **以 Flask Blueprint 替代 `_actions` 字典**：所有 Web 命令通过 Blueprint Route 直接暴露，消除运行时的字符串分发。  
3. **保持接口语义不变**：URL 与参数可以重新设计，但业务逻辑代码原封迁移（不改动 `app/` 业务层）。  
4. **前端 `ajax_post` 平滑迁移**：通过一层 CMD → URL 映射表，让现有 200+ 前端调用点无需一次性全改。  
5. **安全认证体系保留并下沉到 Blueprint 层**：继续使用 `flask_login` 的 `@login_required`，并将 `action_login_check` 改造为装饰器下沉到 `web/core/decorators.py`，所有 Controller 路由统一挂载。  
6. **零兼容旧代码**：允许直接删除 `web/actions/` 目录及其 Mixin 文件。

---

## 2. 新目录结构

```text
web/
├── action.py                 # 入口类新形态：仅保留生命周期管理与通用工具
├── main.py                   # Flask App 本体（修改注册逻辑）
├── apiv1.py                  # 现有 REST API（修改调用方式）
├── core/
│   ├── __init__.py
│   ├── response.py           # 统一响应封装（已存在，扩展）
│   └── decorators.py         # 新增：登录校验、RBAC权限、统一响应、异常处理装饰器
├── controllers/              # 新增：按业务域拆分的 Blueprint 控制器
│   ├── __init__.py           # 统一注册所有 Blueprint
│   ├── system.py             # 系统设置、版本、重启、配置、消息客户端、TMDb 黑名单
│   ├── media.py              # 媒体详情、搜索、推荐、日历、库统计
│   ├── site.py               # 站点 CRUD、站点统计、站点资源、图标
│   ├── download.py           # 下载任务、下载器、下载设置、自动删种
│   ├── rss.py                # 电影/电视剧订阅、订阅历史、日历
│   ├── userrss.py            # 自定义 RSS 任务、解析器、文章预览/下载
│   ├── filter.py             # 过滤规则组、规则管理
│   ├── words.py              # 自定义识别词、词组、分类
│   ├── brush.py              # 刷流任务
│   ├── sync.py               # 目录同步、文件整理、历史记录、未识别
│   ├── plugin.py             # 插件安装/卸载/配置/页面
│   ├── rbac.py               # 用户、角色、菜单（RBAC）
│   └── scheduler.py          # 调度任务管理
└── static/js/
    ├── util.js               # ajax_post 适配新路由
    └── functions.js          # 部分页面可逐步改用新 URL
```

### 2.1 目录职责边界

| 目录/文件 | 职责 |
|-----------|------|
| `web/controllers/` | **唯一**暴露 HTTP 接口的层。每个模块对应一个业务域，内部定义一个 Flask Blueprint。禁止直接引入 `app/` 层业务对象以外的重型依赖。 |
| `web/core/` | 基础设施：统一响应体构造、全局异常捕获装饰器、请求参数解析辅助函数、**登录校验与 RBAC 权限装饰器**。 |
| `web/action.py` | **不再是控制器**。仅作为 Flask 应用的生命周期入口（`start_service` / `stop_service` / `restart_server`）与少量被模板过滤器复用的静态工具方法容器。 |
| `web/main.py` | 负责创建 `Flask(__name__)`、注册 Blueprint（来自 `web/controllers/__init__.py`）、页面路由、`/do` 兼容中转路由（过渡期内保留或一次性替换）。 |

---

## 3. 安全认证设计

### 3.1 认证机制保留

- 继续使用 **`flask_login`** 作为 Session 认证基础。
- 继续使用现有的 **`web/backend/user.py`** 中的 `User` 模型与 `LoginManager`。
- 继续使用 **`web/security.py`** 中的 `require_auth`（用于 API Key / Token 认证，如 Webhook、apiv1 等）。

### 3.2 `action_login_check` 装饰器下沉

原 `web/main.py` 中定义的 `action_login_check` 将迁移至 **`web/core/decorators.py`**，供所有 Blueprint 统一使用：

```python
# web/core/decorators.py
from functools import wraps
from flask_login import current_user
from web.core.response import fail

def action_login_check(func):
    """
    替代 web/main.py 中的 action_login_check。
    校验用户是否已登录；未登录返回统一 JSON 失败响应。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return fail(code=-1, msg="用户未登录")
        return func(*args, **kwargs)
    return wrapper
```

### 3.3 Blueprint 路由认证挂载方式

所有 Web 前端 AJAX 接口统一挂载 `@action_login_check`；不需要认证的接口（如 `/api/web/system/net_test` 若未来需要开放，或 Webhook 路由）则不挂载。

**示例**：

```python
# web/controllers/system.py
from flask import Blueprint
from web.core.decorators import action_login_check, parse_json_data
from web.core.response import success

system_bp = Blueprint("system", __name__, url_prefix="/api/web/system")

@system_bp.route('/restart', methods=['POST'])
@action_login_check
@parse_json_data
def restart(data):
    WebAction.restart_server()
    return success()
```

### 3.4 RBAC 权限控制

- `web/controllers/rbac.py` 负责暴露 **RBAC 管理接口**（用户 CRUD、角色 CRUD、菜单 CRUD）。
- 这些管理接口本身也挂载 `@action_login_check`。
- 更细粒度的按钮级/菜单级权限由前端根据 `current_user.get_usermenus()` 与角色配置控制，保持现有逻辑不变。
- `apiv1.py` 中的 `ClientResource` 继续使用 `login_required`（Session），`ApiResource` 继续使用 `require_auth`（Token/API Key）。

### 3.5 API 安全（apiv1）

- `web/apiv1.py` 不经过 `WebAction().api_action()` 二次分发后，**认证装饰器仍需显式挂载在每个 Resource 上**。
- 方案：将现有 `ClientResource` / `ApiResource` 基类的 `method_decorators` 保持不变，直接调用新的 Controller 函数体即可。

---

## 4. 12 个 Mixin → Controller 拆分方案

每个 Controller 一个 Blueprint，前缀统一为 `/api/web`，URL 采用 `/{domain}/{action}` 风格（RPC 风格，便于前端迁移）。

### 4.1 映射总览

| 原 Mixin | 新 Controller | Blueprint 名称 | URL 前缀 |
|----------|---------------|----------------|----------|
| `_system` | `system.py` | `system_bp` | `/api/web/system` |
| `_media` | `media.py` | `media_bp` | `/api/web/media` |
| `_site` | `site.py` | `site_bp` | `/api/web/site` |
| `_download` | `download.py` | `download_bp` | `/api/web/download` |
| `_rss` | `rss.py` | `rss_bp` | `/api/web/rss` |
| `_userrss` | `userrss.py` | `userrss_bp` | `/api/web/userrss` |
| `_filter` | `filter.py` | `filter_bp` | `/api/web/filter` |
| `_words` | `words.py` | `words_bp` | `/api/web/words` |
| `_brush` | `brush.py` | `brush_bp` | `/api/web/brush` |
| `_sync` | `sync.py` | `sync_bp` | `/api/web/sync` |
| `_plugin` | `plugin.py` | `plugin_bp` | `/api/web/plugin` |
| `_rbac` | `rbac.py` | `rbac_bp` | `/api/web/rbac` |
| `_scheduler` | `scheduler.py` | `scheduler_bp` | `/api/web/scheduler` |

### 4.2 各 Controller 路由设计（关键接口）

#### system
```python
# 配置
@system_bp.route('/config/update', methods=['POST'])
@system_bp.route('/config/all', methods=['POST'])
@system_bp.route('/directory', methods=['POST'])
@system_bp.route('/set', methods=['POST'])

# 服务生命周期
@system_bp.route('/restart', methods=['POST'])
@system_bp.route('/update', methods=['POST'])
@system_bp.route('/logout', methods=['POST'])

# 消息客户端
@system_bp.route('/message_client/update', methods=['POST'])
@system_bp.route('/message_client/delete', methods=['POST'])
@system_bp.route('/message_client/check', methods=['POST'])
@system_bp.route('/message_client/get', methods=['POST'])
@system_bp.route('/message_client/test', methods=['POST'])

# 其他
@system_bp.route('/version', methods=['POST'])
@system_bp.route('/progress', methods=['POST'])
@system_bp.route('/net_test', methods=['POST'])
@system_bp.route('/sch', methods=['POST'])
@system_bp.route('/tmdb_blacklist/add', methods=['POST'])
@system_bp.route('/tmdb_blacklist/delete', methods=['POST'])
@system_bp.route('/tmdb_blacklist/clear', methods=['POST'])
```

#### media
```python
@media_bp.route('/detail', methods=['POST'])
@media_bp.route('/info', methods=['POST'])
@media_bp.route('/search', methods=['POST'])          # 原 search_media_infos
@media_bp.route('/similar', methods=['POST'])
@media_bp.route('/recommendations', methods=['POST'])
@media_bp.route('/person', methods=['POST'])
@media_bp.route('/person_medias', methods=['POST'])
@media_bp.route('/tv_seasons', methods=['POST'])
@media_bp.route('/season_episodes', methods=['POST'])
@media_bp.route('/calendar/movie', methods=['POST'])
@media_bp.route('/calendar/tv', methods=['POST'])
@media_bp.route('/recommend', methods=['POST'])
@media_bp.route('/downloaded', methods=['POST'])
@media_bp.route('/search_result', methods=['POST'])
@media_bp.route('/library/count', methods=['POST'])
@media_bp.route('/library/playhistory', methods=['POST'])
@media_bp.route('/library/space', methods=['POST'])
@media_bp.route('/transfer/statistics', methods=['POST'])
@media_bp.route('/subtitle/download', methods=['POST'])
@media_bp.route('/path_scrap', methods=['POST'])
```

#### site
```python
@site_bp.route('/update', methods=['POST'])
@site_bp.route('/info', methods=['POST'])
@site_bp.route('/list', methods=['POST'])
@site_bp.route('/delete', methods=['POST'])
@site_bp.route('/test', methods=['POST'])
@site_bp.route('/favicon', methods=['POST'])
@site_bp.route('/cookie_ua', methods=['POST'])
@site_bp.route('/captcha', methods=['POST'])
@site_bp.route('/check_attr', methods=['POST'])
@site_bp.route('/statistics/user', methods=['POST'])
@site_bp.route('/statistics/activity', methods=['POST'])
@site_bp.route('/statistics/history', methods=['POST'])
@site_bp.route('/statistics/seedinfo', methods=['POST'])
@site_bp.route('/resources', methods=['POST'])
```

#### download
```python
@download_bp.route('/search', methods=['POST'])      # 原 download
@download_bp.route('/link', methods=['POST'])
@download_bp.route('/torrent', methods=['POST'])
@download_bp.route('/start', methods=['POST'])
@download_bp.route('/stop', methods=['POST'])
@download_bp.route('/remove', methods=['POST'])
@download_bp.route('/info', methods=['POST'])
@download_bp.route('/history', methods=['POST'])     # get_downloaded
@download_bp.route('/now', methods=['POST'])         # get_downloading
@download_bp.route('/setting/get', methods=['POST'])
@download_bp.route('/setting/update', methods=['POST'])
@download_bp.route('/setting/delete', methods=['POST'])
@download_bp.route('/dirs', methods=['POST'])
@download_bp.route('/client/update', methods=['POST'])
@download_bp.route('/client/delete', methods=['POST'])
@download_bp.route('/client/list', methods=['POST'])
@download_bp.route('/client/check', methods=['POST'])
@download_bp.route('/client/test', methods=['POST'])
@download_bp.route('/indexers', methods=['POST'])
@download_bp.route('/indexer_statistics', methods=['POST'])
@download_bp.route('/hardlinks', methods=['POST'])
```

#### rss（订阅）
```python
@rss_bp.route('/movie/list', methods=['POST'])
@rss_bp.route('/tv/list', methods=['POST'])
@rss_bp.route('/history', methods=['POST'])
@rss_bp.route('/default_setting', methods=['POST'])
@rss_bp.route('/movie/items', methods=['POST'])
@rss_bp.route('/tv/items', methods=['POST'])
@rss_bp.route('/ical', methods=['POST'])
@rss_bp.route('/add', methods=['POST'])
@rss_bp.route('/remove', methods=['POST'])
@rss_bp.route('/refresh', methods=['POST'])
@rss_bp.route('/detail', methods=['POST'])
@rss_bp.route('/history/delete', methods=['POST'])
@rss_bp.route('/history/redo', methods=['POST'])
@rss_bp.route('/cache/clear', methods=['POST'])
```

#### userrss（自定义订阅）
```python
@userrss_bp.route('/task/get', methods=['POST'])
@userrss_bp.route('/task/delete', methods=['POST'])
@userrss_bp.route('/task/update', methods=['POST'])
@userrss_bp.route('/task/check', methods=['POST'])
@userrss_bp.route('/parser/get', methods=['POST'])
@userrss_bp.route('/parser/delete', methods=['POST'])
@userrss_bp.route('/parser/update', methods=['POST'])
@userrss_bp.route('/run', methods=['POST'])
@userrss_bp.route('/articles', methods=['POST'])
@userrss_bp.route('/article_test', methods=['POST'])
@userrss_bp.route('/history', methods=['POST'])
@userrss_bp.route('/articles_check', methods=['POST'])
@userrss_bp.route('/articles_download', methods=['POST'])
```

#### filter
```python
@filter_bp.route('/rules', methods=['POST'])
@filter_bp.route('/group/add', methods=['POST'])
@filter_bp.route('/group/restore', methods=['POST'])
@filter_bp.route('/group/default', methods=['POST'])
@filter_bp.route('/group/delete', methods=['POST'])
@filter_bp.route('/rule/add', methods=['POST'])
@filter_bp.route('/rule/delete', methods=['POST'])
@filter_bp.route('/rule/detail', methods=['POST'])
@filter_bp.route('/rule/share', methods=['POST'])
@filter_bp.route('/rule/import', methods=['POST'])
@filter_bp.route('/test', methods=['POST'])
```

#### words
```python
@words_bp.route('/list', methods=['POST'])
@words_bp.route('/categories', methods=['POST'])
@words_bp.route('/group/add', methods=['POST'])
@words_bp.route('/group/delete', methods=['POST'])
@words_bp.route('/word/update', methods=['POST'])
@words_bp.route('/word/get', methods=['POST'])
@words_bp.route('/word/delete', methods=['POST'])
@words_bp.route('/word/check', methods=['POST'])
@words_bp.route('/word/export', methods=['POST'])
@words_bp.route('/word/analyse', methods=['POST'])
@words_bp.route('/word/import', methods=['POST'])
```

#### brush
```python
@brush_bp.route('/add', methods=['POST'])
@brush_bp.route('/delete', methods=['POST'])
@brush_bp.route('/detail', methods=['POST'])
@brush_bp.route('/state', methods=['POST'])
@brush_bp.route('/run', methods=['POST'])
@brush_bp.route('/torrents', methods=['POST'])
```

#### sync（含原文件整理/历史/未识别）
```python
@sync_bp.route('/path/add', methods=['POST'])
@sync_bp.route('/path/get', methods=['POST'])
@sync_bp.route('/path/delete', methods=['POST'])
@sync_bp.route('/path/check', methods=['POST'])
@sync_bp.route('/run', methods=['POST'])
@sync_bp.route('/directory/update', methods=['POST'])
@sync_bp.route('/rename', methods=['POST'])
@sync_bp.route('/rename_udf', methods=['POST'])
@sync_bp.route('/re_identification', methods=['POST'])
@sync_bp.route('/history/delete', methods=['POST'])
@sync_bp.route('/history/clear', methods=['POST'])
@sync_bp.route('/unknown/list', methods=['POST'])
@sync_bp.route('/unknown/list_page', methods=['POST'])
@sync_bp.route('/unknown/delete', methods=['POST'])
@sync_bp.route('/sub_path', methods=['POST'])
@sync_bp.route('/rename_file', methods=['POST'])
@sync_bp.route('/delete_files', methods=['POST'])
@sync_bp.route('/test_connection', methods=['POST'])
```

#### plugin
```python
@plugin_bp.route('/install', methods=['POST'])
@plugin_bp.route('/uninstall', methods=['POST'])
@plugin_bp.route('/apps', methods=['POST'])
@plugin_bp.route('/page', methods=['POST'])
@plugin_bp.route('/state', methods=['POST'])
@plugin_bp.route('/config', methods=['POST'])
@plugin_bp.route('/config/update', methods=['POST'])
@plugin_bp.route('/method/run', methods=['POST'])
```

#### rbac
```python
@rbac_bp.route('/user/create', methods=['POST'])
@rbac_bp.route('/user/update', methods=['POST'])
@rbac_bp.route('/user/delete', methods=['POST'])
@rbac_bp.route('/user/get', methods=['POST'])
@rbac_bp.route('/user/reset_password', methods=['POST'])
@rbac_bp.route('/role/create', methods=['POST'])
@rbac_bp.route('/role/update', methods=['POST'])
@rbac_bp.route('/role/delete', methods=['POST'])
@rbac_bp.route('/role/get', methods=['POST'])
@rbac_bp.route('/menu/create', methods=['POST'])
@rbac_bp.route('/menu/update', methods=['POST'])
@rbac_bp.route('/menu/delete', methods=['POST'])
@rbac_bp.route('/menu/get', methods=['POST'])
@rbac_bp.route('/menu/sort', methods=['POST'])
@rbac_bp.route('/menus/user', methods=['POST'])
@rbac_bp.route('/menus/top', methods=['POST'])
@rbac_bp.route('/users', methods=['POST'])
```

#### scheduler
```python
@scheduler_bp.route('/jobs', methods=['POST'])
@scheduler_bp.route('/job/update', methods=['POST'])
@scheduler_bp.route('/job/delete', methods=['POST'])
@scheduler_bp.route('/job/pause', methods=['POST'])
@scheduler_bp.route('/job/resume', methods=['POST'])
@scheduler_bp.route('/job/run', methods=['POST'])
```

---

## 5. 统一响应格式与错误处理

### 5.1 响应体规范

保持与现有前端兼容的结构：

```json
{
  "code": 0,
  "msg": "",
  "data": {}
}
```

- `code = 0`：业务成功。
- `code > 0` 或 `code = -1`：业务失败（具体含义保持与原 `_fail` 一致）。
- `msg`： human-readable 提示。
- 其余字段平铺返回（保持兼容性）。

### 5.2 核心工具（`web/core/response.py`）

```python
from flask import jsonify

def success(data=None, **kwargs):
    result = {"code": 0}
    if data is not None:
        result["data"] = data
    result.update(kwargs)
    return jsonify(result)

def fail(code=1, msg="", **kwargs):
    result = {"code": code, "msg": msg}
    result.update(kwargs)
    return jsonify(result), 200  # HTTP 状态码保持 200，由 code 区分业务错误
```

### 5.3 装饰器（`web/core/decorators.py`）

```python
from functools import wraps
from flask import request
from flask_login import current_user
from web.core.response import fail

def action_login_check(func):
    """
    Action安全认证装饰器
    """
    @wraps(func)
    def login_check(*args, **kwargs):
        if not current_user.is_authenticated:
            return fail(code=-1, msg="用户未登录")
        return func(*args, **kwargs)
    return login_check

def parse_json_data(func):
    """
    自动提取 request.get_json() 中的 data 字段作为视图函数第一个位置参数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        payload = request.get_json() or {}
        data = payload.get("data") or payload
        return func(data, *args, **kwargs)
    return wrapper
```

### 5.4 Blueprint 视图函数标准写法

```python
from flask import Blueprint
from web.core.decorators import action_login_check, parse_json_data
from web.core.response import success, fail

system_bp = Blueprint("system", __name__, url_prefix="/api/web/system")

@system_bp.route('/restart', methods=['POST'])
@action_login_check
@parse_json_data
def restart(data):
    WebAction.restart_server()
    return success()
```

---

## 6. 前端 `ajax_post` 适配策略

### 6.1 旧调用方式

```javascript
// web/static/js/util.js
function ajax_post(cmd, params, handler, aync = true, show_progress = true) {
  // 原先统一 POST 到 /do，body 为 {cmd: cmd, data: params}
}
```

### 6.2 新适配方案

**方案**：在 `util.js` 中增加一张 **CMD → URL 映射表**，`ajax_post` 内部自动转换，无需一次性修改全部 200+ 调用点。

```javascript
// web/static/js/util.js
const CMD_URL_MAP = {
  "search": "/api/web/media/search",
  "download": "/api/web/download/search",
  "download_link": "/api/web/download/link",
  "restart": "/api/web/system/restart",
  "logout": "/api/web/system/logout",
  "get_site": "/api/web/site/info",
  "get_sites": "/api/web/site/list",
  // ... 全部 200+ 命令映射（见附录完整表）
};

function ajax_post(cmd, params, handler, aync = true, show_progress = true) {
  const url = CMD_URL_MAP[cmd] || "/api/web/do";  // 兜底，重构期间可保留旧 /do
  // 新接口保持同样的 POST + JSON body 格式：{data: params}
  // 若部分接口后续想改为 RESTful 传参，可在此处分支处理
  $.ajax({
    url: url,
    type: "POST",
    contentType: "application/json",
    data: JSON.stringify({data: params}),
    // ... 其余不变
  });
}
```

### 6.3 迁移节奏

1. **第一阶段**：所有 Controller 建成后，填充 `CMD_URL_MAP`，`ajax_post` 自动路由到新 URL。  
2. **第二阶段**：页面 JS 可逐步弃用 `ajax_post("cmd", ...)`，直接调用 `fetch("/api/web/xxx")`。  
3. **第三阶段**：`CMD_URL_MAP` 与 `/do` 中转路由可以同时移除。

---

## 7. `web/action.py` 入口类新形态

### 7.1 新代码结构

```python
# web/action.py
import os
import subprocess

from app.helper.drissionpage_helper import DrissionPageHelper
from app.downloader import Downloader
from app.plugins import PluginManager, EventManager
from app.rss import Rss
from app.rsschecker import RssChecker
from app.scheduler import Scheduler
from app.sync import Sync
from app.torrentremover import TorrentRemover
from app.utils.types import SearchType, EventType
from config import Config
from web.backend.search_torrents import search_media_by_message
from web.cache import cache
from web.core.response import success, fail
from app.helper import ThreadHelper, IndexerHelper
from app.sites import SiteConf


class WebAction:
    """
    仅保留：
    1. 应用生命周期管理（start_service / stop_service / restart_server）
    2. 消息命令处理（handle_message_job）—— 被 webhook / websocket 调用
    3. 少量被 main.py 模板过滤器直接引用的静态工具方法
    """

    @staticmethod
    def stop_service():
        Scheduler().stop_service()
        Sync().stop_service()
        BrushTask().stop_service()
        RssChecker().stop_service()
        TorrentRemover().stop_service()
        Downloader().stop_service()
        PluginManager().stop_service()
        DrissionPageHelper().close_all_tabs()

    @staticmethod
    def start_service():
        IndexerHelper()
        SiteConf()
        Scheduler()
        Sync()
        BrushTask()
        RssChecker()
        TorrentRemover()
        PluginManager()

    @classmethod
    def restart_service(cls):
        cls.stop_service()
        cls.start_service()

    @classmethod
    def restart_server(cls):
        cls.stop_service()
        script_path = os.path.join(os.getcwd(), 'restart-server.sh')
        os.chmod(script_path, 0o755)
        subprocess.run(['bash', script_path], cwd=os.getcwd())

    @staticmethod
    def handle_message_job(msg, in_from=SearchType.OT, user_id=None, user_name=None):
        # 原逻辑原封迁移：_commands 匹配、插件命令、search_media_by_message
        ...

    # 被模板过滤器 brush_rule_string 调用
    @staticmethod
    def parse_brush_rule_string(rules: dict):
        from app.brushtask_rule import BrushRuleEngine
        return BrushRuleEngine.format_rule_html(rules)

    # 被 main.py 页面初始化调用
    @staticmethod
    def get_rmt_modes():
        ...

    @staticmethod
    def get_commands():
        ...
```

### 7.2 说明

- **`action(self, cmd, data)` 与 `api_action(self, cmd, data)` 删除**：由 Blueprint Route 直接替代。  
- **`_actions` 与 `_commands` 字典删除**：`_actions` 彻底消失；`_commands` 移至 `handle_message_job` 内部局部变量或类变量，仅服务于消息机器人。  
- **不再实例化 `WebAction()` 来调用接口**：页面渲染中需要的数据，改为直接调用 `app/` 业务层或新的 Service 辅助函数。

---

## 8. 需要同步修改的外部调用点清单

### 8.1 `web/main.py`

| 位置 | 当前调用 | 修改方式 |
|------|----------|----------|
| `App.register_blueprint(...)` 附近 | 仅注册 `apiv1_bp`、`img_blueprint` | 新增 `from web.controllers import register_blueprints; register_blueprints(App)` |
| `@App.route('/do')` | `WebAction().action(cmd, data)` | **方式 A**：保留 `/do` 但改为遍历已注册 Blueprint 的 view_functions 做二次分发（过渡兼容）；**方式 B**：直接删除 `/do`，依赖前端 `ajax_post` 映射表直调新 URL。推荐 **方式 B**。 |
| 页面路由（如 `index()`、`web()` 等） | 多处 `WebAction().get_xxx()` | 改为直接调用 `app/` 层原方法，或封装到 `web/services/` 辅助函数。例如 `WebAction().get_library_mediacount()` → `MediaServer().get_medias_count()` 等。 |
| `stream_progress` | `WA = WebAction(); WA.refresh_process(...)` | 移到 `web/controllers/system.py` 暴露新路由，或 SSE 逻辑改为直接 import 对应函数。 |
| `message_handler(ws)` | `WebAction().handle_message_job(...)` / `WebAction().get_system_message(...)` | `handle_message_job` 保留在 `WebAction` 类中；`get_system_message` 移入 `system` Controller 或 Service。 |
| 模板过滤器 `brush_rule_string` | `WebAction.parse_brush_rule_string(...)` | 保留 `WebAction.parse_brush_rule_string` 静态方法。 |

### 8.2 `web/apiv1.py`

| 位置 | 当前调用 | 修改方式 |
|------|----------|----------|
| 全部 `WebAction().api_action(cmd='xxx', data=...)` | 通过 `api_action` 二次封装调用 | **一次性全部替换为直接调用 Controller 层函数**。由于 apiv1 已有 namespace 划分，最干净的做法是：每个 namespace 下的 Resource 直接 import 对应 `web/controllers/xxx.py` 中的处理函数，不再经过 `WebAction`。  |
| 部分直接返回的业务数据（如 `BrushTask().get_brushtask_info()`） | 已直接调用 app 层 | 无需改动。 |

### 8.3 `run.py`

- 检查是否直接 `from web.action import WebAction`。
- 若有，改为仅调用生命周期方法（`WebAction.start_service()` 等），或改为 `from web.main import App` 启动 Flask。

### 8.4 插件（`app/plugins/`）

- 搜索 `WebAction` 引用。  
- 若插件通过 `WebAction().action()` 调用 Web 命令，改为：  
  - 若插件自身在后台运行，优先直接调用 `app/` 业务层；  
  - 若必须走 Web 层，改为 HTTP 调用内部新 URL 或 import Controller 函数。

### 8.5 测试文件（`tests/`）

- `tests/test_web_action_refactor.py`、`tests/test_scheduler_webaction.py` 等：更新 import 路径与调用方式，改为测试 Controller 函数或 Blueprint endpoint。

---

## 9. 实施步骤（建议执行顺序）

1. **搭建基础设施**
   - 创建 `web/controllers/` 与 `web/core/decorators.py`。
   - 编写统一响应与装饰器，确保与旧 `_success` / `_fail` 输出一致。
2. **重写 `web/action.py`**
   - 删除 Mixin 继承与 `_actions`，仅保留生命周期与消息处理。
3. **逐个迁移 Controller**
   - 建议顺序：`system` → `site` → `download` → `sync` → `media` → `rss` → `userrss` → `filter` → `words` → `brush` → `plugin` → `rbac` → `scheduler`。
   - 每迁移一个，同步更新 `CMD_URL_MAP` 并跑对应前端页面测试。
4. **改造 `web/main.py`**
   - 注册所有 Blueprint。
   - 移除 `/do` 路由（或保留兼容层）。
   - 将页面路由中的 `WebAction().get_xxx()` 替换为直接业务调用。
5. **改造 `web/apiv1.py`**
   - 将所有 `WebAction().api_action(...)` 替换为直接调用对应 Controller 函数。
6. **前端适配**
   - 修改 `web/static/js/util.js` 的 `ajax_post`。
7. **清理旧代码**
   - 删除 `web/actions/` 目录（`_base.py`、12 个 Mixin）。
8. **回归测试**
   - 重点测试：登录/登出、搜索下载、订阅增删改查、站点测试、刷流任务、调度任务、RBAC 菜单。

---

## 10. 架构图

```mermaid
graph TD
    A[浏览器前端] -->|ajax_post cmd| B[web/static/js/util.js<br/>CMD_URL_MAP]
    B -->|POST /api/web/{domain}/{action}| C[Flask Blueprint Routes<br/>web/controllers/]
    C --> D[web/core/decorators.py<br/>登录校验/参数解析]
    D --> E[Controller 函数体]
    E -->|直接调用| F[app/ 业务层]
    F --> G[数据库/外部服务]

    H[Webhook/Telegram/WeChat] -->|handle_message_job| I[web/action.py<br/>生命周期类]
    I --> F

    J[web/apiv1.py<br/>REST API] -->|直接 import| E
    K[web/main.py<br/>页面路由] -->|直接 import| F
```

---

## 11. 关键接口草图

### 11.1 `web/controllers/__init__.py`

```python
from .system import system_bp
from .media import media_bp
from .site import site_bp
from .download import download_bp
from .rss import rss_bp
from .userrss import userrss_bp
from .filter import filter_bp
from .words import words_bp
from .brush import brush_bp
from .sync import sync_bp
from .plugin import plugin_bp
from .rbac import rbac_bp
from .scheduler import scheduler_bp


def register_blueprints(app):
    bps = [
        system_bp, media_bp, site_bp, download_bp,
        rss_bp, userrss_bp, filter_bp, words_bp,
        brush_bp, sync_bp, plugin_bp, rbac_bp, scheduler_bp,
    ]
    for bp in bps:
        app.register_blueprint(bp)
```

### 11.2 `web/controllers/system.py`（示例）

```python
from flask import Blueprint
from web.core.decorators import action_login_check, parse_json_data
from web.core.response import success, fail
from web.action import WebAction

system_bp = Blueprint("system", __name__, url_prefix="/api/web/system")

@system_bp.route('/restart', methods=['POST'])
@action_login_check
@parse_json_data
def restart(data):
    WebAction.restart_server()
    return success()

@system_bp.route('/version', methods=['POST'])
@action_login_check
@parse_json_data
def version(data):
    from web.backend.web_utils import WebUtils
    version, url, flag = WebUtils.get_latest_version()
    if flag:
        return success(version=version, url=url)
    return fail(code=-1, version="", url="")
```

### 11.3 `web/static/js/util.js` 映射表（节选）

```javascript
const CMD_URL_MAP = {
  "search": "/api/web/media/search",
  "download": "/api/web/download/search",
  "download_link": "/api/web/download/link",
  "restart": "/api/web/system/restart",
  "logout": "/api/web/system/logout",
  "get_site": "/api/web/site/info",
  "get_sites": "/api/web/site/list",
  // ... 完整映射见实施阶段清单
};

function ajax_post(cmd, params, handler, aync = true, show_progress = true) {
  const url = CMD_URL_MAP[cmd] || "/api/web/do";
  $.ajax({
    url: url,
    type: "POST",
    contentType: "application/json",
    data: JSON.stringify({data: params}),
    // ...
  });
}
```

---

## 附录：原 12 Mixin 命令 → 新 URL 完整映射表

> 注：以下映射用于生成 `CMD_URL_MAP` 与 Controller 路由注册表，保持参数不变。

| 原 cmd | 新 URL | 所属 Controller |
|--------|--------|-----------------|
| `sch` | `/api/web/system/sch` | system |
| `search` | `/api/web/media/search` | media |
| `download` | `/api/web/download/search` | download |
| `download_link` | `/api/web/download/link` | download |
| `download_torrent` | `/api/web/download/torrent` | download |
| `pt_start` | `/api/web/download/start` | download |
| `pt_stop` | `/api/web/download/stop` | download |
| `pt_remove` | `/api/web/download/remove` | download |
| `pt_info` | `/api/web/download/info` | download |
| `del_unknown_path` | `/api/web/sync/unknown/delete` | sync |
| `rename` | `/api/web/sync/rename` | sync |
| `rename_udf` | `/api/web/sync/rename_udf` | sync |
| `delete_history` | `/api/web/sync/history/delete` | sync |
| `clear_history` | `/api/web/sync/history/clear` | sync |
| `version` | `/api/web/system/version` | system |
| `update_site` | `/api/web/site/update` | site |
| `get_site` | `/api/web/site/info` | site |
| `del_site` | `/api/web/site/delete` | site |
| `get_site_favicon` | `/api/web/site/favicon` | site |
| `restart` | `/api/web/system/restart` | system |
| `update_system` | `/api/web/system/update` | system |
| `reset_db_version` | `/api/web/system/reset_db_version` | system |
| `logout` | `/api/web/system/logout` | system |
| `update_config` | `/api/web/system/config/update` | system |
| `save_indexer_config` | `/api/web/system/indexer_config` | system |
| `save_mediaserver_config` | `/api/web/system/mediaserver_config` | system |
| `update_directory` | `/api/web/sync/directory/update` | sync |
| `add_or_edit_sync_path` | `/api/web/sync/path/add` | sync |
| `get_sync_path` | `/api/web/sync/path/get` | sync |
| `delete_sync_path` | `/api/web/sync/path/delete` | sync |
| `check_sync_path` | `/api/web/sync/path/check` | sync |
| `remove_rss_media` | `/api/web/rss/remove` | rss |
| `add_rss_media` | `/api/web/rss/add` | rss |
| `re_identification` | `/api/web/sync/re_identification` | sync |
| `media_info` | `/api/web/media/info` | media |
| `test_connection` | `/api/web/sync/test_connection` | sync |
| `user_manager` | `/api/web/rbac/user/manage` | rbac |
| `refresh_rss` | `/api/web/rss/refresh` | rss |
| `movie_calendar_data` | `/api/web/media/calendar/movie` | media |
| `tv_calendar_data` | `/api/web/media/calendar/tv` | media |
| `rss_detail` | `/api/web/rss/detail` | rss |
| `truncate_blacklist` | `/api/web/sync/history/clear` | sync |
| `truncate_rsshistory` | `/api/web/rss/cache/clear` | rss |
| `add_brushtask` | `/api/web/brush/add` | brush |
| `del_brushtask` | `/api/web/brush/delete` | brush |
| `brushtask_detail` | `/api/web/brush/detail` | brush |
| `update_brushtask_state` | `/api/web/brush/state` | brush |
| `name_test` | `/api/web/media/name_test` | media |
| `rule_test` | `/api/web/filter/test` | filter |
| `net_test` | `/api/web/system/net_test` | system |
| `add_filtergroup` | `/api/web/filter/group/add` | filter |
| `restore_filtergroup` | `/api/web/filter/group/restore` | filter |
| `set_default_filtergroup` | `/api/web/filter/group/default` | filter |
| `del_filtergroup` | `/api/web/filter/group/delete` | filter |
| `add_filterrule` | `/api/web/filter/rule/add` | filter |
| `del_filterrule` | `/api/web/filter/rule/delete` | filter |
| `filterrule_detail` | `/api/web/filter/rule/detail` | filter |
| `get_site_activity` | `/api/web/site/statistics/activity` | site |
| `get_site_history` | `/api/web/site/statistics/history` | site |
| `get_recommend` | `/api/web/media/recommend` | media |
| `get_downloaded` | `/api/web/media/downloaded` | media |
| `get_site_seeding_info` | `/api/web/site/statistics/seedinfo` | site |
| `check_site_attr` | `/api/web/site/check_attr` | site |
| `refresh_process` | `/api/web/system/progress` | system |
| `restory_backup` | `/api/web/system/restore_backup` | system |
| `start_mediasync` | `/api/web/media/library/sync_start` | media |
| `mediasync_state` | `/api/web/media/library/sync_status` | media |
| `get_tvseason_list` | `/api/web/media/tv_seasons` | media |
| `get_userrss_task` | `/api/web/userrss/task/get` | userrss |
| `delete_userrss_task` | `/api/web/userrss/task/delete` | userrss |
| `update_userrss_task` | `/api/web/userrss/task/update` | userrss |
| `check_userrss_task` | `/api/web/userrss/task/check` | userrss |
| `get_rssparser` | `/api/web/userrss/parser/get` | userrss |
| `delete_rssparser` | `/api/web/userrss/parser/delete` | userrss |
| `update_rssparser` | `/api/web/userrss/parser/update` | userrss |
| `run_userrss` | `/api/web/userrss/run` | userrss |
| `run_brushtask` | `/api/web/brush/run` | brush |
| `list_site_resources` | `/api/web/site/resources` | site |
| `list_rss_articles` | `/api/web/userrss/articles` | userrss |
| `rss_article_test` | `/api/web/userrss/article_test` | userrss |
| `list_rss_history` | `/api/web/userrss/history` | userrss |
| `rss_articles_check` | `/api/web/userrss/articles_check` | userrss |
| `rss_articles_download` | `/api/web/userrss/articles_download` | userrss |
| `add_custom_word_group` | `/api/web/words/group/add` | words |
| `delete_custom_word_group` | `/api/web/words/group/delete` | words |
| `add_or_edit_custom_word` | `/api/web/words/word/update` | words |
| `get_custom_word` | `/api/web/words/word/get` | words |
| `delete_custom_words` | `/api/web/words/word/delete` | words |
| `check_custom_words` | `/api/web/words/word/check` | words |
| `export_custom_words` | `/api/web/words/word/export` | words |
| `analyse_import_custom_words_code` | `/api/web/words/word/analyse` | words |
| `import_custom_words` | `/api/web/words/word/import` | words |
| `get_categories` | `/api/web/words/categories` | words |
| `re_rss_history` | `/api/web/rss/history/redo` | rss |
| `delete_rss_history` | `/api/web/rss/history/delete` | rss |
| `share_filtergroup` | `/api/web/filter/rule/share` | filter |
| `import_filtergroup` | `/api/web/filter/rule/import` | filter |
| `get_transfer_statistics` | `/api/web/media/transfer/statistics` | media |
| `get_library_spacesize` | `/api/web/media/library/space` | media |
| `get_library_mediacount` | `/api/web/media/library/count` | media |
| `get_library_playhistory` | `/api/web/media/library/playhistory` | media |
| `get_search_result` | `/api/web/media/search_result` | media |
| `search_media_infos` | `/api/web/media/search` | media |
| `get_movie_rss_list` | `/api/web/rss/movie/list` | rss |
| `get_tv_rss_list` | `/api/web/rss/tv/list` | rss |
| `get_rss_history` | `/api/web/rss/history` | rss |
| `get_transfer_history` | `/api/web/sync/history/list` | sync |
| `get_unknown_list` | `/api/web/sync/unknown/list` | sync |
| `get_unknown_list_by_page` | `/api/web/sync/unknown/list_page` | sync |
| `get_customwords` | `/api/web/words/list` | words |
| `get_users` | `/api/web/rbac/users` | rbac |
| `get_filterrules` | `/api/web/filter/rules` | filter |
| `get_downloading` | `/api/web/download/now` | download |
| `test_site` | `/api/web/site/test` | site |
| `get_sub_path` | `/api/web/sync/sub_path` | sync |
| `rename_file` | `/api/web/sync/rename_file` | sync |
| `delete_files` | `/api/web/sync/delete_files` | sync |
| `download_subtitle` | `/api/web/media/subtitle/download` | media |
| `get_download_setting` | `/api/web/download/setting/get` | download |
| `update_download_setting` | `/api/web/download/setting/update` | download |
| `delete_download_setting` | `/api/web/download/setting/delete` | download |
| `update_message_client` | `/api/web/system/message_client/update` | system |
| `delete_message_client` | `/api/web/system/message_client/delete` | system |
| `check_message_client` | `/api/web/system/message_client/check` | system |
| `get_message_client` | `/api/web/system/message_client/get` | system |
| `test_message_client` | `/api/web/system/message_client/test` | system |
| `get_sites` | `/api/web/site/list` | site |
| `get_indexers` | `/api/web/download/indexers` | download |
| `get_download_dirs` | `/api/web/download/dirs` | download |
| `find_hardlinks` | `/api/web/download/hardlinks` | download |
| `update_site_cookie_ua` | `/api/web/site/cookie_ua` | site |
| `set_site_captcha_code` | `/api/web/site/captcha` | site |
| `update_torrent_remove_task` | `/api/web/download/torrent_remove/update` | download |
| `get_torrent_remove_task` | `/api/web/download/torrent_remove/get` | download |
| `delete_torrent_remove_task` | `/api/web/download/torrent_remove/delete` | download |
| `get_remove_torrents` | `/api/web/download/torrent_remove/list` | download |
| `auto_remove_torrents` | `/api/web/download/torrent_remove/auto` | download |
| `list_brushtask_torrents` | `/api/web/brush/torrents` | brush |
| `set_system_config` | `/api/web/system/set` | system |
| `get_site_user_statistics` | `/api/web/site/statistics/user` | site |
| `send_plugin_message` | `/api/web/plugin/message` | plugin |
| `send_custom_message` | `/api/web/system/custom_message` | system |
| `media_detail` | `/api/web/media/detail` | media |
| `media_similar` | `/api/web/media/similar` | media |
| `media_recommendations` | `/api/web/media/recommendations` | media |
| `media_person` | `/api/web/media/person` | media |
| `person_medias` | `/api/web/media/person_medias` | media |
| `save_user_script` | `/api/web/system/user_script` | system |
| `run_directory_sync` | `/api/web/sync/run` | sync |
| `update_plugin_config` | `/api/web/plugin/config/update` | plugin |
| `get_season_episodes` | `/api/web/media/season_episodes` | media |
| `get_user_menus` | `/api/web/rbac/menus/user` | rbac |
| `get_top_menus` | `/api/web/rbac/menus/top` | rbac |
| `update_downloader` | `/api/web/download/client/update` | download |
| `del_downloader` | `/api/web/download/client/delete` | download |
| `check_downloader` | `/api/web/download/client/check` | download |
| `get_downloaders` | `/api/web/download/client/list` | download |
| `test_downloader` | `/api/web/download/client/test` | download |
| `get_indexer_statistics` | `/api/web/download/indexer_statistics` | download |
| `media_path_scrap` | `/api/web/media/path_scrap` | media |
| `get_default_rss_setting` | `/api/web/rss/default_setting` | rss |
| `get_movie_rss_items` | `/api/web/rss/movie/items` | rss |
| `get_tv_rss_items` | `/api/web/rss/tv/items` | rss |
| `get_ical_events` | `/api/web/rss/ical` | rss |
| `install_plugin` | `/api/web/plugin/install` | plugin |
| `uninstall_plugin` | `/api/web/plugin/uninstall` | plugin |
| `get_plugin_apps` | `/api/web/plugin/apps` | plugin |
| `get_plugin_page` | `/api/web/plugin/page` | plugin |
| `get_plugin_state` | `/api/web/plugin/state` | plugin |
| `get_plugins_conf` | `/api/web/plugin/config` | plugin |
| `update_category_config` | `/api/web/system/category_config` | system |
| `get_category_config` | `/api/web/system/category_config` | system |
| `get_system_processes` | `/api/web/system/processes` | system |
| `run_plugin_method` | `/api/web/plugin/method/run` | plugin |
| `update_all_config` | `/api/web/system/config/all` | system |
| `add_tmdb_blacklist` | `/api/web/system/tmdb_blacklist/add` | system |
| `delete_tmdb_blacklist` | `/api/web/system/tmdb_blacklist/delete` | system |
| `clear_tmdb_blacklist` | `/api/web/system/tmdb_blacklist/clear` | system |
| `create_user` | `/api/web/rbac/user/create` | rbac |
| `update_user` | `/api/web/rbac/user/update` | rbac |
| `delete_user` | `/api/web/rbac/user/delete` | rbac |
| `get_user` | `/api/web/rbac/user/get` | rbac |
| `reset_password` | `/api/web/rbac/user/reset_password` | rbac |
| `create_role` | `/api/web/rbac/role/create` | rbac |
| `update_role` | `/api/web/rbac/role/update` | rbac |
| `delete_role` | `/api/web/rbac/role/delete` | rbac |
| `get_role` | `/api/web/rbac/role/get` | rbac |
| `create_menu` | `/api/web/rbac/menu/create` | rbac |
| `update_menu` | `/api/web/rbac/menu/update` | rbac |
| `delete_menu` | `/api/web/rbac/menu/delete` | rbac |
| `get_menu` | `/api/web/rbac/menu/get` | rbac |
| `update_menu_sort` | `/api/web/rbac/menu/sort` | rbac |
| `get_scheduler_jobs` | `/api/web/scheduler/jobs` | scheduler |
| `update_scheduler_job` | `/api/web/scheduler/job/update` | scheduler |
| `delete_scheduler_job` | `/api/web/scheduler/job/delete` | scheduler |
| `pause_scheduler_job` | `/api/web/scheduler/job/pause` | scheduler |
| `resume_scheduler_job` | `/api/web/scheduler/job/resume` | scheduler |
| `run_scheduler_job` | `/api/web/scheduler/job/run` | scheduler |
