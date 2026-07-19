"""
IYUUAutoSeed Plugin v2
基于IYUU官方Api实现自动辅种
"""

import time
from threading import Event
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import log
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.plugin_framework.builtin_plugins.iyuuautoseed.backend.iyuu.iyuu_helper import IyuuHelper
from app.plugin_framework.context import PluginContext
from app.schemas.download import Torrent, TorrentStatus
from app.utils.config_tools import get_proxies
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
        self.ctx.register_api("bindable_sites", self._api_bindable_sites)
        self.ctx.register_api("bind_site", self._api_bind_site)
        self._start_service()

    def _api_helper(self) -> IyuuHelper | None:
        """按当前配置构建 IyuuHelper（供自定义 API 使用）"""
        config = self._get_config()
        token = config.get("token")
        if not token:
            return None
        return IyuuHelper(
            token=token,
            site_engine=self.ctx.site_engine,
            rate_limit=config.get("rate_limit") or "",
        )

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

    def _get_bound_sites(self) -> dict:
        """读取本地已绑定站点记录 {site: {uid, time}}"""
        content = self.ctx.read_data("bound_sites.json")
        if not content:
            return {}
        try:
            data = JsonUtils.loads(content)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_bound_site(self, site: str, uid: str) -> None:
        """记录绑定成功的站点"""
        data = self._get_bound_sites()
        data[site] = {"uid": uid, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.ctx.write_data("bound_sites.json", JsonUtils.dumps(data, ensure_ascii=False, indent=2))

    def _api_bindable_sites(self, params: dict) -> dict:
        """获取支持鉴权绑定的站点列表，并关联本地站点配置（预填 api_key、标记凭证类型）"""
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
        """绑定站点：site/passkey/uid"""
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
        self._do_seed(manual=True)

    def _start_service(self):
        config = self._get_config()
        enable = config.get("enable", False)
        cron = config.get("cron")
        token = config.get("token")

        if not enable:
            return
        if not token:
            self.ctx.warn("未配置IYUU Token")
            return

        self.iyuuhelper = IyuuHelper(
            token=token,
            site_engine=self.ctx.site_engine,
            rate_limit=config.get("rate_limit") or "",
        )

        if cron:
            self.ctx.info(f"辅种服务启动，周期：{cron}")
            self.ctx.schedule_cron("seed", self._do_seed, cron=str(cron))

        # 种子校验服务
        self.ctx.schedule_interval("check_recheck", self._check_recheck, minutes=3)

    def _stop_service(self):
        self._event.set()
        try:
            self.ctx.remove_schedule("seed")
            self.ctx.remove_schedule("seed_once")
            self.ctx.remove_schedule("check_recheck")
        except Exception as e:  # noqa: BLE001
            log.debug(f"[plugin]忽略异常: {e}")
        self._event.clear()

    def _load_cache(self):
        content = self.ctx.read_data("cache.json")
        if content:
            try:
                return JsonUtils.loads(content)
            except Exception as e:  # noqa: BLE001
                log.debug(f"[plugin]忽略异常: {e}")
        return {"error_caches": [], "success_caches": [], "permanent_error_caches": []}

    def _save_cache(self, data):
        self.ctx.write_data("cache.json", JsonUtils.dumps(data, ensure_ascii=False, indent=2))

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

        self._save_cache(
            {
                "error_caches": error_caches,
                "success_caches": success_caches,
                "permanent_error_caches": permanent_error_caches,
            }
        )

        if notify and (self.success or self.fail):
            self.ctx.notify(
                title="[IYUU自动辅种任务完成]",
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
        return torrent.progress == 100 and torrent.status in [
            TorrentStatus.Uploading,
            TorrentStatus.Paused,
            TorrentStatus.Stopped,
            TorrentStatus.Checking,
            TorrentStatus.Queued,
        ]

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

    @staticmethod
    def _build_download_url(is_https: Any, host: str, download_page: str, torrent_id: Any) -> str | None:
        """拼接种子下载链接：填充种子ID，剥离仍为占位符的凭证参数（{passkey}/{uid} 等，由 Cookie 认证替代）。
        路径中仍残留占位符（如 dl/{}/{passkey}）时返回 None，表示该站点无法辅种。"""
        scheme = "http" if is_https == 0 else "https"
        path = download_page.replace("{}", str(torrent_id))
        url = f"{scheme}://{host}/{path.lstrip('/')}"
        parts = urlsplit(url)
        if parts.query:
            kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if "{" not in v]
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
        if "{" in url:
            return None
        return url

    def _download_torrent(self, seed, downloader_id, save_path, sites_cfg):
        if not self.iyuuhelper:
            self.fail += 1
            self.cached += 1
            return False
        self.total += 1
        site_url, download_page, is_https = self.iyuuhelper.get_torrent_url(seed.get("sid"))
        if not site_url or not download_page:
            self.fail += 1
            self.cached += 1
            return False
        if "genDlToken" in download_page:
            self.ctx.debug(f"{site_url} 需要 genDlToken 流程，暂不支持辅种")
            self.fail += 1
            self.cached += 1
            return False

        site_info, _ = self._resolve_local_site(sid=seed.get("sid"))
        if not site_info:
            return False
        if not sites_cfg or str(site_info.get("id")) not in sites_cfg:
            return False

        self.realtotal += 1
        # 检查hash是否已在下载器中
        if self._downloader.get_torrents(downloader_id=downloader_id, ids=[seed.get("info_hash")]):
            self.exist += 1
            return False

        # 拼接种子下载链接
        torrent_url = self._build_download_url(is_https, site_url, download_page, seed.get("torrent_id"))
        if not torrent_url:
            self.ctx.debug(f"{site_url} 下载链接包含无法填充的凭证占位符，跳过：{download_page}")
            self.fail += 1
            return False
        proxies = get_proxies() if site_info.get("proxy") else None
        proxy_url = proxies.get("http") if proxies else None
        engine = self.ctx.site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        # 站点级限流：复用站点 NOTE 中配置的 rate_limit（与站点引擎一致）
        rl_kwargs = {}
        if rate_limiter:
            site_rate = rate_limiter.get_rate(str(site_info.get("id")))
            if site_rate:
                rl_kwargs = {"rate_limit_key": f"site:{site_info.get('id')}", "rate_limit_rate": site_rate[0]}
        try:
            res = HttpClient(
                config=HttpClientConfig(proxy_url=proxy_url),
                rate_limiter=rate_limiter_engine,
            ).get(
                torrent_url,
                headers={"User-Agent": site_info.get("ua")},
                auth=CookieAuth(site_info.get("cookie")),
                **rl_kwargs,
            )
        except Exception:
            self.fail += 1
            return False

        # 服务层无 add_torrent，需通过下载器客户端实例添加
        client = self._downloader.get_downloader(downloader_id)
        if not client:
            self.fail += 1
            return False
        ret = client.add_torrent(
            content=res.content,
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
        else:
            self.fail += 1
            return False

    def _save_seed_history(self, current_hash, downloader_id, success_torrents):
        try:
            content = self.ctx.read_data("seed_history.json")
            if content:
                history = JsonUtils.loads(content)
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
            self.ctx.write_data("seed_history.json", JsonUtils.dumps(history, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ctx.error(f"保存辅种历史失败: {e}")
