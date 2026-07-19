"""
IYUUAutoSeed Plugin v2
基于IYUU官方Api实现自动辅种
"""

import time
from threading import Event
from typing import Any

import log
from app.plugin_framework.builtin_plugins.iyuuautoseed.backend.iyuu.iyuu_helper import IyuuHelper
from app.plugin_framework.context import PluginContext
from app.schemas.download import Torrent, TorrentStatus
from app.sites.torrent import Torrent as TorrentUtil
from app.utils.json_utils import JsonUtils


class IYUUAutoSeedPlugin:
    """IYUU自动辅种插件"""

    def __init__(
        self,
        ctx: PluginContext,
        downloader: Any,
        sites: Any,
    ):
        self.ctx = ctx
        self._downloader = downloader
        self._sites = sites
        self.iyuuhelper: IyuuHelper | None = None
        self._scheduler_thread = None
        self._stop_event = Event()
        self._recheck_torrents: dict[str, list[str]] = {}
        self._torrent_tags = ["已整理", "辅种"]
        self.total = 0
        self.realtotal = 0
        self.success = 0
        self.exist = 0
        self.fail = 0
        self.cached = 0

    # ——— 站点解析 —————————————————————

    def _resolve_local_site(self, sid: Any = None, nickname: str = "", slug: str = "") -> tuple[dict | None, Any]:
        """解析 IYUU 站点对应的 (本地站点配置, 站点定义)：
        1. 按 IYUU base_url 匹配；2. 域名不一致时（如 api.m-team.cc ≠ api.m-team.io）
        按站点定义的中文名/标识回退匹配。"""
        engine = self.ctx.site_engine
        if sid and self.iyuuhelper:
            base_url, _, _ = self.iyuuhelper.get_torrent_url(sid)
            if base_url:
                site = self._sites.get_sites(siteurl=base_url)
                if isinstance(site, dict) and site.get("id"):
                    return site, engine.get_by_url(base_url) if engine else None
        if engine:
            site_def = (engine.get_by_name(nickname) if nickname else None) or (
                engine.get_by_name(slug) if slug else None
            )
            if site_def:
                api_cfg = getattr(site_def, "api", None) if site_def else None
                if api_cfg and api_cfg.base_url:
                    site = self._sites.get_sites(siteurl=api_cfg.base_url)
                    if isinstance(site, dict) and site.get("id"):
                        return site, site_def
                # HTML 站点定义（无 api）按站点名查找本地配置
                sites = self._sites.get_sites_by_name(site_def.name)
                if sites:
                    return sites[0], site_def
        return None, None

    # ——— 缓存 —————————————————————

    def _load_cache(self):
        content = self.ctx.read_data("cache.json")
        if content:
            return JsonUtils.loads(content)
        return {"error_caches": [], "success_caches": [], "permanent_error_caches": []}

    def _save_cache(self, data):
        self.ctx.write_data("cache.json", JsonUtils.dumps(data, ensure_ascii=False, indent=2))

    # ——— 持久化绑定记录 —————————————————————

    def _get_bound_sites(self) -> dict:
        content = self.ctx.read_data("bound_sites.json")
        if not content:
            return {}
        try:
            data = JsonUtils.loads(content)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_bound_site(self, site: str, uid: str) -> None:
        data = self._get_bound_sites()
        data[site] = {"uid": uid, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.ctx.write_data("bound_sites.json", JsonUtils.dumps(data, ensure_ascii=False, indent=2))

    # ——— 主流程 —————————————————————

    def on_enable(self):
        self.ctx.info("IYUU自动辅种插件已启用")
        self.ctx.register_api("bindable_sites", self._api_bindable_sites)
        self.ctx.register_api("bind_site", self._api_bind_site)
        self._start_service()

    def on_disable(self):
        self.ctx.info("IYUU自动辅种插件已禁用")
        if self._scheduler_thread:
            self._stop_event.set()
        self.ctx.unregister_all_apis()

    def _start_service(self):
        config = self._get_config()
        token = config.get("token")
        if token:
            self.iyuuhelper = IyuuHelper(
                token=token,
                site_engine=self.ctx.site_engine,
                rate_limit=config.get("rate_limit") or "",
            )
        cron = config.get("cron", "0 0 * * *")
        if self._scheduler_thread:
            self._stop_event.set()
        self._stop_event.clear()
        self._scheduler_thread = self.ctx.schedule_cron("iyuuautoseed", lambda: self._do_seed(manual=False), cron)

    def _get_config(self):
        return self.ctx.get_config() or {}

    # ——— 辅种核心 —————————————————————

    def _do_seed(self, manual=False):
        config = self._get_config()
        enable = config.get("enable", False)
        token = config.get("token")
        downloaders = config.get("downloaders", [])
        sites_cfg = config.get("sites", [])
        nolabels = config.get("nolabels")
        notify = config.get("notify", False)
        clearcache = config.get("clearcache", False)

        if (not enable and not manual) or not token or not downloaders:
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

        for did in downloaders:
            if not self._downloader.get_downloader_conf(did):
                continue
            completed_torrents = self._downloader.get_completed_torrents(downloader_id=did)
            if not completed_torrents:
                continue
            if nolabels:
                nolabel_list = [label.strip() for label in nolabels.split(",") if label.strip()]
                completed_torrents = [t for t in completed_torrents if not set(t.labels or []) & set(nolabel_list)]
            hashs = [t.id for t in completed_torrents if t.progress == 100]
            for chunk in self._chunks(hashs, 200):
                self._seed_torrents(chunk, did, sites_cfg, error_caches, success_caches)

        self._recheck_completed(downloaders)
        self._save_cache(
            {
                "error_caches": error_caches,
                "success_caches": success_caches,
                "permanent_error_caches": permanent_error_caches,
            }
        )
        self.ctx.info(
            f"总共需要辅种的种子数：{self.total}\n"
            f"总请求数：{len(success_caches) + len(error_caches)}\n"
            f"实际可辅种数：{self.realtotal}\n"
            f"成功：{self.success}\n"
            f"已存在：{self.exist}\n"
            f"失败：{self.fail}(缓存数量：{self.cached})"
        )
        if notify:
            self.ctx.notify("辅种任务完成", f"成功：{self.success}，已存在：{self.exist}，失败：{self.fail}")

    @staticmethod
    def _chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    # ——— 种子下载 —————————————————————

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
                    continue
                if seed.get("info_hash") in success_caches or seed.get("info_hash") in error_caches:
                    continue

                success = self._download_torrent(seed, downloader_id, save_paths.get(current_hash), sites_cfg)
                if success:
                    success_torrents.append(seed.get("info_hash"))

            if success_torrents:
                self._save_seed_history(current_hash, downloader_id, success_torrents)

        self.ctx.info(f"下载器 {downloader_id} 辅种完成")

    def _resolve_download_url(self, site_info: dict, site_def, torrent_id: Any) -> str | None:
        """通过站点引擎解析下载链接（统一处理 genDlToken/api_chained/html/template）"""
        if not site_def:
            return None
        tid = str(torrent_id)
        page_url = site_def.get_page_url(tid)
        if not page_url:
            page_url = f"{site_def.domain}/details.php?id={tid}"
        try:
            return self.ctx.site_engine.resolve_download_url(page_url, site_info)
        except Exception as e:
            log.warn(f"[IYUU] 解析下载链接失败 {site_info.get('name')}: {e}")
            return None

    def _download_torrent(self, seed, downloader_id, save_path, sites_cfg):
        if not self.iyuuhelper:
            self.fail += 1
            self.cached += 1
            return False
        self.total += 1

        site_info, site_def = self._resolve_local_site(sid=seed.get("sid"))
        if not site_info:
            return False
        if not sites_cfg or str(site_info.get("id")) not in sites_cfg:
            return False

        self.realtotal += 1
        if self._downloader.get_torrents(downloader_id=downloader_id, ids=[seed.get("info_hash")]):
            self.exist += 1
            return False

        # 通过站点引擎解析下载链接（genDlToken/api/HTML 统一处理）
        download_url = self._resolve_download_url(site_info, site_def, seed.get("torrent_id"))
        if not download_url:
            self.fail += 1
            return False

        # 下载 .torrent 文件（引擎统一认证）
        torrent_util = TorrentUtil(site_engine=self.ctx.site_engine)
        try:
            _file_path, content, _dl_files_folder, _dl_files, _retmsg = torrent_util.get_torrent_info(
                url=download_url,
                cookie=site_info.get("cookie", ""),
                api_key=site_info.get("api_key", ""),
                bearer_token=site_info.get("bearer_token", ""),
                ua=site_info.get("ua", ""),
                referer=None,
                proxy=site_info.get("proxy") or False,
            )
        except Exception:
            self.fail += 1
            return False
        if not content:
            self.fail += 1
            return False

        # 添加到下载器
        client = self._downloader.get_downloader(downloader_id)
        if not client:
            self.fail += 1
            return False
        ret = client.add_torrent(
            content=content,
            is_paused=True,
            download_dir=save_path,
            tag=self._torrent_tags,
        )
        if ret:
            self.success += 1
            if downloader_id not in self._recheck_torrents:
                self._recheck_torrents[downloader_id] = []
            self._recheck_torrents[downloader_id].append(seed.get("info_hash"))
            return True
        self.fail += 1
        return False

    # ——— 已完成种子校验 —————————————————————

    @staticmethod
    def _can_seeding(torrent: Torrent):
        return torrent.progress == 100 and torrent.status in [
            TorrentStatus.Uploading,
            TorrentStatus.Paused,
            TorrentStatus.Stopped,
            TorrentStatus.Checking,
            TorrentStatus.Queued,
        ]

    def _recheck_completed(self, downloaders):
        for downloader_id, hash_list in self._recheck_torrents.items():
            if downloader_id not in downloaders:
                continue
            torrents = self._downloader.get_torrents(downloader_id=downloader_id, ids=hash_list)
            if not torrents:
                continue
            for torrent in torrents:
                if torrent.size == 0:
                    continue
                if self._can_seeding(torrent):
                    self._downloader.start_torrents(downloader_id=downloader_id, ids=[torrent.id])

    # ——— 种子历史 —————————————————————

    def _save_seed_history(self, current_hash, downloader_id, success_torrents):
        try:
            content = self.ctx.read_data("seed_history.json")
            if content:
                history = JsonUtils.loads(content)
            else:
                history = {}
            key = f"{current_hash}_{downloader_id}"
            history[key] = success_torrents
            self.ctx.write_data("seed_history.json", JsonUtils.dumps(history, ensure_ascii=False))
        except Exception as e:
            log.debug(f"[IYUU] 保存种子历史失败: {e}")

    # ——— 自定义 API —————————————————————

    def _api_helper(self) -> IyuuHelper | None:
        config = self._get_config()
        token = config.get("token")
        if not token:
            return None
        return IyuuHelper(
            token=token,
            site_engine=self.ctx.site_engine,
            rate_limit=config.get("rate_limit") or "",
        )

    def _api_bindable_sites(self, params: dict) -> dict:
        helper = self._api_helper()
        if not helper:
            return {"success": False, "message": "未配置 IYUU Token"}
        sites, err = helper.get_auth_sites()
        if err:
            return {"success": False, "message": f"获取可绑定站点失败: {err}"}
        bound_sites = self._get_bound_sites()
        for row in sites:
            bound = bound_sites.get(row.get("site"))
            if bound:
                row["bound"] = True
                row["bound_uid"] = bound.get("uid")
                row["bound_time"] = bound.get("time")
            local, site_def = self._resolve_local_site(
                sid=row.get("id"),
                nickname=row.get("nickname") or "",
                slug=row.get("site") or "",
            )
            if not local:
                continue
            row["local"] = True
            if local.get("api_key"):
                row["api_key"] = local.get("api_key")
            api_cfg = getattr(site_def, "api", None) if site_def else None
            if api_cfg and isinstance(api_cfg.auth, dict) and api_cfg.auth.get("type"):
                row["auth_type"] = api_cfg.auth["type"]
        return {"success": True, "data": sites}

    def _api_bind_site(self, params: dict) -> dict:
        helper = self._api_helper()
        if not helper:
            return {"success": False, "message": "未配置 IYUU Token"}
        site = params.get("site")
        passkey = params.get("passkey")
        uid = params.get("uid")
        if not site or not passkey or not uid:
            return {"success": False, "message": "site/passkey/uid 不能为空"}
        result, msg = helper.bind_site(site, passkey, uid)
        if msg:
            return {"success": False, "message": msg}
        self._save_bound_site(site, uid)
        return {"success": True, "message": "绑定成功", "data": result}
