"""
Weather Widget 示例插件
展示插件依赖管理功能，使用 requests 和 pytz
"""


class WeatherWidgetPlugin:
    """天气插件"""

    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        """启用时调用"""
        self.ctx.log_info("Weather Widget 插件已启用")

    def on_disable(self):
        """禁用时调用"""
        self.ctx.log_info("Weather Widget 插件已禁用")

    def on_hook(self, event, data):
        """事件处理"""
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                api_key = data.get("config", {}).get("api_key", "")
                self.ctx.log_info(f"API Key 已更新: {api_key[:4]}...")

    def fetch_weather(self, city: str = "Beijing") -> dict:
        """获取天气数据（演示依赖使用）"""
        from datetime import datetime

        import pytz
        import requests

        api_key = self.ctx.get_config("api_key", "")
        if not api_key:
            return {"error": "请先在设置中配置 API Key"}

        try:
            # 使用 OpenWeatherMap API 作为示例
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": city,
                "appid": api_key,
                "units": "metric",
                "lang": "zh_cn",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            tz = pytz.timezone("Asia/Shanghai")
            now = datetime.now(tz)

            return {
                "city": data.get("name"),
                "temperature": data.get("main", {}).get("temp"),
                "humidity": data.get("main", {}).get("humidity"),
                "description": data.get("weather", [{}])[0].get("description"),
                "updated_at": now.isoformat(),
            }
        except Exception as e:
            self.ctx.log_error(f"获取天气失败: {e}")
            return {"error": str(e)}

    def get_status(self) -> dict:
        """返回插件状态"""
        return {
            "plugin_id": self.ctx.plugin_id,
            "api_key_configured": bool(self.ctx.get_config("api_key", "")),
        }
