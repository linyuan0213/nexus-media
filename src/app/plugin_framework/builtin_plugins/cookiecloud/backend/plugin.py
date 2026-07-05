"""
CookieCloud Plugin v2
从 CookieCloud 云端同步数据
"""

import contextlib
import re
from collections import defaultdict
from typing import Any

from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
from app.domain.entities.site import SiteEntity
from app.domain.enums import SiteUseType
from app.infrastructure.cache_system import get_cache_manager
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.plugin_framework.context import PluginContext
from app.utils import StringUtils
from app.utils.json_utils import JsonUtils


class CookieCloudPlugin:
    """CookieCloud 同步插件"""

    _ignore_cookies = ["CookieAutoDeleteBrowsingDataCleanup"]

    def __init__(
        self,
        ctx: PluginContext,
        sites: Any,
        index_helper: Any,
        site_repo: Any = None,
    ):
        self.ctx = ctx
        self.sites = sites
        self._site_repo = site_repo or SiteRepositoryAdapter()
        self._index_helper = index_helper
        self._cache = get_cache_manager().get_or_create("plugin_cookiecloud", cache_type="redis")

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("CookieCloud 插件已启用")
        self._start_service()
        self.ctx.register_message_command("cookiecloud", "立即同步 CookieCloud", self._on_cookiecloud_cmd)

    def on_disable(self):
        self.ctx.info("CookieCloud 插件已禁用")
        self._stop_service()
        self.ctx.unregister_message_command("cookiecloud")

    def _on_cookiecloud_cmd(self, client_type, user_id, text):
        self.ctx.info(f"用户 {user_id} 通过 {client_type} 触发 CookieCloud 同步")
        self._cookie_sync()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()
        elif event == "site.cookie_sync":
            self._cookie_save()
        elif event == "site.local_storage_sync":
            self._local_storage_save()

    def run(self):
        self.ctx.info("手动触发 CookieCloud 同步")
        self._cookie_sync()

    def _start_service(self):
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")

        if not enabled:
            self.ctx.info("未启用定时同步，跳过")
            return

        if enabled and cron:
            self.ctx.info(f"CookieCloud 同步服务启动，周期：{cron}")
            try:
                self.ctx.schedule_cron("sync", self._cookie_sync, cron=cron)
            except Exception as e:
                self.ctx.error(f"schedule_cron 失败: {e}")

    def _stop_service(self):
        with contextlib.suppress(Exception):
            self.ctx.remove_schedule("sync")

    @staticmethod
    def is_domain_in_list(domain, domain_list):
        return any(re.search(pattern, domain) for pattern in domain_list)

    def _check_domain(self, domain):
        config = self._get_config()
        blacklist = config.get("blacklist", "")
        whitelist = config.get("whitelist", "")

        if blacklist and self.is_domain_in_list(domain, blacklist.splitlines()):
            self.ctx.debug(f"{domain} 在黑名单中，已排除")
            return False

        if not whitelist:
            return True

        if self.is_domain_in_list(domain, whitelist.splitlines()):
            self.ctx.debug(f"{domain} 在白名单中")
            return True

        return False

    def _download_data(self) -> tuple[dict, str, bool]:
        config = self._get_config()
        server = config.get("server", "")
        key = config.get("key", "")
        password = config.get("password", "")

        if not server or not key or not password:
            return {}, "CookieCloud 参数不正确", False

        if not server.startswith("http"):
            server = f"http://{server}"
        if server.endswith("/"):
            server = server[:-1]

        req_url = f"{server}/get/{key}"
        try:
            with HttpClient(config=HttpClientConfig(default_headers={"Content-Type": "application/json"})) as http:
                ret = http.post(url=req_url, json={"password": password})
            result = ret.json()
            content = {}
            if not result:
                return {}, "", True
            if result.get("cookie_data"):
                content["cookie_data"] = result.get("cookie_data")
            if result.get("local_storage_data"):
                content["local_storage_data"] = result.get("local_storage_data")
            return content, "", True
        except HttpClientError as exc:
            return {}, f"同步 CookieCloud 失败，错误码：{exc.status_code}", False
        except Exception:
            return {}, "CookieCloud 请求失败，请检查服务器地址、用户 KEY 及加密密码是否正确", False

    def _cookie_sync(self):
        self.ctx.info("同步服务开始 ...")
        contents, msg, flag = self._download_data()
        if not flag:
            self.ctx.error(msg)
            self._send_message(msg)
            return
        if not contents:
            self.ctx.info("未从 CookieCloud 获取到数据")
            self._send_message("未从 CookieCloud 获取到数据")
            return

        try:
            update_count, add_count = self._process_cookies(contents if isinstance(contents, dict) else {})
        except Exception as e:
            err_msg = f"处理 Cookie 数据异常: {e}"
            self.ctx.error(err_msg)
            self._send_message(err_msg)
            return

        if not contents.get("local_storage_data"):
            if update_count or add_count:
                msg = f"更新了 {update_count} 个站点的 Cookie 数据，新增了 {add_count} 个站点"
            else:
                msg = "同步完成，但未更新任何站点数据！"
        else:
            msg = f"同步完成：更新了 {update_count} 个站点的 Cookie 数据，新增了 {add_count} 个站点"

        self.ctx.info(msg)

        config = self._get_config()
        if config.get("notify"):
            self._send_message(msg)

    def _cookie_save(self):
        self.ctx.info("开始同步 Cookie 到 Redis ...")
        contents, msg, flag = self._download_data()
        if not flag:
            self.ctx.error(msg)
            return
        if not contents:
            self.ctx.info("未从 CookieCloud 获取到数据")
            return
        self._store_cookies_to_cache(contents if isinstance(contents, dict) else {})
        self.ctx.info("Cookie 同步 Redis 成功")

    def _store_cookies_to_cache(self, contents: dict):
        domain_cookie_groups = defaultdict(list)
        cookie_content = contents.get("cookie_data") or {}
        for _site, cookies in cookie_content.items():
            for cookie in cookies:
                if not self._check_domain(cookie["domain"]):
                    continue
                domain_parts = cookie["domain"].split(".")[-2:]
                domain_key = tuple(domain_parts)
                domain_cookie_groups[domain_key].append(cookie)

        result = {}
        for domain, content_list in domain_cookie_groups.items():
            if not content_list:
                continue

            domain_url = ".".join(domain)
            domain_url = self.ctx.site_engine.normalize_domain(domain_url) or domain_url

            cloudflare_cookie = True
            for content in content_list:
                if content["name"] != "cf_clearance":
                    cloudflare_cookie = False
                    break
            if cloudflare_cookie:
                continue

            cookie_str = ";".join(
                [
                    f"{content.get('name')}={content.get('value')}"
                    for content in content_list
                    if content.get("name") and content.get("name") not in self._ignore_cookies
                ]
            )
            self._cache.set(f"cookie:{domain_url}", cookie_str)
            result[domain_url] = cookie_str

        return result

    def _find_matching_sites(self, domain_url: str) -> list[dict]:
        matched = []
        for site in self.sites.get_sites():
            strict_url = site.get("strict_url", "")
            if not strict_url:
                continue
            site_domain = StringUtils.get_url_domain(strict_url)
            if not site_domain:
                continue
            site_suffix = ".".join(site_domain.split(".")[-2:])
            if site_suffix == domain_url:
                matched.append(site)
        return matched

    def _process_cookies(self, contents: dict):
        domain_cookies = self._store_cookies_to_cache(contents)

        update_count = 0
        add_count = 0
        updated_ids: set[int] = set()

        for domain_url, cookie_str in domain_cookies.items():
            try:
                matched_sites = self._find_matching_sites(domain_url)
                if matched_sites:
                    for site_info in matched_sites:
                        sid = int(site_info.get("id") or 0)
                        if sid and sid not in updated_ids:
                            self._site_repo.update_cookie_ua(sid, cookie=cookie_str)
                            updated_ids.add(sid)
                            update_count += 1
                else:
                    indexer_info = self._index_helper.get_indexer_info(domain_url)
                    if indexer_info:
                        site_pri = self.sites.get_max_site_pri() + 1
                        self._site_repo.insert(
                            SiteEntity(
                                name=indexer_info.get("name"),
                                pri=site_pri,
                                sign_url=indexer_info.get("domain"),
                                cookie=cookie_str,
                                rss_uses=SiteUseType.STATISTIC.value,
                            )
                        )
                        add_count += 1
            except Exception as e:
                self.ctx.error(f"处理域名 {domain_url} 时出错: {e}")

        if update_count or add_count:
            self.sites.refresh()

        return update_count, add_count

    def _local_storage_save(self):
        self.ctx.info("开始同步 LocalStorage ...")
        contents, msg, flag = self._download_data()
        if not flag:
            self.ctx.error(msg)
            return
        if not contents:
            self.ctx.info("未从 CookieCloud 获取到数据")
            return

        local_storage = contents.get("local_storage_data") or {}
        synced = 0
        for site, storage in local_storage.items():
            try:
                if not storage:
                    continue
                if not self._check_domain(site):
                    continue
                for cookie_data in storage:
                    if cookie_data.get("domain") and self._check_domain(cookie_data.get("domain", "")):
                        domain_parts = site.split(".")[-2:]
                        domain_key = tuple(domain_parts)
                        domain_url = ".".join(domain_key)
                        domain_url = self.ctx.site_engine.normalize_domain(domain_url) or domain_url

                        self._cache.set(f"local_storage:{domain_url}", JsonUtils.dumps(storage))
                        synced += 1
            except Exception as e:
                self.ctx.error(f"处理 LocalStorage {site} 时出错: {e}")

        self.ctx.info(f"LocalStorage 同步 Redis 成功，共同步 {synced} 个站点")

    def _send_message(self, msg):
        self.ctx.notify(
            title="[CookieCloud 同步任务执行完成]",
            text=msg,
        )
