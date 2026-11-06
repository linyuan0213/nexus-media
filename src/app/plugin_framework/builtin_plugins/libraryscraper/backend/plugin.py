"""
LibraryScraper Plugin v2
定时对媒体库进行刮削
"""

import os
import re
import shutil
import time
from threading import Event

import log
from app.core.settings import settings
from app.media import meta_info
from app.media.scraper import Scraper
from app.media.scraper.poster_quality import (
    has_legacy_watermark_marker,
    is_bad_poster,
    synthetic_poster_path,
)
from app.plugin_framework.context import PluginContext

_BACKUP_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".nfo")


class LibraryScraperPlugin:
    """媒体库刮削插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._scraper = Scraper(
            media_service=ctx.media_service,
            metadata_service=getattr(ctx, "metadata_service", None),
            metadata_gateway=getattr(ctx, "metadata_gateway", None),
        )
        self._event = Event()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("媒体库刮削插件已启用")
        self._normalize_config()
        self._start_service()

    def _normalize_config(self):
        """补齐旧配置：空模式/旧 no_force 统一迁移为增量模式 missing."""
        config = self._get_config()
        changed = False
        mode = str(config.get("mode") or "")
        if mode not in ("missing", "repair", "force_all"):
            config["mode"] = "repair"
            changed = True
        if not str(config.get("cron") or "").strip():
            config["cron"] = "0 8 * * *"
            changed = True
        if "backup_before_repair" not in config:
            config["backup_before_repair"] = True
            changed = True
        if "batch_limit" not in config:
            config["batch_limit"] = 0
            changed = True
        if changed:
            self.ctx.set_all_config(config)

    def on_disable(self):
        self.ctx.info("媒体库刮削插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._normalize_config()
                self._stop_service()
                self._start_service()
        elif event == "media.scraped":
            event_info = data or {}
            path = event_info.get("path")
            force = event_info.get("force")
            if path:
                mode = "force_all" if force else "no_force"
                self._scraper.folder_scraper(path, mode=mode)

    def run(self):
        """立即运行刮削"""
        self.ctx.info("手动触发媒体库刮削")
        self._do_scrape()

    def _start_service(self):
        config = self._get_config()
        cron = config.get("cron")

        if not cron:
            return

        if cron:
            self.ctx.info(f"刮削服务启动，周期：{cron}")
            self.ctx.schedule_cron("scrape", self._do_scrape, cron=str(cron))

    def _stop_service(self):
        self._event.set()
        try:
            self.ctx.remove_schedule("scrape")
            self.ctx.remove_schedule("scrape_once")
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Plugin]忽略异常: {e}")
        self._event.clear()

    @staticmethod
    def _poster_is_bad(path: str) -> bool:
        """横版、占位图或由剧照裁出的伪海报都不满足要求."""
        return is_bad_poster(path)

    @staticmethod
    def _is_incomplete_dir(path: str, files: list[str]) -> bool:
        poster_name = next(
            (
                name
                for name in files
                if name.lower().endswith((".jpg", ".png", ".webp")) and name.lower().startswith("poster")
            ),
            None,
        )
        if not poster_name or LibraryScraperPlugin._poster_is_bad(os.path.join(path, poster_name)):
            return True
        if synthetic_poster_path(path) or has_legacy_watermark_marker(path):
            # 旧版横版裁切 poster / 40 字节旧水印标记，必须重新取竖版正面封面。
            return True
        nfo = next((name for name in files if name.lower().endswith(".nfo")), None)
        if not nfo:
            return True
        try:
            text = open(os.path.join(path, nfo), encoding="utf-8-sig").read()
        except OSError:
            return True
        # 空 <actor> 标签也算缺失，必须至少有一个非空演员名。
        if not re.search(r"<actor>.*?<name>[^<]+</name>", text, re.S):
            return True
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        if title is None or not re.sub(r"<[^>]+>|\s", "", title.group(1)):
            return True
        title_text = title.group(1)
        if any(
            marker in title_text
            for marker in (
                "アダルト動画サイト",
                "MGS動画",
                "ページが見つかりません",
                "404 Not Found",
                "MissAV",
                "FREE JAV BT",
                "JavBus",
                "JavDB",
            )
        ):
            return True
        # 成人来源经常没有简介；有标题和演员即可，plot 为空不再触发无限重刮。
        return False

    @staticmethod
    def _media_files(files: list[str]) -> list[str]:
        return [name for name in files if name.lower().endswith((".mp4", ".mkv", ".avi", ".wmv", ".ts"))]

    def _iter_media_dirs(self, paths: list[str], exclude_path: str | None):
        for root in paths:
            if not root or not os.path.isdir(root):
                continue
            for dir_path, _dirs, files in os.walk(root):
                if exclude_path and os.path.abspath(dir_path).startswith(os.path.abspath(exclude_path)):
                    continue
                if self._media_files(files):
                    yield dir_path, files

    def _iter_incomplete_dirs(self, paths: list[str], exclude_path: str | None):
        for dir_path, files in self._iter_media_dirs(paths, exclude_path):
            if self._is_incomplete_dir(dir_path, files):
                yield dir_path

    @staticmethod
    def _backup_targets(dir_path: str) -> list[str]:
        try:
            names = os.listdir(dir_path)
        except OSError:
            return []
        return [
            os.path.join(dir_path, name)
            for name in names
            if name == ".watermark" or name.lower().endswith(_BACKUP_SUFFIXES)
        ]

    def _backup_dir(self, root: str, dir_path: str, run_id: str) -> str | None:
        """写入前备份 poster/thumb/fanart/NFO/.watermark；失败则跳过该目录."""
        config = self._get_config()
        base = str(config.get("backup_path") or "").strip() or os.path.join(
            settings.data_path, "plugin_backups", "libraryscraper"
        )
        relative = os.path.relpath(dir_path, root)
        target = os.path.join(base, run_id, relative)
        try:
            os.makedirs(target, exist_ok=True)
            for source in self._backup_targets(dir_path):
                shutil.copy2(source, os.path.join(target, os.path.basename(source)))
        except OSError as exc:
            log.error(f"[LibraryScraper]备份失败，跳过写入 {dir_path}: {exc}")
            return None
        return target

    @staticmethod
    def _matches_only_codes(dir_path: str, only_codes: set[str]) -> bool:
        if not only_codes:
            return True
        name = os.path.basename(dir_path).upper()
        return any(code in name for code in only_codes)

    def _emit_refresh(self, dir_path: str, files: list[str]) -> None:
        """逐条目通知刷新，已有 Emby/Jellyfin 条目才会重读 NFO/海报/演员."""
        if not hasattr(self.ctx, "emit"):
            return
        for name in self._media_files(files):
            file_path = os.path.join(dir_path, name)
            info = self._scraper.profile_media_info(file_path)
            if info is None:
                info = meta_info(name)
            self.ctx.emit(
                "media.library_synced",
                {
                    "target_path": file_path,
                    "dest": dir_path,
                    "media_info": info.to_dict(),
                },
            )

    def _do_scrape(self):
        config = self._get_config()
        scraper_path = config.get("scraper_path", [])
        exclude_path = config.get("exclude_path")
        mode = config.get("mode") or "repair"
        if mode == "missing":
            mode = "repair"

        if isinstance(scraper_path, str):
            scraper_path = scraper_path.split("\n")

        backup_enabled = config.get("backup_before_repair", True) is not False
        batch_limit = max(0, int(config.get("batch_limit") or 0))
        only_codes = {code.strip().upper() for code in str(config.get("only_codes") or "").split(",") if code.strip()}
        run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        processed = 0
        self.ctx.info(f"开始刮削媒体库：{scraper_path} ...")
        for path in scraper_path:
            if not path:
                continue
            if self._event.is_set():
                self.ctx.info("媒体库刮削服务停止")
                return
            if mode == "repair":
                targets = self._iter_incomplete_dirs([path], exclude_path)
            else:
                targets = (dir_path for dir_path, _files in self._iter_media_dirs([path], exclude_path))
            for dir_path in targets:
                if self._event.is_set():
                    return
                if not self._matches_only_codes(dir_path, only_codes):
                    continue
                backup = self._backup_dir(path, dir_path, run_id) if backup_enabled else ""
                if backup is None:
                    continue
                if backup:
                    self.ctx.info(f"已备份到 {backup}")
                self.ctx.info(f"补齐缺失元数据：{dir_path}")
                self._scraper.folder_scraper(path=dir_path, mode="force_all")
                self._emit_refresh(dir_path, os.listdir(dir_path))
                processed += 1
                if batch_limit and processed >= batch_limit:
                    self.ctx.info(f"已达到单次批量上限 {batch_limit}，停止")
                    return
        self.ctx.info("媒体库刮削完成")
