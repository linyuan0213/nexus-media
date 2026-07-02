# Hello World 示例插件

这是 Nexus Media 插件框架 v2 的示例插件，展示前后端一体化插件包的完整结构。

## 插件结构

```
hello_world/
├── manifest.json          # 插件元数据
├── backend/
│   ├── __init__.py
│   └── plugin.py          # 后端主类
└── frontend/
    └── index.mjs          # 前端 DI 组件包
```

## manifest.json 说明

- `id`: 插件唯一标识（字母、数字、下划线）
- `backend.entry`: 后端入口，格式 `module.path:ClassName`
- `frontend.routes`: 注册的独立页面路由
- `frontend.settings`: 设置表单字段定义
- `frontend.slots`: 嵌入核心页面的插槽组件

## 后端开发

后端类通过 `ctx`（PluginContext）访问系统能力：

```python
class HelloWorldPlugin:
    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        self.ctx.log_info("插件已启用")
        self.ctx.notify("标题", "内容")

    def on_hook(self, event, data):
        pass
```

### 生命周期方法

- `on_enable()`: 插件启用时调用
- `on_disable()`: 插件禁用时调用
- `on_hook(event, data)`: 订阅的事件触发时调用

### PluginContext API

- `ctx.get_config(key, default)`: 读取配置
- `ctx.set_config(key, value)`: 写入配置
- `ctx.log_info/warn/error/debug(msg)`: 日志记录
- `ctx.notify(title, text, image)`: 发送消息通知
- `ctx.schedule_cron(job_id, func, cron)`: 注册定时任务
- `ctx.emit(event, data)`: 触发全局事件

## 前端开发

前端组件通过 DI（依赖注入）模式获取宿主能力。默认导出函数接收 `host` 参数，返回组件映射。

### DI 模式示例

```javascript
export default function(host) {
  const { h, ref, onMounted } = host.Vue;

  const DashboardWidget = {
    setup() {
      return () => h('div', 'Hello from plugin!');
    }
  };

  return { DashboardWidget };
}
```

### host 可用能力

| 属性 | 说明 |
|------|------|
| `host.Vue` | Vue 3 完整 API（h, ref, computed, watch, onMounted 等） |
| `host.IconifyIcon` | `@vben/icons` 的 IconifyIcon 组件 |
| `host.api` | HTTP 客户端（axios 封装） |

### 插槽组件

插槽组件会被渲染到核心页面的指定位置：

```json
{
  "slots": [
    {
      "target": "dashboard.home",
      "position": "after_stats",
      "component": "DashboardWidget"
    }
  ]
}
```

## 打包安装

将插件目录打包为 zip：

```bash
cd examples/plugins
zip -r hello_world-v1.0.0.zip hello_world/
```

然后在 Nexus Media 前端「插件市场」→「安装本地插件」上传 zip 包。

## 调试

1. 安装插件后，在「已安装插件」页面启用
2. 查看后端日志确认 `on_enable()` 被调用
3. 在前端 Dashboard 查看插件注入的组件
4. 通过「配置」按钮修改配置，观察 `on_hook` 响应
