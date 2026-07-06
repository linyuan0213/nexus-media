import re
from threading import Event
from typing import Any

from app.plugin_framework.context import PluginContext


class TrackerManagerPlugin:
    def __init__(self, ctx: PluginContext, downloader: Any):
        self.ctx = ctx
        self._downloader = downloader
        self._event = Event()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("Tracker 管理插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("Tracker 管理插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        self.ctx.info("手动触发 Tracker 替换")
        self._do_replace()

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        cron = config.get("cron", "0 3 * * *")

        if not enable:
            return

        self.ctx.info(f"Tracker 管理启动，周期：{cron}")
        self.ctx.schedule_cron("replace", self._do_replace, cron=str(cron))

    def _stop_service(self):
        self._event.set()
        self.ctx.remove_schedule("replace")
        self._event.clear()

    def _parse_rules(self, rules_text):
        rules = []
        if not rules_text:
            return rules
        for line in str(rules_text).strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "->" in line:
                src, dst = line.split("->", 1)
                src = src.strip()
                dst = dst.strip()
                if src and dst:
                    rules.append((src, dst))
        return rules

    def _do_replace(self):
        config = self._get_config()
        enable = config.get("enable", False)

        if not enable:
            return

        rules_text = config.get("rules", "")
        if not rules_text:
            self.ctx.warn("未配置替换规则")
            return

        downloaders = config.get("downloaders", [])
        if not downloaders:
            self.ctx.warn("未选择下载器")
            return

        rules = self._parse_rules(rules_text)
        if not rules:
            self.ctx.warn("未能解析出有效规则")
            return

        self.ctx.info(f"已加载 {len(rules)} 条替换规则")

        total_replaced = 0
        for did in downloaders:
            if self._event.is_set():
                break
            try:
                torrents = self._downloader.get_torrents(downloader_id=str(did))
            except Exception as e:
                self.ctx.error(f"获取下载器 {did} 种子列表失败：{e}")
                continue

            if not torrents:
                self.ctx.info(f"下载器 {did} 无种子")
                continue

            replaced_count = 0
            for torrent in torrents:
                if self._event.is_set():
                    break
                hash_str = getattr(torrent, "id", None)
                if not hash_str:
                    continue
                trackers = self._downloader.get_torrent_trackers(tid=hash_str, downloader_id=str(did))
                if not trackers:
                    continue

                for src, dst in rules:
                    if self._event.is_set():
                        break
                    for tracker_url in trackers:
                        if tracker_url and re.search(src, tracker_url):
                            try:
                                self._downloader.edit_torrent_tracker(
                                    tid=hash_str, old_url=tracker_url, new_url=dst, downloader_id=str(did)
                                )
                                replaced_count += 1
                                self.ctx.info(f"[{did}] {tracker_url} → {dst}")
                            except Exception as e:
                                self.ctx.error(f"[{did}] 替换失败 {tracker_url}：{e}")

            self.ctx.info(f"下载器 {did} 完成，替换 {replaced_count} 个 tracker")
            total_replaced += replaced_count

        self.ctx.info(f"Tracker 替换完成，共替换 {total_replaced} 个")
