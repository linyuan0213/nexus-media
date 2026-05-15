"""
IYUUAutoSeed Plugin v2
基于IYUU官方Api实现自动辅种
"""

import json
import os
from datetime import datetime, timedelta
from threading import Event

import pytz

from app.core.constants import MT_URL
from app.plugin_framework.builtin_plugins.iyuuautoseed.backend.iyuu.iyuu_helper import IyuuHelper
from app.plugin_framework.context import PluginContext
from app.schemas.download import Torrent
from app.services.downloader_core import DownloaderCore as Downloader
from app.sites import Sites
from app.utils import RequestUtils
from app.utils.config_tools import get_proxies


class IYUUAutoSeedPlugin:
    """IYUU自动辅种插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._downloader = Downloader()
        self._sites = Sites()
        self._event = Event()
        self.iyuuhelper = None
        self._recheck_torrents = {}
        self._is_recheck_running = False
        self._torrent_xpaths = [
            "//form[contains(@action, 'download.php?id=')]/@action",
            "//a[contains(@href, 'download.php?hash=')]/@href",
            "//a[contains(@href, 'download.php?id=')]/@href",
            "//a[@class='index'][contains(@href, '/dl/')]/@href",
        ]
        self._torrent_tags = ["已整理", "辅种"]
        # 统计计数
        self.total = 0
        self.realtotal = 0
        self.success = 0
        self.exist = 0
        self.fail = 0
        self.cached = 0

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("IYUU自动辅种插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("IYUU自动辅种插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行辅种"""
        self.ctx.info("手动触发IYUU辅种")
        self._do_seed()

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        cron = config.get("cron")
        onlyonce = config.get("onlyonce", False)
        token = config.get("token")

        if not enable and not onlyonce:
            return
        if not token:
            self.ctx.warn("未配置IYUU Token")
            return

        self.iyuuhelper = IyuuHelper(token=token)

        if cron:
            self.ctx.info(f"辅种服务启动，周期：{cron}")
            self.ctx.schedule_cron("seed", self._do_seed, cron=str(cron))

        if onlyonce:
            self.ctx.info("辅种服务启动，立即运行一次")
            run_date = datetime.now(tz=pytz.timezone(os.environ.get("TZ") or "UTC")) + timedelta(seconds=3)
            self.ctx.schedule_date("seed_once", self._do_seed, run_date=run_date)
            self.ctx.set_config("onlyonce", False)

        # 种子校验服务
        self.ctx.schedule_interval("check_recheck", self._check_recheck, minutes=3)

    def _stop_service(self):
        self._event.set()
        try:
            self.ctx.remove_schedule("seed")
            self.ctx.remove_schedule("seed_once")
            self.ctx.remove_schedule("check_recheck")
        except Exception:
            pass
        self._event.clear()

    def _load_cache(self):
        content = self.ctx.read_data("cache.json")
        if content:
            try:
                return json.loads(content)
            except Exception:
                pass
        return {"error_caches": [], "success_caches": [], "permanent_error_caches": []}

    def _save_cache(self, data):
        self.ctx.write_data("cache.json", json.dumps(data, ensure_ascii=False, indent=2))

    def _do_seed(self):
        config = self._get_config()
        enable = config.get("enable", False)
        token = config.get("token")
        downloaders = config.get("downloaders", [])
        sites_cfg = config.get("sites", [])
        nolabels = config.get("nolabels")
        notify = config.get("notify", False)
        clearcache = config.get("clearcache", False)

        if not enable or not token or not downloaders:
            self.ctx.warn("辅种服务未启用或未配置")
            return

        cache = self._load_cache()
        if clearcache:
            error_caches = []
            success_caches = cache.get("success_caches", [])
            permanent_error_caches = cache.get("permanent_error_caches", [])
            self.ctx.set_config("clearcache", False)
        else:
            error_caches = cache.get("error_caches", [])
            success_caches = cache.get("success_caches", [])
            permanent_error_caches = cache.get("permanent_error_caches", [])

        self.total = self.realtotal = self.success = self.exist = self.fail = self.cached = 0

        for downloader_id in downloaders:
            self.ctx.info(f"开始扫描下载器 {downloader_id} ...")
            torrents = self._downloader.get_completed_torrents(downloader_id=downloader_id)
            if not torrents:
                self.ctx.info(f"下载器 {downloader_id} 没有已完成种子")
                continue

            hash_strs = []
            for torrent in torrents:
                if self._event.is_set():
                    self.ctx.info("辅种服务停止")
                    return
                hash_str = torrent.id
                if hash_str in error_caches or hash_str in permanent_error_caches:
                    continue
                if nolabels and torrent.labels:
                    skip = any(label in torrent.labels for label in nolabels.split(","))
                    if skip:
                        continue
                hash_strs.append({"hash": hash_str, "save_path": torrent.save_path})

            if hash_strs:
                self.ctx.info(f"总共需要辅种的种子数：{len(hash_strs)}")
                chunk_size = 200
                for i in range(0, len(hash_strs), chunk_size):
                    chunk = hash_strs[i : i + chunk_size]
                    self._seed_torrents(chunk, downloader_id, sites_cfg, error_caches, success_caches)
                self._check_recheck()
            else:
                self.ctx.info("没有需要辅种的种子")

        self._save_cache({
            "error_caches": error_caches,
            "success_caches": success_caches,
            "permanent_error_caches": permanent_error_caches,
        })

        if notify and (self.success or self.fail):
            self.ctx.notify(
                title="【IYUU自动辅种任务完成】",
                text=f"服务器返回可辅种总数：{self.total}\n"
                f"实际可辅种数：{self.realtotal}\n"
                f"已存在：{self.exist}\n"
                f"成功：{self.success}\n"
                f"失败：{self.fail}\n"
                f"{self.cached} 条失败记录已加入缓存",
            )
        self.ctx.info("辅种任务执行完成")

    def _check_recheck(self):
        if not self._recheck_torrents or self._is_recheck_running:
            return
        self._is_recheck_running = True
        config = self._get_config()
        downloaders = config.get("downloaders", [])

        for downloader_id in downloaders:
            recheck_torrents = self._recheck_torrents.get(downloader_id) or []
            if not recheck_torrents:
                continue
            self.ctx.info(f"开始检查下载器 {downloader_id} 的校验任务 ...")
            torrents = self._downloader.get_torrents(downloader_id=downloader_id, ids=recheck_torrents)
            if torrents:
                can_seeding = [t.id for t in torrents if self._can_seeding(t)]
                if can_seeding:
                    self.ctx.info(f"共 {len(can_seeding)} 个任务校验完成，开始辅种 ...")
                    self._downloader.start_torrents(downloader_id=downloader_id, ids=can_seeding)
                    self._recheck_torrents[downloader_id] = list(set(recheck_torrents) - set(can_seeding))
            elif torrents is None:
                self.ctx.info(f"下载器 {downloader_id} 查询校验任务失败")
            else:
                self._recheck_torrents[downloader_id] = []
        self._is_recheck_running = False

    @staticmethod
    def _can_seeding(torrent: Torrent):
        return torrent.progress == 100 and torrent.status in ["pausedUP", "stoppedUP", "checkingUP", "queuedUP"]

    def _seed_torrents(self, hash_strs, downloader_id, sites_cfg, error_caches, success_caches):
        if not hash_strs:
            return
        self.ctx.info(f"下载器 {downloader_id} 开始查询辅种，数量：{len(hash_strs)} ...")
        hashs = [item.get("hash") for item in hash_strs]
        save_paths = {item.get("hash"): item.get("save_path") for item in hash_strs}

        if not self.iyuuhelper:
            self.ctx.warn("IYUU Token 未配置")
            return
        seed_list, msg = self.iyuuhelper.get_seed_info(hashs)
        if not isinstance(seed_list, dict):
            self.ctx.warn(f"当前种子列表没有可辅种的站点：{msg}")
            return

        self.ctx.info(f"IYUU返回可辅种数：{len(seed_list)}")
        for current_hash, seed_info in seed_list.items():
            if not seed_info:
                continue
            seed_torrents = seed_info.get("torrent", [])
            if not isinstance(seed_torrents, list):
                seed_torrents = [seed_torrents]

            success_torrents = []
            for seed in seed_torrents:
                if not seed or not isinstance(seed, dict):
                    continue
                if not seed.get("sid") or not seed.get("info_hash"):
                    continue
                if seed.get("info_hash") in hashs:
                    self.ctx.info(f"{seed.get('info_hash')} 已在下载器中，跳过 ...")
                    continue
                if seed.get("info_hash") in success_caches:
                    continue
                if seed.get("info_hash") in error_caches:
                    continue

                success = self._download_torrent(seed, downloader_id, save_paths.get(current_hash), sites_cfg)
                if success:
                    success_torrents.append(seed.get("info_hash"))

            if success_torrents:
                self._save_seed_history(current_hash, downloader_id, success_torrents)

        self.ctx.info(f"下载器 {downloader_id} 辅种完成")

    def _download_torrent(self, seed, downloader_id, save_path, sites_cfg):
        if not self.iyuuhelper:
            self.fail += 1
            self.cached += 1
            return False
        self.total += 1
        site_url, download_page = self.iyuuhelper.get_torrent_url(seed.get("sid"))
        if site_url and "m-team" in site_url:
            site_url = MT_URL
        if not site_url or not download_page:
            self.fail += 1
            self.cached += 1
            return False

        site_info = self._sites.get_sites(siteurl=site_url)
        if not site_info:
            return False
        if not isinstance(site_info, dict):
            return False
        if sites_cfg and str(site_info.get("id")) not in sites_cfg:
            return False

        self.realtotal += 1
        # 检查hash是否已在下载器中
        if self._downloader.exists_torrents(downloader_id=downloader_id, hash_str=seed.get("info_hash")):  # type: ignore[union-attr]
            self.exist += 1
            return False

        # 下载种子
        torrent_url = download_page.replace("{}", str(seed.get("torrent_id")))
        proxies = get_proxies() if site_info.get("proxy") else None
        res = RequestUtils(
            cookies=site_info.get("cookie"), headers={"User-Agent": site_info.get("ua")}, proxies=proxies
        ).get_res(torrent_url)
        if not res or not res.content:
            self.fail += 1
            return False

        ret = self._downloader.add_torrent(  # type: ignore[union-attr]
            content=res.content,
            downloader_id=downloader_id,
            save_path=save_path,
            is_paused=True,
            tags=self._torrent_tags,
        )
        if ret:
            self.success += 1
            if downloader_id not in self._recheck_torrents:
                self._recheck_torrents[downloader_id] = []
            self._recheck_torrents[downloader_id].append(seed.get("info_hash"))
            return True
        else:
            self.fail += 1
            return False

    def _save_seed_history(self, current_hash, downloader_id, success_torrents):
        try:
            content = self.ctx.read_data("seed_history.json")
            if content:
                history = json.loads(content)
            else:
                history = {}

            seed_history = history.get(current_hash, [])
            found = False
            for h in seed_history:
                if h.get("downloader") == downloader_id:
                    h["torrents"] = list(set(h.get("torrents", []) + success_torrents))
                    found = True
                    break
            if not found:
                seed_history.append({"downloader": downloader_id, "torrents": list(set(success_torrents))})

            history[current_hash] = seed_history
            self.ctx.write_data("seed_history.json", json.dumps(history, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ctx.error(f"保存辅种历史失败: {e}")
