# Nexus Media 插件开发文档（Plugin Framework v2）

## 概述

Plugin Framework v2 是 Nexus Media 的插件架构，支持前后端一体化开发。每个插件是一个独立的目录包，包含 `manifest.json` 元数据、后端 Python 代码和前端 UMD 组件。

**核心特性：**
- 声明式 manifest 定义，无需修改系统代码
- 沙箱隔离运行，热重载支持
- 内置定时任务、配置持久化、日志管理
- 前端通过 UMD 格式注入，支持独立页面、设置表单和页面插槽
- 全局 HookSystem 事件总线，插件间可通信

---

## 目录结构

```
my_plugin/
├── manifest.json              # 插件元数据（必须）
├── backend/
│   ├── __init__.py
│   └── plugin.py              # 后端主类（必须）
└── frontend/
    └── index.umd.js           # 前端 UMD 包（可选）
```

---

## manifest.json

```json
{
  "manifest_version": "1.0",
  "id": "my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "author": "linyuan0213",
  "author_url": "https://github.com/linyuan0213",
  "description": "插件功能描述",
  "category": "media",
  "tags": ["标签1", "标签2"],
  "icon": "lucide:puzzle",
  "color": "#3b82f6",
  "min_app_version": "3.0.0",
  "backend": {
    "entry": "backend.plugin:MyPlugin",
    "api_prefix": "/api/plugin/my_plugin",
    "permissions": [],
    "hooks": [
      "plugin.config_changed",
      "media.transfered"
    ],
    "supports_run": true
  },
  "frontend": {
    "routes": [
      {
        "path": "history",
        "component": "HistoryPage",
        "title": "历史记录",
        "icon": "lucide:history",
        "menu": true
      }
    ],
    "settings": {
      "component": "SettingsPage",
      "fields": [
        {
          "key": "enabled",
          "type": "switch",
          "label": "启用插件",
          "default": false,
          "help": "开启后插件生效"
        },
        {
          "key": "interval",
          "type": "number",
          "label": "间隔（秒）",
          "default": 60,
          "placeholder": "60"
        },
        {
          "key": "sites",
          "type": "multi_select",
          "label": "选择站点",
          "source": "sites",
          "default": [],
          "help": "选择需要处理的站点"
        },
        {
          "key": "cron",
          "type": "cron",
          "label": "执行周期",
          "default": "0 0 * * *",
          "placeholder": "0 0 * * *"
        }
      ]
    },
    "slots": []
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 插件唯一标识，仅允许字母、数字、下划线 |
| `name` | string | 是 | 显示名称 |
| `version` | string | 是 | 版本号 |
| `author` | string | 是 | 作者 |
| `category` | string | 是 | 分类：`system`/`media`/`download`/`site`/`tool` |
| `icon` | string | 否 | lucide 图标名，如 `lucide:puzzle` |
| `color` | string | 否 | 主题色，如 `#3b82f6` |
| `backend.entry` | string | 是 | 后端入口：`module.path:ClassName` |
| `backend.hooks` | string[] | 否 | 订阅的事件列表 |
| `backend.supports_run` | bool | 否 | 是否支持手动运行 |
| `frontend.routes` | object[] | 否 | 独立页面路由定义 |
| `frontend.settings.fields` | object[] | 否 | 设置表单字段 |
| `frontend.slots` | object[] | 否 | 页面插槽定义 |

### settings fields 类型

| type | 说明 | 额外字段 |
|------|------|----------|
| `switch` | 开关 | - |
| `input` | 文本输入 | `placeholder` |
| `password` | 密码输入 | `placeholder` |
| `textarea` | 多行文本 | `placeholder` |
| `number` | 数字输入 | `placeholder` |
| `select` | 单选下拉 | `options: [{label, value}]` |
| `multi_select` | 多选下拉 | `options` 或 `source: "sites"` |
| `cron` | Cron 表达式 | `placeholder` |

当 `source: "sites"` 时，前端会自动拉取站点列表作为选项，并过滤 BT 公开站点。

---

## 后端开发

### 最小插件类

```python

"""
MyPlugin - 插件后端
"""


class MyPlugin:
    """我的插件"""

    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        """插件启用时调用"""
        self.ctx.info("插件已启用")

    def on_disable(self):
        """插件禁用时调用"""
        self.ctx.info("插件已禁用")

    def on_hook(self, event, data):
        """订阅的事件触发时调用"""
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已更新")

    def run(self):
        """手动运行（supports_run: true 时可用）"""
        self.ctx.info("手动运行插件任务")
```

### 生命周期方法

| 方法 | 触发时机 | 说明 |
|------|----------|------|
| `on_enable()` | 插件启用后 | 初始化定时任务、注册事件等 |
| `on_disable()` | 插件禁用前 | 清理资源、取消定时任务 |
| `on_hook(event, data)` | 订阅事件触发 | 处理全局事件 |
| `run()` | 用户点击「运行」 | 手动触发任务执行 |

### PluginContext API

```python
# 配置读写
self.ctx.get_config()               # 获取全部配置 dict
self.ctx.get_config("key", default) # 获取单个配置项
self.ctx.set_config("key", value)   # 设置单个配置项
self.ctx.set_all_config({"k": "v"}) # 设置全部配置

# 日志
self.ctx.info("信息日志")
self.ctx.warn("警告日志")
self.ctx.error("错误日志")
self.ctx.debug("调试日志")

# 数据文件（位于 config/plugins_data/{plugin_id}/）
content = self.ctx.read_data("history.json")   # 读取数据文件
self.ctx.write_data("history.json", "{}")      # 写入数据文件

# 目录
self.ctx.data_dir  # 插件数据目录路径

# 通知
self.ctx.notify("标题", "正文内容", image="可选图片URL")

# 定时任务
self.ctx.schedule_cron("job1", func, cron="0 8 * * *")
self.ctx.schedule_interval("job2", func, minutes=5)
self.ctx.schedule_date("once", func, run_date=datetime)
self.ctx.remove_schedule("job1")

# 事件触发
self.ctx.emit("custom.event", {"key": "value"})
```

### 定时任务完整示例

```python
from datetime import datetime, timedelta
import pytz
from config import Config

class MyPlugin:
    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        config = self.ctx.get_config()
        cron = config.get("cron")
        onlyonce = config.get("onlyonce", False)

        if cron:
            self.ctx.schedule_cron("main", self._do_task, cron=str(cron))

        if onlyonce:
            tz = pytz.timezone(Config().get_timezone())
            run_date = datetime.now(tz=tz) + timedelta(seconds=3)
            self.ctx.schedule_date("once", self._do_task, run_date=run_date)
            self.ctx.set_config("onlyonce", False)

    def on_disable(self):
        self.ctx.remove_schedule("main")
        self.ctx.remove_schedule("once")

    def _do_task(self):
        self.ctx.info("定时任务执行中...")
```

### 事件订阅与处理

在 `manifest.json` 的 `backend.hooks` 中声明订阅的事件：

```json
{
  "backend": {
    "hooks": [
      "plugin.config_changed",
      "media.transfered",
      "download.completed"
    ]
  }
}
```

在 `on_hook` 中处理：

```python
def on_hook(self, event, data):
    if event == "media.transfered":
        path = data.get("path")
        self.ctx.info(f"媒体已转移: {path}")
    elif event == "download.completed":
        torrent_id = data.get("torrent_id")
        self.ctx.info(f"下载完成: {torrent_id}")
```

### 可用事件列表

```
plugin.install / plugin.enable / plugin.disable / plugin.uninstall
plugin.config_changed / plugin.reload

media.scraped / media.transfered / media.library_synced
media.source_deleted / media.douban_sync

download.started / download.completed / download.failed / download.removed

site.signed_in / site.statistics_updated / site.cookie_sync
site.local_storage_sync / site.signin

rss.subscribed / rss.found / rss.downloaded

webhook.emby / webhook.jellyfin / webhook.plex

system.startup / system.shutdown / scheduler.tick

wework.login / subtitle.download / message.incoming
subscribe.add / subscribe.finished / search.start
transfer.fail / library.file_deleted / autoseed.start
```

---

## 前端开发

### UMD 格式要求

前端组件打包为 UMD 格式，暴露到 `window.__PLUGIN_{id}__`。

```javascript
(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? factory(exports, require('vue'))
    : typeof define === 'function' && define.amd
      ? define(['exports', 'vue'], factory)
      : (global = typeof globalThis !== 'undefined' ? globalThis : global || self,
         factory(global.__PLUGIN_my_plugin__ = {}, global.Vue));
})(this, function (exports, Vue) {
  'use strict';
  const { h, ref, onMounted, computed } = Vue;

  // 组件定义...

  exports.MyPage = MyPage;
});
```

### 全局可用依赖

| 全局变量 | 说明 |
|----------|------|
| `window.Vue` | Vue 3 完整 API（h, ref, computed, watch, onMounted 等） |
| `window.IconifyIcon` | `@vben/icons` 的 IconifyIcon 组件 |
| `window.requestClient` | 前端 HTTP 客户端（axios 封装） |

### 主题 CSS 变量

所有颜色必须使用 Vben Admin 主题变量：

```javascript
h('div', {
  style: {
    backgroundColor: 'hsl(var(--card))',
    color: 'hsl(var(--card-foreground))',
    border: '1px solid hsl(var(--border) / 0.5)',
  }
})
```

| 变量 | 用途 |
|------|------|
| `--background` | 页面背景 |
| `--foreground` | 主文字 |
| `--card` | 卡片背景 |
| `--card-foreground` | 卡片文字 |
| `--border` | 边框 |
| `--primary` | 主色调 |
| `--primary-foreground` | 主色调文字 |
| `--muted-foreground` | 次要文字 |
| `--success` | 成功 |
| `--warning` | 警告 |
| `--destructive` | 危险/删除 |

### 组件类型

#### 1. 独立页面（Routes）

```javascript
const HistoryPage = {
  name: 'MyHistoryPage',
  setup() {
    const loading = ref(false);
    const records = ref([]);

    async function fetchData() {
      const res = await window.requestClient.get(
        '/api/plugin-framework/plugins/my_plugin/data/history.json'
      );
      records.value = res || [];
    }

    onMounted(fetchData);

    return () => h('div', { style: { padding: '1.5rem' } }, [
      h('h2', {}, '历史记录'),
      ...records.value.map(item => h('div', {}, item.name))
    ]);
  }
};

exports.HistoryPage = HistoryPage;
```

路由路径：`/plugin/{plugin_id}/{path}`，如 `/plugin/my_plugin/history`。

#### 2. 设置页面（Settings）

```javascript
const SettingsPage = {
  name: 'MySettings',
  props: ['config', 'onChange'],
  setup(props) {
    const local = ref({ ...props.config });

    const update = (key, value) => {
      local.value[key] = value;
      if (props.onChange) props.onChange(local.value);
    };

    return () => h('div', {}, [
      h('input', {
        value: local.value.greeting || '',
        onInput: (e) => update('greeting', e.target.value),
      })
    ]);
  }
};

exports.SettingsPage = SettingsPage;
```

#### 3. 插槽组件（Slots）

```json
{
  "frontend": {
    "slots": [
      {
        "target": "dashboard.home",
        "position": "after_stats",
        "component": "DashboardWidget"
      }
    ]
  }
}
```

```javascript
const DashboardWidget = {
  name: 'MyWidget',
  setup() {
    return () => h('div', {
      style: {
        padding: '1rem',
        borderRadius: '0.5rem',
        backgroundColor: 'hsl(var(--card))',
        border: '1px solid hsl(var(--border))',
      }
    }, '插槽内容');
  }
};

exports.DashboardWidget = DashboardWidget;
```

### 数据文件读取

插件可通过 `/api/plugin-framework/plugins/{plugin_id}/data/{filename}` 读取后端写入的数据文件：

```javascript
const res = await window.requestClient.get(
  '/api/plugin-framework/plugins/my_plugin/data/history.json'
);
```

### IconifyIcon 使用

```javascript
const IconifyIcon = window.IconifyIcon;

h(IconifyIcon, {
  icon: 'lucide:check-circle',
  style: { fontSize: '1rem', color: 'hsl(var(--success))' }
})
```

所有图标前缀统一为 `lucide:`。

---

## 数据持久化

### 配置存储

插件配置自动持久化到数据库，通过 `PluginContext` 读写：

```python
# 后端写入
self.ctx.set_config("sites", ["1", "2", "3"])

# 后端读取
sites = self.ctx.get_config("sites", [])
```

### 数据文件

对于复杂数据（如历史记录），写入数据目录：

```python
import json

history = {"2025-01-15": {"sign": ["1", "2"], "retry": ["3"]}}
self.ctx.write_data("history.json", json.dumps(history, ensure_ascii=False))
```

前端通过 API 读取：

```javascript
const data = await window.requestClient.get(
  '/api/plugin-framework/plugins/my_plugin/data/history.json'
);
```

### 日志

```python
self.ctx.info("普通信息")
self.ctx.warn("警告信息")
self.ctx.error("错误信息")
self.ctx.debug("调试信息")
```

日志同时写入文件和数据库，可在前端「日志」按钮中查看。

---

## 调试

### 后端调试

1. 修改 `backend/plugin.py` 后，在前端点击「重载」按钮热重载
2. 或重启 Nexus Media 服务
3. 查看日志：`logs/nas-tools.log` 或前端插件日志面板

### 前端调试

1. 打开浏览器 DevTools → Console
2. 检查 `window.__PLUGIN_{id}__` 是否正确注册
3. 检查 Vue Router 路由是否正确注册：`router.getRoutes()`

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 插件加载失败 | 入口类名不匹配 | 检查 `backend.entry` 和类名 |
| 前端页面空白 | UMD 未正确暴露组件 | 检查 `exports.XXX = XXX` |
| 配置不保存 | 字段 key 不匹配 | 检查 manifest 和代码中的 key |
| 定时任务不执行 | cron 格式错误 | 使用标准 5 位 cron 表达式 |

---

## 打包与安装

### 打包

```bash
cd my_plugin/
zip -r ../my_plugin-v1.0.0.zip .
```

### 安装

1. 进入 Nexus Media 前端「插件市场」
2. 点击右上角「安装本地插件」
3. 上传 zip 文件
4. 在「已安装插件」页面启用

### 更新

直接上传新版本的 zip 包，系统会自动：
- 禁用旧版本
- 删除旧文件
- 安装新版本
- 保留原有配置

---

## 完整示例

### 后端：backend/plugin.py

```python

"""
示例插件后端
"""
import json
from datetime import datetime


class DemoPlugin:
    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        self.ctx.info("Demo 插件已启用")
        config = self.ctx.get_config()
        cron = config.get("cron")
        if cron:
            self.ctx.schedule_cron("task", self._run, cron=str(cron))

    def on_disable(self):
        self.ctx.remove_schedule("task")

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更")

    def run(self):
        self.ctx.info("手动运行")
        self._run()

    def _run(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history = {"time": now, "status": "ok"}
        self.ctx.write_data("history.json", json.dumps(history))
        self.ctx.notify("Demo 插件", f"任务完成于 {now}")
```

### 前端：frontend/index.umd.js

```javascript
(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? factory(exports, require('vue'))
    : typeof define === 'function' && define.amd
      ? define(['exports', 'vue'], factory)
      : (global = typeof globalThis !== 'undefined' ? globalThis : global || self,
         factory(global.__PLUGIN_demo__ = {}, global.Vue));
})(this, function (exports, Vue) {
  'use strict';
  const { h, ref, onMounted } = Vue;

  const HistoryPage = {
    setup() {
      const data = ref(null);
      onMounted(async () => {
        const res = await window.requestClient.get(
          '/api/plugin-framework/plugins/demo/data/history.json'
        );
        data.value = res;
      });
      return () => h('div', { style: { padding: '1.5rem' } },
        data.value
          ? h('div', {}, [
              h('div', { style: { fontWeight: 600 } }, `时间: ${data.value.time}`),
              h('div', {}, `状态: ${data.value.status}`),
            ])
          : h('div', {}, '加载中...')
      );
    }
  };

  exports.HistoryPage = HistoryPage;
});
```

### manifest.json

```json
{
  "manifest_version": "1.0",
  "id": "demo",
  "name": "Demo 插件",
  "version": "1.0.0",
  "author": "linyuan0213",
  "description": "演示插件开发",
  "category": "tool",
  "icon": "lucide:zap",
  "backend": {
    "entry": "backend.plugin:DemoPlugin",
    "hooks": ["plugin.config_changed"],
    "supports_run": true
  },
  "frontend": {
    "routes": [
      {
        "path": "history",
        "component": "HistoryPage",
        "title": "执行记录",
        "icon": "lucide:history",
        "menu": true
      }
    ],
    "settings": {
      "component": "SettingsPage",
      "fields": [
        {
          "key": "cron",
          "type": "cron",
          "label": "执行周期",
          "default": "0 0 * * *"
        }
      ]
    }
  }
}
```

---

## 参考

- 完整示例：`examples/plugins/hello_world/`
- 内置插件参考：`app/plugin_framework/builtin_plugins/`
- 核心框架代码：`app/plugin_framework/`
