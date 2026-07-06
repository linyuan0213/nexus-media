from threading import Event
from typing import Any

from app.plugin_framework.context import PluginContext


class SiteRatioPlugin:
    def __init__(self, ctx: PluginContext, site_service: Any):
        self.ctx = ctx
        self._site_service = site_service
        self._event = Event()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("站点分享率监控插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("站点分享率监控插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        self.ctx.info("手动触发分享率检查")
        self._do_check(manual=True)

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        cron = config.get("cron", "30 8 * * *")

        if not enable:
            return

        self.ctx.info(f"分享率监控启动，周期：{cron}")
        self.ctx.schedule_cron("check", self._do_check, cron=str(cron))

    def _stop_service(self):
        self._event.set()
        self.ctx.remove_schedule("check")
        self._event.clear()

    def _do_check(self, manual=False):
        config = self._get_config()
        enable = config.get("enable", False)

        if not enable and not manual:
            return

        threshold = float(config.get("ratio_threshold", 1.0))
        exclude = config.get("exclude_sites", [])
        if isinstance(exclude, str):
            exclude = [s.strip() for s in exclude.split(",") if s.strip()]
        exclude_sites = set(exclude)
        notify_recovery = config.get("notify_on_recovery", False)

        builtin_sites = set()
        try:
            all_sites = self._site_service.get_sites(basic=True)
            for s in all_sites:
                if s.get("source") == "builtin" and s.get("enabled") is not False:
                    builtin_sites.add(s.get("name", ""))
        except Exception:
            self.ctx.error("获取站点列表失败")

        try:
            statistics = self._site_service.get_site_user_statistics(sites=None, encoding="DICT")
        except Exception as e:
            self.ctx.error(f"获取站点统计数据失败：{e}")
            return

        self.ctx.info(f"获取到 {len(statistics)} 个站点统计数据")

        if not statistics:
            self.ctx.warn("未获取到站点统计数据")
            return

        below_sites = []
        above_sites = []
        checked = 0
        skipped = []
        for item in statistics:
            if isinstance(item, dict):
                site_name = str(item.get("site_name", ""))
                if not site_name:
                    continue
                if site_name in exclude_sites:
                    skipped.append(f"{site_name}(已排除)")
                    continue
                if builtin_sites and site_name not in builtin_sites:
                    skipped.append(f"{site_name}(非内置站点)")
                    continue
                ratio_str = str(item.get("ratio", "0"))
                try:
                    ratio = float(ratio_str.replace(",", ""))
                except ValueError:
                    ratio = 0.0
                if ratio <= 0:
                    skipped.append(f"{site_name}(无数据)")
                    continue
                checked += 1
                if ratio < threshold:
                    below_sites.append((site_name, ratio))
                elif notify_recovery:
                    above_sites.append((site_name, ratio))

        if skipped:
            self.ctx.info(f"跳过 {len(skipped)} 个站点：{', '.join(skipped)}")
        self.ctx.info(f"已检查 {checked} 个站点，{len(below_sites)} 个低于阈值 {threshold}")

        if below_sites:
            self._notify(below_sites, threshold)

        if notify_recovery and above_sites:
            previous = self.ctx.read_data("previous_below.txt") or ""
            prev_set = set(previous.strip().split(",")) if previous.strip() else set()
            current_below = {name for name, _ in below_sites}
            recovered = prev_set - current_below
            if recovered:
                recovered_names = ", ".join(sorted(recovered))
                self.ctx.info(f"以下站点分享率已恢复：{recovered_names}")
            self.ctx.write_data("previous_below.txt", ",".join(sorted(current_below)))

    def _notify(self, below_sites, threshold):
        below_sites.sort(key=lambda x: x[1])
        lines = [f"以下站点分享率低于 {threshold}：", ""]
        for name, ratio in below_sites:
            lines.append(f"  · {name}：{ratio:.3f}")
        text = "\n".join(lines)
        self.ctx.notify(title="站点分享率告警", text=text)
        self.ctx.info(f"已发送分享率告警：{len(below_sites)} 个站点低于 {threshold}")
