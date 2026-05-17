# Weather Widget 插件

展示插件依赖管理功能的示例插件。

## 依赖

- `requests>=2.28.0` - HTTP 请求库
- `pytz` - 时区处理库

依赖在 `manifest.json` 的 `backend.dependencies` 中声明，安装插件时自动检测并安装。

## 功能

- 通过 OpenWeatherMap API 获取天气数据
- 演示插件依赖的自动安装流程

## 配置

- `api_key`: OpenWeatherMap API Key

## 安装

将本目录打包为 zip，通过插件市场安装：

```bash
cd examples/plugins/weather_widget
zip -r weather_widget.zip .
```

然后在 NAS-Tools 插件页面上传安装。
