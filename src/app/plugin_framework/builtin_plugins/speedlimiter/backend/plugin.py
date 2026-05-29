"""
SpeedLimiter Plugin v2
媒体服务器播放状态改变时，根据设置对下载器进行限速
"""

import contextlib
import time

from app.helper.security_helper import SecurityHelper
from app.plugin_framework.context import PluginContext
from app.di import container


class SpeedLimiterPlugin:
    """下载器限速插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._downloader = container.downloader_core()
        self._mediaserver = container.media_server()
        self._playing_flag = False
        self._limit_enabled = False
        self._download_limit = 0
        self._upload_limit = 0
        self._download_unlimit = 0
        self._upload_unlimit = 0
        self._auto_limit = False
        self._bandwidth = 0
        self._allocation_ratio = []
        self._limited_downloader_ids = []
        self._notify = False
        self._unlimited_ips = {"ipv4": "0.0.0.0/0", "ipv6": "::/0"}

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("下载器限速插件已启用")
        self._load_config()
        self._start_service()

    def on_disable(self):
        self.ctx.info("下载器限速插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._load_config()
                self._start_service()
        elif event == "webhook.emby":
            self._handle_webhook("emby", data)
        elif event == "webhook.jellyfin":
            self._handle_webhook("jellyfin", data)
        elif event == "webhook.plex":
            self._handle_webhook("plex", data)

    def _load_config(self):
        config = self._get_config()
        try:
            self._bandwidth = int(float(config.get("bandwidth") or 0)) * 1000000
        except Exception:
            self._bandwidth = 0

        self._auto_limit = bool(self._bandwidth)

        try:
            self._download_limit = int(float(config.get("download_limit") or 0))
        except Exception:
            self._download_limit = 0

        try:
            self._upload_limit = int(float(config.get("upload_limit") or 0))
        except Exception:
            self._upload_limit = 0

        self._limit_enabled = bool(self._download_limit or self._upload_limit or self._auto_limit)
        self._limited_downloader_ids = config.get("downloaders") or []
        if not self._limited_downloader_ids:
            self._limit_enabled = False

        self._unlimited_ips["ipv4"] = config.get("ipv4") or "0.0.0.0/0"
        self._unlimited_ips["ipv6"] = config.get("ipv6") or "::/0"
        if "0.0.0.0/0" in self._unlimited_ips["ipv4"] and "::/0" in self._unlimited_ips["ipv6"]:
            self._limit_enabled = False

        try:
            self._download_unlimit = int(float(config.get("download_unlimit") or 0))
        except Exception:
            self._download_unlimit = 0

        try:
            self._upload_unlimit = int(float(config.get("upload_unlimit") or 0))
        except Exception:
            self._upload_unlimit = 0

        ratio = config.get("allocation_ratio")
        if ratio:
            try:
                self._allocation_ratio = [int(i) for i in ratio.split(":")]
            except Exception:
                self.ctx.warn("分配比例含有:外非数字字符，执行均分")
                self._allocation_ratio = []
        else:
            self._allocation_ratio = []

        self._notify = bool(config.get("notify"))

    def _start_service(self):
        if not self._limit_enabled:
            return
        interval = int(self._get_config().get("interval") or 300)
        self.ctx.schedule_interval("check_playing", self._check_playing_sessions, seconds=interval)
        self.ctx.info("播放限速服务启动")

    def _stop_service(self):
        with contextlib.suppress(Exception):
            self.ctx.remove_schedule("check_playing")

    def _handle_webhook(self, server_type, data):
        if not self._limit_enabled:
            return

        mediaserver_type = self._mediaserver.get_type()
        if server_type == "emby" and mediaserver_type == "emby":
            if data.get("Event") in ["playback.start", "playback.stop"]:
                self._check_playing_sessions(time_check=False, message=data.get("Title", ""))
        elif server_type == "jellyfin" and mediaserver_type == "jellyfin":
            if data.get("NotificationType") in ["PlaybackStart", "PlaybackStop"]:
                self._check_playing_sessions(time_check=False)
        elif server_type == "plex" and mediaserver_type == "plex":
            if data.get("event") in ["media.play", "media.stop"]:
                time.sleep(3)
                self._check_playing_sessions(time_check=False)

    def _check_playing_sessions(self, time_check=True, message=""):
        mediaserver_type = self._mediaserver.get_type()
        playing_sessions = self._mediaserver.get_playing_sessions() or []
        total_bit_rate = 0

        if mediaserver_type == "emby":
            for session in playing_sessions:
                if (
                    not SecurityHelper.allow_access(self._unlimited_ips, session.get("RemoteEndPoint"))
                    and session.get("NowPlayingItem", {}).get("MediaType") == "Video"
                ):
                    total_bit_rate += int(session.get("NowPlayingItem", {}).get("Bitrate") or 0)
        elif mediaserver_type == "jellyfin":
            for session in playing_sessions:
                if (
                    not SecurityHelper.allow_access(self._unlimited_ips, session.get("RemoteEndPoint"))
                    and session.get("NowPlayingItem", {}).get("MediaType") == "Video"
                ):
                    media_streams = session.get("NowPlayingItem", {}).get("MediaStreams") or []
                    for media_stream in media_streams:
                        total_bit_rate += int(media_stream.get("BitRate") or 0)
        elif mediaserver_type == "plex":
            for session in playing_sessions:
                if (
                    not SecurityHelper.allow_access(self._unlimited_ips, session.get("address"))
                    and session.get("type") == "Video"
                ):
                    total_bit_rate += int(session.get("bitrate") or 0)
        else:
            return

        _playing_flag = bool(total_bit_rate)

        if _playing_flag:
            if not time_check and not self._auto_limit and _playing_flag == self._playing_flag:
                return
            if self._auto_limit:
                self._calc_limit(total_bit_rate)
        else:
            if not time_check and _playing_flag == self._playing_flag:
                return

        _log = True
        if time_check and _playing_flag == self._playing_flag:
            _log = False

        limited_downloader_confs, limited_allocation_ratio = self._check_limited_downloader()
        if not limited_downloader_confs:
            self.ctx.warn("未有启用的限速下载器")
            return

        limit_log = self._speed_limit(
            downloader_confs=limited_downloader_confs,
            allocation_ratio=limited_allocation_ratio,
            playing_flag=_playing_flag,
        )

        self._playing_flag = _playing_flag

        if _log:
            for log_info in limit_log:
                self.ctx.info(f"{'播放' if _playing_flag else '未播放'}限速：{log_info}")
            if self._notify:
                limit_text = "\n".join(limit_log)
                title = (
                    f"[{'定时检查' if time_check else mediaserver_type}{'开始' if _playing_flag else '停止'}播放限速]"
                )
                self.ctx.notify(title=title, text=f"{message}\n{limit_text}")

    def _calc_limit(self, total_bit_rate):
        if not total_bit_rate:
            return
        residual_bandwidth = self._bandwidth - total_bit_rate
        if residual_bandwidth < 0:
            self._upload_limit = 10
        else:
            self._upload_limit = int(residual_bandwidth / 8 / 1024)

    def _check_limited_downloader(self):
        limited_downloader_confs = []
        limited_allocation_ratio = []

        if self._allocation_ratio and len(self._allocation_ratio) != len(self._limited_downloader_ids):
            self._allocation_ratio = []
            self.ctx.warn("分配比例配置错误，与限速下载器数量不一致，执行均分")

        downloader_confs_dict = self._downloader.get_downloader_conf_simple()
        for i in range(len(self._limited_downloader_ids)):
            did = self._limited_downloader_ids[i]
            downloader_conf = downloader_confs_dict.get(did)
            if downloader_conf and downloader_conf.get("enabled"):
                limited_downloader_confs.append(downloader_conf)
                if self._allocation_ratio:
                    limited_allocation_ratio.append(self._allocation_ratio[i])

        return limited_downloader_confs, limited_allocation_ratio

    def _speed_limit(self, downloader_confs, allocation_ratio, playing_flag):
        if not downloader_confs:
            return []

        limit_log = []
        allocation_count = sum(allocation_ratio) if allocation_ratio else len(downloader_confs)

        for i in range(len(downloader_confs)):
            downloader_conf = downloader_confs[i]
            downloader_name = downloader_conf.get("name")

            if playing_flag:
                if self._auto_limit:
                    if not allocation_ratio:
                        upload_limit = int(self._upload_limit / allocation_count)
                    else:
                        upload_limit = int(self._upload_limit * allocation_ratio[i] / allocation_count)
                    upload_limit = max(upload_limit, 10)
                else:
                    upload_limit = self._upload_limit
                download_limit = self._download_limit
            else:
                upload_limit = self._upload_unlimit
                download_limit = self._download_unlimit

            self._downloader.set_speed_limit(
                downloader_id=downloader_conf.get("id"), download_limit=download_limit, upload_limit=upload_limit
            )

            log_info = f"{downloader_name}"
            if upload_limit:
                log_info += f" 上传：{upload_limit}KB/s"
            if download_limit:
                log_info += f" 下载：{download_limit}KB/s"
            if not upload_limit and not download_limit:
                log_info += " 不限速"
            limit_log.append(log_info)

        return limit_log
