import os

# -*- coding: utf-8 -*-
"""
TorrentMark Plugin v2
标记种子是否是PT
"""
from datetime import datetime
from threading import Event

import pytz

from app.plugin_framework.context import PluginContext
from app.schemas.download import Torrent
from app.services.downloader_core import DownloaderCore as Downloader


class TorrentMarkPlugin:
    """种子标记插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._downloader = Downloader()
        self._event = Event()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("种子标记插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("种子标记插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行标记"""
        self.ctx.info("手动触发种子标记")
        self._do_mark()

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        cron = config.get("cron")
        onlyonce = config.get("onlyonce", False)

        if not enable and not onlyonce:
            return

        if cron:
            self.ctx.info(f"标记服务启动，周期：{cron}")
            self.ctx.schedule_cron("mark", self._do_mark, cron=str(cron))

        if onlyonce:
            self.ctx.info("标记服务启动，立即运行一次")
            run_date = datetime.now(tz=pytz.timezone(os.environ.get("TZ")))
            self.ctx.schedule_date("mark_once", self._do_mark, run_date=run_date)
            self.ctx.set_config("onlyonce", False)

    def _stop_service(self):
        self._event.set()
        try:
            self.ctx.remove_schedule("mark")
            self.ctx.remove_schedule("mark_once")
        except Exception:
            pass
        self._event.clear()

    def _do_mark(self):
        config = self._get_config()
        enable = config.get("enable", False)
        downloaders = config.get("downloaders", [])

        if not enable or not downloaders:
            self.ctx.warn("标记服务未启用或未配置下载器")
            return

        for downloader_id in downloaders:
            if self._event.is_set():
                self.ctx.info("标记服务停止")
                return

            self.ctx.info(f"开始扫描下载器：{downloader_id} ...")
            torrents = self._downloader.get_completed_torrents(downloader_id=downloader_id)
            if not torrents:
                self.ctx.info(f"下载器 {downloader_id} 没有已完成种子")
                continue

            self.ctx.info(f"下载器 {downloader_id} 已完成种子数：{len(torrents)}")
            for torrent in torrents:
                if self._event.is_set():
                    self.ctx.info("标记服务停止")
                    return

                hash_str = torrent.id
                torrent_tags = set(torrent.labels)
                pt_flag = self._is_pt(torrent)
                torrent_tags.discard("")

                if pt_flag:
                    torrent_tags.discard("BT")
                    torrent_tags.add("PT")
                else:
                    torrent_tags.add("BT")
                    torrent_tags.discard("PT")

                self._downloader.set_torrents_tag(downloader_id=downloader_id, ids=hash_str, tags=list(torrent_tags))

        self.ctx.info("标记任务执行完成")

    @staticmethod
    def _is_pt(torrent: Torrent):
        tracker_list = torrent.trackers
        if len(tracker_list) <= 5:
            keywords = ["secure=", "passkey=", "totheglory", "credential=", "tracker.zhuque.in", "announce?uid="]
            if any(keyword in tracker_list[0] for keyword in keywords):
                return True
        return False
