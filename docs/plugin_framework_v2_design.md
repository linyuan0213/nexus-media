# Nexus Media 插件框架 v2 设计文档

## 1. 设计目标

### 1.1 核心能力
1. **前后端一体化插件包**：单个 `.zip` 包含后端 Python + 前端 Vue/JS
2. **动态加载**：安装后无需重启，前后端热加载
3. **页面扩展**：插件可注册独立页面、嵌入核心页面插槽
4. **API 扩展**：插件可注册独立 API 路由
5. **安全隔离**：后端沙箱运行，前端 iframe/动态组件隔离

### 1.2 与旧插件关系
- 旧 `_IPluginModule` 体系冻结，不再扩展
- 新框架搭建完成后，逐步将旧插件核心逻辑迁移为新格式
- 过渡期内两套体系并行

---

## 2. 插件包格式

```
plugin-name-v1.0.0.zip
├── manifest.json          # 插件元数据和声明
├── backend/
│   ├── __init__.py
│   ├── handler.py         # 插件主类
│   └── requirements.txt   # Python 依赖
└── frontend/
    ├── index.umd.js       # 主页面组件 (UMD)
    ├── settings.umd.js    # 设置页面组件 (UMD)
    ├── icon.svg           # 插件图标
    └── README.md          # 文档
```

### 2.1 manifest.json 规范

```json
{
  "manifest_version": "1.0",
  "id": "com.example.autosignin",
  "name": "站点自动签到",
  "version": "1.2.0",
  "author": "Nexus Media Team",
  "author_url": "https://github.com/...",
  "description": "自动签到站点获取魔力值",
  "category": "site",
  "tags": ["签到", "定时任务"],
  "icon": "lucide:calendar-check",
  "color": "#22c55e",
  "min_app_version": "3.0.0",
  "backend": {
    "entry": "backend.handler:AutoSignInPlugin",
    "api_prefix": "/api/plugin/autosignin",
    "permissions": ["site:view"],
    "hooks": [
      "scheduler.tick",
      "plugin.config_changed"
    ]
  },
  "frontend": {
    "routes": [
      {
        "path": "/plugin/autosignin",
        "component": "frontend/index.umd.js",
        "title": "自动签到",
        "icon": "lucide:calendar-check",
        "menu": true
      }
    ],
    "settings": {
      "component": "frontend/settings.umd.js",
      "fields": [
        {
          "key": "enabled",
          "type": "switch",
          "label": "启用签到",
          "default": true
        },
        {
          "key": "cron",
          "type": "cron",
          "label": "执行周期",
          "default": "0 8 * * *"
        },
        {
          "key": "sites",
          "type": "multi_select",
          "label": "签到站点",
          "source": "sites"
        }
      ]
    },
    "slots": [
      {
        "target": "dashboard.home",
        "position": "after_stats",
        "component": "frontend/dashboard-widget.umd.js"
      }
    ]
  }
}
```

---

## 3. 后端架构

### 3.1 目录结构

```
app/plugin_framework/              # 新插件框架
├── __init__.py
├── registry.py                    # 插件注册表
├── sandbox.py                     # 沙箱运行环境
├── loader.py                      # 包加载器
├── api_gateway.py                 # API 网关
├── hook_system.py                 # 事件钩子系统
├── models.py                      # 数据模型
└── schemas.py                     # DTO

plugins/                           # 用户插件目录（gitignore）
├── autosignin-1.2.0/
├── webhook-2.0.0/
└── ...
```

### 3.2 核心类

#### PluginRegistry

```python
class PluginRegistry:
    """插件注册表，管理所有已安装插件的元数据"""

    def scan(self) -> List[PluginManifest]:
        """扫描 plugins/ 目录，加载所有 manifest"""

    def install(self, zip_path: str) -> PluginManifest:
        """安装插件包，解压到 plugins/{id}-{version}/"""

    def uninstall(self, plugin_id: str) -> None:
        """卸载插件，删除目录并清理注册表"""

    def get(self, plugin_id: str) -> PluginManifest:
        """获取插件元数据"""

    def list(self, category=None, installed_only=True) -> List[PluginManifest]:
        """列出插件"""
```

#### PluginSandbox

```python
class PluginSandbox:
    """插件沙箱，隔离运行环境"""

    def load_backend(self, manifest: PluginManifest):
        """动态加载后端模块，注入 PluginContext"""

    def unload(self, plugin_id: str):
        """卸载插件，清理资源"""

    def call(self, plugin_id: str, method: str, *args, **kwargs):
        """调用插件方法"""
```

#### PluginContext（注入给插件的上下文）

```python
class PluginContext:
    """插件可访问的系统能力"""

    # 配置读写
    config: PluginConfigStore

    # 数据持久化
    db: PluginDatabase

    # 消息通知
    notify: PluginNotifier

    # 定时任务
    scheduler: PluginScheduler

    # HTTP 客户端
    http: PluginHttpClient

    # 日志
    logger: Logger

    # 事件发布
    def emit(self, event: str, data: dict): ...

    # 获取系统服务（只读代理）
    def get_service(self, name: str): ...
```

#### PluginConfigStore

```python
class PluginConfigStore:
    """插件配置存储，每个插件独立命名空间"""

    def get(self, key: str, default=None):
        """读取配置"""

    def set(self, key: str, value):
        """写入配置"""

    def all(self) -> dict:
        """获取全部配置"""
```

#### API 网关

```python
class PluginAPIGateway:
    """插件 API 网关，动态挂载 FastAPI 子路由"""

    def mount(self, plugin_id: str, prefix: str, router: APIRouter):
        """为插件挂载 API 路由"""

    def unmount(self, plugin_id: str):
        """卸载插件路由"""
```

### 3.3 插件基类（新版）

```python
class BasePlugin(ABC):
    """新版插件基类"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    @abstractmethod
    def on_install(self):
        """首次安装时调用"""
        pass

    @abstractmethod
    def on_enable(self):
        """启用时调用"""
        pass

    @abstractmethod
    def on_disable(self):
        """禁用时调用"""
        pass

    @abstractmethod
    def on_uninstall(self):
        """卸载时调用"""
        pass

    def on_config_change(self, config: dict):
        """配置变更时调用"""
        pass

    def on_hook(self, event: str, data: dict):
        """事件触发时调用"""
        pass
```

### 3.4 Hook 系统

```python
class HookSystem:
    """全局事件钩子"""

    # 核心事件
    EVENTS = [
        # 插件生命周期
        "plugin.install",
        "plugin.enable",
        "plugin.disable",
        "plugin.uninstall",
        "plugin.config_changed",

        # 媒体事件
        "media.scraped",           # 刮削完成
        "media.transfered",        # 转移完成
        "media.library_synced",    # 媒体库同步完成

        # 下载事件
        "download.started",
        "download.completed",
        "download.failed",
        "download.removed",

        # 站点事件
        "site.signed_in",          # 签到完成
        "site.statistics_updated", # 统计更新

        # 订阅事件
        "rss.subscribed",
        "rss.found",
        "rss.downloaded",

        # 系统事件
        "scheduler.tick",          # 定时触发
        "system.startup",
        "system.shutdown",
    ]

    def register(self, event: str, handler: Callable, plugin_id: str = None)
    def unregister(self, event: str, handler: Callable)
    def emit(self, event: str, data: dict)
```

### 3.5 API 端点

```yaml
/api/plugin-framework:

  # 插件管理
  GET    /plugins                    列出所有插件
  POST   /plugins/install            安装插件（上传 zip）
  DELETE /plugins/{id}               卸载插件
  POST   /plugins/{id}/enable        启用插件
  POST   /plugins/{id}/disable       禁用插件
  GET    /plugins/{id}/manifest      获取 manifest
  GET    /plugins/{id}/readme        获取 README

  # 插件配置
  GET    /plugins/{id}/config        获取配置
  POST   /plugins/{id}/config        保存配置

  # 插件历史/日志
  GET    /plugins/{id}/logs          获取日志
  DELETE /plugins/{id}/logs          清空日志

  # 钩子调试
  POST   /hooks/emit                 手动触发钩子（调试用）
```

---

## 4. 前端架构

### 4.1 插件前端加载器

```typescript
// src/plugin-framework/loader.ts
class PluginLoader {
  // 已加载的插件组件
  private components = new Map<string, Component>();

  // 从后端获取插件清单并加载前端资源
  async loadPlugins() {
    const manifests = await getPluginManifests();
    for (const m of manifests) {
      if (m.frontend?.routes) {
        await this.loadRoutes(m.id, m.frontend.routes);
      }
      if (m.frontend?.slots) {
        await this.loadSlots(m.id, m.frontend.slots);
      }
    }
  }

  // 动态加载 UMD 组件
  async loadComponent(pluginId: string, url: string): Promise<Component> {
    // 方案1: 通过 script 标签加载 UMD
    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = url;
      script.onload = () => {
        // UMD 包会在 window 上暴露组件
        const comp = window[`__PLUGIN_${pluginId}`];
        resolve(comp);
      };
      document.head.appendChild(script);
    });
  }
}
```

### 4.2 动态路由注册

```typescript
// 在获取用户菜单后，动态添加插件路由
function registerPluginRoutes(manifests: PluginManifest[]) {
  const router = useRouter();
  for (const m of manifests) {
    for (const route of m.frontend?.routes || []) {
      router.addRoute({
        path: route.path,
        name: `Plugin_${m.id}_${route.path}`,
        component: () => pluginLoader.loadComponent(m.id, route.component),
        meta: {
          title: route.title,
          icon: route.icon,
          pluginId: m.id,
        },
      });
    }
  }
}
```

### 4.3 页面插槽系统

核心页面预留插槽，插件可注入组件：

```vue
<!-- dashboard/home/index.vue -->
<template>
  <div>
    <!-- 固定内容 -->
    <WelcomeHeader />
    <StatCards />

    <!-- 插件插槽: after_stats -->
    <PluginSlot name="dashboard.home.after_stats" />

    <!-- 固定内容 -->
    <Charts />
  </div>
</template>
```

```vue
<!-- PluginSlot.vue -->
<script setup>
const props = defineProps<{ name: string }>();
const components = computed(() => pluginSlotStore.getSlots(props.name));
</script>

<template>
  <div v-for="comp in components" :key="comp.pluginId">
    <component :is="comp.component" />
  </div>
</template>
```

### 4.4 插件设置表单

```vue
<!-- 通用插件设置渲染器 -->
<template>
  <NForm>
    <template v-for="field in fields" :key="field.key">
      <PluginFormField :field="field" v-model="config[field.key]" />
    </template>
  </NForm>
</template>
```

### 4.5 前端页面组件

#### 插件市场

```vue
<!-- views/plugin/market/index.vue -->
<template>
  <div class="p-4">
    <PageHeader title="插件市场">
      <NButton @click="showUpload = true">安装本地插件</NButton>
    </PageHeader>

    <!-- 分类筛选 -->
    <NTabs v-model:value="category">
      <NTabPane name="all" tab="全部" />
      <NTabPane name="site" tab="站点" />
      <NTabPane name="media" tab="媒体" />
      <NTabPane name="download" tab="下载" />
      <NTabPane name="tool" tab="工具" />
    </NTabs>

    <!-- 插件卡片网格 -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <PluginMarketCard
        v-for="plugin in filteredPlugins"
        :key="plugin.id"
        :plugin="plugin"
        @install="handleInstall"
      />
    </div>
  </div>
</template>
```

#### 已安装插件

```vue
<!-- views/plugin/installed/index.vue -->
<template>
  <div class="p-4">
    <PageHeader title="已安装插件" />

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <PluginInstalledCard
        v-for="plugin in installedPlugins"
        :key="plugin.id"
        :plugin="plugin"
        @toggle="handleToggle"
        @config="openConfig"
        @uninstall="handleUninstall"
      />
    </div>
  </div>
</template>
```

---

## 5. 数据库模型

```sql
-- 插件元数据表
CREATE TABLE plugin_manifest (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    author TEXT,
    description TEXT,
    category TEXT,
    tags TEXT, -- JSON
    icon TEXT,
    color TEXT,
    manifest_json TEXT NOT NULL, -- 完整 manifest
    installed_at TIMESTAMP,
    updated_at TIMESTAMP,
    enabled BOOLEAN DEFAULT 0,
    path TEXT NOT NULL -- 插件目录路径
);

-- 插件配置表（每个插件一个 JSON 对象）
CREATE TABLE plugin_config (
    plugin_id TEXT PRIMARY KEY,
    config TEXT NOT NULL, -- JSON
    updated_at TIMESTAMP
);

-- 插件日志表
CREATE TABLE plugin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL,
    level TEXT NOT NULL, -- INFO/WARN/ERROR
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Hook 订阅表
CREATE TABLE plugin_hooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL,
    event TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1
);
```

---

## 6. 实现计划

### Phase 1: 核心框架（5-7 天）

**后端**
1. 创建 `app/plugin_framework/` 目录结构
2. 实现 `PluginManifest` 数据模型和验证
3. 实现 `PluginRegistry`（扫描、安装、卸载）
4. 实现 `PluginSandbox`（动态加载、隔离运行）
5. 实现 `PluginContext` 及子系统（ConfigStore、Notifier、Scheduler）
6. 实现 `HookSystem`（事件注册、触发）
7. 实现 `PluginAPIGateway`（动态路由挂载）
8. 实现 API Router

**前端**
1. 创建 `src/plugin-framework/` 目录
2. 实现 `PluginLoader`（UMD 组件加载）
3. 实现动态路由注册
4. 实现 `PluginSlot` 插槽组件
5. 实现 `PluginFormField` 动态表单字段
6. 创建插件市场页面
7. 创建已安装插件页面
8. 创建插件配置弹窗

### Phase 2: 示例插件（2 天）

1. 创建示例插件包（hello-world）
2. 后端：实现 `BasePlugin` 子类
3. 前端：用 Vue 3 打包 UMD 组件
4. 完整测试安装、启用、配置、卸载流程

### Phase 3: 迁移旧插件（后续迭代）

1. 为旧插件编写兼容包装器
2. 逐步将核心逻辑迁移到新框架
3. 弃用 `_IPluginModule` 体系

---

## 7. 安全考虑

1. **后端沙箱**
   - 插件运行在受限 Python 环境中
   - 禁止访问文件系统（除插件数据目录外）
   - 禁止导入敏感模块（os.system, subprocess 等）
   - 网络请求通过 PluginHttpClient 代理（可审计）

2. **前端隔离**
   - 插件前端组件通过 iframe 或 Shadow DOM 隔离
   - 禁止访问 localStorage/sessionStorage（除插件命名空间）
   - 与主应用通信通过 postMessage 或事件总线

3. **权限控制**
   - 插件声明所需权限，安装时用户确认
   - API 路由受 RBAC 权限保护
   - 敏感操作（删除文件、执行命令）需额外授权

4. **包验证**
   - 安装时验证 manifest.json 格式
   - 验证文件哈希（防止篡改）
   - 限制包大小（最大 10MB）

---

## 8. 文件变更清单

### 新增

| 路径 | 说明 |
|------|------|
| `app/plugin_framework/__init__.py` | 包入口 |
| `app/plugin_framework/registry.py` | 插件注册表 |
| `app/plugin_framework/sandbox.py` | 沙箱运行 |
| `app/plugin_framework/loader.py` | 包加载器 |
| `app/plugin_framework/api_gateway.py` | API 网关 |
| `app/plugin_framework/hook_system.py` | 事件钩子 |
| `app/plugin_framework/models.py` | 数据库模型 |
| `app/plugin_framework/schemas.py` | DTO |
| `app/plugin_framework/context.py` | 插件上下文 |
| `api/routers/plugin_framework.py` | API 路由 |
| `web/frontend/apps/nexus-media/src/plugin-framework/` | 前端框架 |
| `web/frontend/apps/nexus-media/src/views/plugin/market/` | 插件市场 |
| `web/frontend/apps/nexus-media/src/views/plugin/installed/` | 已安装 |

### 修改

| 路径 | 说明 |
|------|------|
| `app/db/models/__init__.py` | 注册新模型 |
| `app/initializer.py` | 初始化插件框架 |
| `api/main.py` | 注册插件 API 路由 |
| `api/deps.py` | 添加 PluginRegistry 依赖 |
