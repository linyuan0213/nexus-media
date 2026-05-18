# Nexus Media 插件管理系统重构设计文档

## 1. 设计目标

### 1.1 现状问题
- 新版前端插件页面尚未完成（配置弹窗显示"开发中"）
- 插件市场页为占位页面
- 前端路由未正式启用（放在 `modules.bak`）
- 插件配置表单缺乏动态渲染能力
- 缺少插件详情页、日志/历史查看
- 插件扩展页面（get_page）在新前端未支持

### 1.2 重构目标
1. **完整的插件市场**：支持浏览、搜索、安装、卸载插件
2. **已安装插件管理**：卡片/列表视图、启用/禁用、配置、查看日志
3. **动态配置表单**：后端声明字段，前端自动渲染
4. **插件扩展页面**：支持插件自定义页面嵌入
5. **插件日志/历史**：运行时数据可视化
6. **移动端适配**：所有页面支持响应式布局

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  插件市场    │ 已安装插件   │ 插件配置    │   插件扩展页面     │
│  PluginMarket│ PluginList  │ PluginConfig│   PluginPage      │
└──────┬──────┴──────┬──────┴──────┬──────┴─────────┬─────────┘
       │             │             │                │
       └─────────────┴──────┬──────┴────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      API 层 (FastAPI)                        │
├─────────────────────────────────────────────────────────────┤
│  GET    /api/plugin/plugins          获取所有插件           │
│  GET    /api/plugin/installed        获取已安装插件         │
│  POST   /api/plugin/install          安装插件               │
│  POST   /api/plugin/uninstall        卸载插件               │
│  POST   /api/plugin/config           保存插件配置           │
│  POST   /api/plugin/state            获取插件状态           │
│  POST   /api/plugin/page             获取插件扩展页面       │
│  POST   /api/plugin/history          获取插件历史数据       │
│  POST   /api/plugin/method           执行插件方法           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    业务层 (PluginService)                     │
├─────────────────────────────────────────────────────────────┤
│  get_plugins()      扫描所有插件类                           │
│  get_installed()    获取已安装插件及配置                     │
│  install()          安装插件（加入列表+实例化）              │
│  uninstall()        卸载插件（移除列表+停止）                │
│  save_config()      保存配置并重载                           │
│  get_state()        获取插件运行状态                         │
│  get_history()      获取插件历史记录                         │
│  run_method()       反射调用插件方法                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  核心层 (PluginManager)                       │
├─────────────────────────────────────────────────────────────┤
│  __load_plugins()    扫描并加载插件类                        │
│  start_service()     启动插件服务                            │
│  stop_service()      停止所有插件                            │
│  reload_plugin()     重载单个插件                            │
│  run_plugin()        运行插件方法                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  插件层 (_IPluginModule)                      │
├─────────────────────────────────────────────────────────────┤
│  get_fields()        声明配置字段                            │
│  init_config()       初始化/重载配置                         │
│  stop_service()      停止服务                                │
│  get_state()         获取状态                                │
│  get_page()          扩展页面                                │
│  get_history()       历史数据                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 后端设计

### 3.1 插件元数据扩展

在 `_IPluginModule` 基类新增/规范以下属性：

```python
class _IPluginModule(metaclass=ABCMeta):
    # 现有属性
    module_name: str           # 插件名称
    module_desc: str           # 插件描述
    module_icon: str           # 图标（lucide 图标名）
    module_color: str          # 主题色
    module_version: str        # 版本
    module_author: str         # 作者
    author_url: str            # 作者主页
    module_order: int          # 排序
    
    # 新增属性
    module_category: str       # 分类：system / media / download / site / tool
    module_tags: list          # 标签：["签到", "同步", "通知"]
    module_readme: str         # README 内容（支持 Markdown）
    module_changelog: str      # 更新日志
    module_requires: list      # 依赖插件列表
    module_compatible: dict    # 兼容性：{"nexus-media": ">=3.0"}
```

### 3.2 配置字段 DSL

`get_fields()` 返回标准字段定义，前端根据类型自动渲染：

```python
@staticmethod
@abstractmethod
def get_fields():
    return {
        "enabled": {
            "type": "switch",
            "label": "启用插件",
            "default": False,
        },
        "cron": {
            "type": "cron",
            "label": "执行周期",
            "placeholder": "0 8 * * *",
            "help": "Cron 表达式，留空则不定时执行",
        },
        "sites": {
            "type": "select",
            "label": "选择站点",
            "options": "sites",  # 特殊值，从系统获取站点列表
            "multiple": True,
        },
        "notify": {
            "type": "switch",
            "label": "发送通知",
            "default": True,
        },
        "webhook_url": {
            "type": "input",
            "label": "Webhook URL",
            "placeholder": "https://...",
            "required": True,
        },
    }
```

支持的字段类型：
| 类型 | 前端组件 | 说明 |
|------|---------|------|
| `switch` | NSwitch | 布尔开关 |
| `input` | NInput | 文本输入 |
| `textarea` | NInput(type=textarea) | 多行文本 |
| `number` | NInputNumber | 数字输入 |
| `select` | NSelect | 单选下拉 |
| `multi_select` | NSelect(multiple) | 多选下拉 |
| `cron` | NCron（自定义） | Cron 表达式输入 |
| `password` | NInput(type=password) | 密码输入 |
| `file` | NUpload | 文件上传 |
| `json` | NCodeEditor / NInput | JSON 配置 |
| `divider` | NDivider | 分组分割线 |

### 3.3 API 接口设计

```yaml
/api/plugin:
  
  GET /plugins:
    summary: 获取所有插件（市场）
    response:
      code: 0
      data:
        - id: AutoSignIn
          name: 站点自动签到
          desc: 自动签到站点获取魔力值
          icon: lucide:calendar-check
          color: hsl(145, 75%, 42%)
          version: "1.2"
          author: Nexus Media
          category: site
          tags: ["签到", "定时任务"]
          installed: true
          enabled: true
          state: true
          order: 1
          readme: "..."
          changelog: "..."
  
  GET /installed:
    summary: 获取已安装插件（含配置）
    response:
      code: 0
      data:
        - id: AutoSignIn
          name: 站点自动签到
          config: {...}           # 当前配置值
          fields: {...}           # 字段定义
          state: true             # 运行状态
          history_count: 128      # 历史记录数
  
  POST /install:
    body: { "plugin_id": "AutoSignIn" }
    response: { code: 0, data: { message: "安装成功" } }
  
  POST /uninstall:
    body: { "plugin_id": "AutoSignIn" }
    response: { code: 0, data: { message: "卸载成功" } }
  
  POST /config:
    body: { "plugin_id": "AutoSignIn", "config": {...} }
    response: { code: 0, data: { message: "保存成功" } }
  
  GET /{plugin_id}/state:
    response: { code: 0, data: { state: true, message: "运行正常" } }
  
  GET /{plugin_id}/history:
    query: { page: 1, page_size: 20 }
    response: { code: 0, data: { total: 128, items: [...] } }
  
  POST /{plugin_id}/method:
    body: { "method": "sign_in", "args": {} }
    response: { code: 0, data: { result: "..." } }
  
  GET /{plugin_id}/page:
    response: { code: 0, data: { title: "签到记录", html: "..." } }
```

### 3.4 PluginService 扩展

```python
class PluginService:
    def __init__(self, plugin_manager=None, plugin_repo=None):
        self._pm = plugin_manager or PluginManager()
        self._repo = plugin_repo or PluginRepository()
    
    def get_plugins(self, category=None, search=None) -> List[PluginDTO]:
        """获取插件列表（支持分类过滤和搜索）"""
        
    def get_installed(self) -> List[InstalledPluginDTO]:
        """获取已安装插件（含配置和字段定义）"""
        
    def install(self, plugin_id: str) -> ResultDTO:
        """安装插件"""
        
    def uninstall(self, plugin_id: str) -> ResultDTO:
        """卸载插件"""
        
    def save_config(self, plugin_id: str, config: dict) -> ResultDTO:
        """保存配置并重载"""
        
    def get_history(self, plugin_id: str, page=1, page_size=20) -> PageDTO:
        """分页获取插件历史"""
        
    def run_method(self, plugin_id: str, method: str, args: dict) -> ResultDTO:
        """执行插件方法"""
```

---

## 4. 前端设计

### 4.1 路由结构

```typescript
// router/routes/modules/plugin.ts
export default {
  path: '/plugin',
  name: 'Plugin',
  meta: { title: '插件中心', icon: 'lucide:puzzle' },
  children: [
    {
      path: 'market',
      name: 'PluginMarket',
      component: () => import('#/views/plugin/market/index.vue'),
      meta: { title: '插件市场', icon: 'lucide:store' },
    },
    {
      path: 'installed',
      name: 'PluginInstalled',
      component: () => import('#/views/plugin/installed/index.vue'),
      meta: { title: '已安装', icon: 'lucide:plug' },
    },
    {
      path: ':id/config',
      name: 'PluginConfig',
      component: () => import('#/views/plugin/config/index.vue'),
      meta: { title: '插件配置', hideInMenu: true },
    },
  ],
};
```

### 4.2 页面设计

#### 4.2.1 插件市场 (PluginMarket)

布局：
- 顶部：搜索栏 + 分类筛选标签（全部/系统/媒体/下载/站点/工具）
- 主体：卡片网格布局
- 每张卡片：图标 + 名称 + 描述 + 作者 + 版本 + 安装按钮

交互：
- 点击卡片打开详情抽屉（Drawer）：README + 更新日志 + 安装按钮
- 已安装插件显示"已安装"标签，可跳转配置

#### 4.2.2 已安装插件 (PluginInstalled)

布局：
- 视图切换：网格 / 列表
- 排序：按名称 / 按分类 / 最近更新
- 每张卡片/每行：图标 + 名称 + 描述 + 开关（启用/禁用）+ 配置按钮 + 日志按钮 + 卸载按钮

交互：
- 开关：即时保存启用状态
- 配置按钮：打开配置弹窗
- 日志按钮：打开历史记录弹窗
- 卸载：确认弹窗后卸载

#### 4.2.3 插件配置 (PluginConfig)

动态表单渲染器 `PluginConfigForm`：

```vue
<template>
  <NForm :model="config" label-placement="left" :label-width="140">
    <template v-for="(field, key) in fields" :key="key">
      <!-- switch -->
      <NFormItem v-if="field.type === 'switch'" :label="field.label">
        <NSwitch v-model:value="config[key]" />
      </NFormItem>
      
      <!-- input -->
      <NFormItem v-else-if="field.type === 'input'" :label="field.label">
        <NInput v-model:value="config[key]" :placeholder="field.placeholder" />
      </NFormItem>
      
      <!-- select -->
      <NFormItem v-else-if="field.type === 'select'" :label="field.label">
        <NSelect 
          v-model:value="config[key]" 
          :options="resolveOptions(field)"
          :multiple="field.multiple"
        />
      </NFormItem>
      
      <!-- cron -->
      <NFormItem v-else-if="field.type === 'cron'" :label="field.label">
        <PluginCronInput v-model:value="config[key]" />
      </NFormItem>
      
      <!-- divider -->
      <NDivider v-else-if="field.type === 'divider'">
        {{ field.label }}
      </NDivider>
    </template>
  </NForm>
</template>
```

#### 4.2.4 插件历史 (PluginHistory)

弹窗/抽屉形式：
- 表格展示历史记录（时间、类型、内容、状态）
- 支持分页
- 支持清空历史

### 4.3 组件清单

| 组件 | 路径 | 说明 |
|------|------|------|
| PluginMarketCard | views/plugin/components/MarketCard.vue | 市场卡片 |
| PluginInstalledCard | views/plugin/components/InstalledCard.vue | 已安装卡片 |
| PluginInstalledListItem | views/plugin/components/InstalledListItem.vue | 列表项 |
| PluginConfigForm | views/plugin/components/ConfigForm.vue | 动态配置表单 |
| PluginHistoryDrawer | views/plugin/components/HistoryDrawer.vue | 历史记录抽屉 |
| PluginDetailDrawer | views/plugin/components/DetailDrawer.vue | 详情抽屉 |
| PluginCronInput | views/plugin/components/CronInput.vue | Cron 输入器 |

---

## 5. 数据模型

### 5.1 PluginDTO

```typescript
interface PluginDTO {
  id: string;                    // 插件类名
  name: string;                  // 显示名称
  desc: string;                  // 描述
  icon: string;                  // lucide 图标名
  color: string;                 // 主题色
  version: string;               // 版本
  author: string;                // 作者
  authorUrl: string;             // 作者主页
  category: string;              // 分类
  tags: string[];                // 标签
  order: number;                 // 排序
  installed: boolean;            // 是否已安装
  enabled: boolean;              // 是否启用
  state: boolean;                // 运行状态
  readme?: string;               // README
  changelog?: string;            // 更新日志
  requires?: string[];           // 依赖
}
```

### 5.2 InstalledPluginDTO

```typescript
interface InstalledPluginDTO extends PluginDTO {
  config: Record<string, any>;   // 当前配置
  fields: Record<string, FieldDef>; // 字段定义
  historyCount: number;          // 历史记录数
}

interface FieldDef {
  type: string;                  // 字段类型
  label: string;                 // 标签
  default?: any;                 // 默认值
  placeholder?: string;          // 占位符
  options?: Option[] | string;   // 选项或数据源
  multiple?: boolean;            // 是否多选
  required?: boolean;            // 是否必填
  help?: string;                 // 帮助文本
}
```

### 5.3 PluginHistoryDTO

```typescript
interface PluginHistoryDTO {
  id: number;
  pluginId: string;
  key: string;
  value: string;
  date: string;
}
```

---

## 6. 生命周期管理

```
┌─────────────────────────────────────────────────────────────────┐
│                         插件生命周期                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    安装     ┌──────────┐    启用     ┌─────────┐│
│   │  未安装   │ ──────────> │  已安装   │ ──────────> │  运行中  ││
│   │          │            │  (禁用)   │            │         ││
│   └──────────┘            └────┬─────┘            └────┬────┘│
│       ^                        │                       │      │
│       │       卸载             │      禁用             │      │
│       └────────────────────────┘                       │      │
│                                                        │      │
│       ^────────────────────────────────────────────────┘      │
│                      停止服务                                  │
│                                                                │
│   状态转换触发：                                                │
│   - 安装：加入 UserInstalledPlugins，实例化，init_config()      │
│   - 卸载：从 UserInstalledPlugins 移除，stop_service()          │
│   - 启用：config.enabled = true，reload_plugin()                │
│   - 禁用：config.enabled = false，stop_service()                │
│   - 配置更新：save_config()，reload_plugin()                    │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 扩展机制

### 7.1 页面扩展

插件通过 `get_page()` 返回自定义 HTML，前端通过 iframe 或 v-html 嵌入：

```python
def get_page(self):
    return {
        "title": "签到记录",
        "html": self.render_signin_history(),
    }
```

前端展示：
- 在已安装插件卡片上显示"查看页面"按钮
- 点击打开抽屉/弹窗展示 HTML 内容
- 支持简单的数据表格、图表等

### 7.2 事件扩展

现有 `@EventHandler.register` 机制不变，新增事件类型标准化：

```python
class EventType:
    PluginInstall = "plugin.install"
    PluginUninstall = "plugin.uninstall"
    PluginConfigChange = "plugin.config_change"
    DownloadComplete = "download.complete"
    MediaScraped = "media.scraped"
    # ... 现有事件
```

### 7.3 API 扩展

插件可注册自定义 API 路由（未来支持）：

```python
def register_routes(self, router: APIRouter):
    @router.post("/my-plugin/action")
    def do_action():
        return {"result": "ok"}
```

---

## 8. 实现计划

### Phase 1：后端基础（2-3 天）

1. **扩展 `_IPluginModule` 基类**
   - 新增 `module_category`, `module_tags`, `module_readme`, `module_changelog`
   - 规范 `get_fields()` 返回格式
   
2. **扩展 `PluginService`**
   - 新增 `get_plugins()`, `get_history()`, `get_page()`
   - 完善 DTO 转换
   
3. **重构 `api/routers/plugin.py`**
   - 使用 RESTful 风格路径
   - 统一返回格式
   
4. **数据迁移**
   - 确保现有插件配置兼容

### Phase 2：前端基础（3-4 天）

1. **API 模块**
   - 重构 `api/modules/plugin.ts`
   - 定义 TypeScript 接口
   
2. **路由配置**
   - 启用 `plugin.ts` 路由
   - 配置菜单
   
3. **插件市场页**
   - 卡片布局
   - 搜索/筛选
   - 详情抽屉
   
4. **已安装插件页**
   - 网格/列表切换
   - 启用开关
   - 配置/历史/卸载按钮

### Phase 3：高级功能（2-3 天）

1. **动态配置表单**
   - 实现 `PluginConfigForm` 组件
   - 支持所有字段类型
   - Cron 输入器
   
2. **插件历史**
   - 历史记录表格
   - 分页
   - 清空
   
3. **扩展页面**
   - 支持 `get_page()` 渲染
   
4. **移动端适配**
   - 响应式布局
   - 触摸优化

### Phase 4：测试与优化（2 天）

1. 单元测试
2. 集成测试
3. 性能优化
4. 文档完善

---

## 9. 文件变更清单

### 后端

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/plugins/modules/_base.py` | 修改 | 扩展基类属性 |
| `app/plugins/plugin_manager.py` | 修改 | 完善加载逻辑 |
| `app/services/plugin_service.py` | 重写 | 重构服务层 |
| `app/schemas/plugin.py` | 新增 | DTO 定义 |
| `api/routers/plugin.py` | 重写 | RESTful API |
| `app/db/models/plugin.py` | 修改 | 历史表扩展 |

### 前端

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/api/modules/plugin.ts` | 重写 | API 封装 |
| `src/router/routes/modules/plugin.ts` | 新增 | 路由配置 |
| `src/views/plugin/market/index.vue` | 重写 | 市场页 |
| `src/views/plugin/installed/index.vue` | 重写 | 已安装页 |
| `src/views/plugin/config/index.vue` | 新增 | 配置页 |
| `src/views/plugin/components/*.vue` | 新增 | 公共组件 |
| `src/store/plugin.ts` | 重写 | Pinia Store |

---

## 10. 兼容性说明

- **向后兼容**：现有插件无需修改即可工作
- **配置兼容**：现有 `SystemConfig` 存储格式不变
- **API 兼容**：旧版 API 保留但标记为 deprecated
- **前端兼容**：旧版模板页面保留，新版页面并行运行
