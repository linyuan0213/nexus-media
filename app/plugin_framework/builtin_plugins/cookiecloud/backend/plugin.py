# -*- coding: utf-8 -*-
"""
CookieCloud Plugin v2
从 CookieCloud 云端同步数据
"""
import json
import re
from collections import defaultdict
from typing import Union

from app.helper import IndexerHelper
from app.sites import Sites
from app.utils import RequestUtils
from app.utils.cache_system import get_cache_manager
from app.core.constants import MT_URL

from app.plugin_framework.context import PluginContext


class CookieCloudPlugin:
    """CookieCloud 同步插件"""

    _ignore_cookies = ['CookieAutoDeleteBrowsingDataCleanup']

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self.sites = Sites()
        self._index_helper = IndexerHelper()
        self._cache = get_cache_manager().get_or_create(
            "plugin_cookiecloud", cache_type="redis"
        )

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("CookieCloud 插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("CookieCloud 插件已禁用")
        self._stop_service()

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
        """立即运行同步"""
        self.ctx.info("手动触发 CookieCloud 同步")
        self._cookie_sync()

    def _start_service(self):
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")

        if not enabled:
            self.ctx.info("未启用定时同步，跳过")
            return

        # 周期运行
        if enabled and cron:
            self.ctx.info(f"CookieCloud 同步服务启动，周期：{cron}")
            try:
                self.ctx.schedule_cron("sync", self._cookie_sync, cron=cron)
            except Exception as e:
                self.ctx.error(f"schedule_cron 失败: {e}")

    def _stop_service(self):
        try:
            self.ctx.remove_schedule("sync")
        except Exception:
            pass

    @staticmethod
    def is_domain_in_list(domain, domain_list):
        for pattern in domain_list:
            if re.match(pattern, domain):
                return True
        return False

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

    def _download_data(self) -> Union[dict, str, bool]:
        config = self._get_config()
        server = config.get("server", "")
        key = config.get("key", "")
        password = config.get("password", "")

        if not server or not key or not password:
            return {}, "CookieCloud 参数不正确", False

        if not server.startswith("http"):
            server = "http://%s" % server
        if server.endswith("/"):
            server = server[:-1]

        req = RequestUtils(content_type="application/json")
        req_url = "%s/get/%s" % (server, key)
        ret = req.post_res(url=req_url, json={"password": password})

        if ret and ret.status_code == 200:
            result = ret.json()
            content = {}
            if not result:
                return {}, "", True
            if result.get("cookie_data"):
                content['cookie_data'] = result.get("cookie_data")
            if result.get("local_storage_data"):
                content['local_storage_data'] = result.get("local_storage_data")
            return content, "", True
        elif ret:
            return {}, "同步 CookieCloud 失败，错误码：%s" % ret.status_code, False
        else:
            return {}, "CookieCloud 请求失败，请检查服务器地址、用户 KEY 及加密密码是否正确", False

    def _cookie_sync(self):
        """同步站点 Cookie（定时任务入口）"""
        self.ctx.info("同步服务开始 ...")
        contents, msg, flag = self._download_data()
        if not flag:
            self.ctx.error(msg)
            self._send_message(msg)
            return
        if not contents:
            self.ctx.info("未从 CookieCloud 获取到数据")
            self._send_message(msg)
            return

        update_count, add_count = self._process_cookies(contents)

        if update_count or add_count:
            msg = f"更新了 {update_count} 个站点的 Cookie 数据，新增了 {add_count} 个站点"
        else:
            msg = "同步完成，但未更新任何站点数据！"
        self.ctx.info(msg)

        config = self._get_config()
        if config.get("notify"):
            self._send_message(msg)

    def _process_cookies(self, contents: dict):
        domain_cookie_groups = defaultdict(list)
        cookie_content = contents.get("cookie_data")
        for site, cookies in cookie_content.items():
            for cookie in cookies:
                if not self._check_domain(cookie["domain"]):
                    continue
                domain_parts = cookie["domain"].split(".")[-2:]
                domain_key = tuple(domain_parts)
                domain_cookie_groups[domain_key].append(cookie)

        update_count = 0
        add_count = 0

        for domain, content_list in domain_cookie_groups.items():
            if not content_list:
                continue

            domain_url = ".".join(domain)
            if 'm-team' in domain_url:
                domain_url = '.'.join(MT_URL.split('.')[-2:])

            cloudflare_cookie = True
            for content in content_list:
                if content["name"] != "cf_clearance":
                    cloudflare_cookie = False
                    break
            if cloudflare_cookie:
                continue

            cookie_str = ";".join(
                [f"{content.get('name')}={content.get('value')}"
                 for content in content_list
                 if content.get("name") and content.get("name") not in self._ignore_cookies]
            )
            self._cache.set(f'cookie:{domain_url}', cookie_str)

            site_info = self.sites.get_sites_by_suffix(domain_url)
            if site_info:
                success, _, _ = self.sites.test_connection(site_id=site_info.get("id"))
                if not success:
                    self.sites.update_site_cookie(siteid=site_info.get("id"), cookie=cookie_str)
                    update_count += 1
            else:
                indexer_info = self._index_helper.get_indexer_info(domain_url)
                if indexer_info:
                    site_pri = self.sites.get_max_site_pri() + 1
                    self.sites.add_site(
                        name=indexer_info.get("name"),
                        site_pri=site_pri,
                        signurl=indexer_info.get("domain"),
                        cookie=cookie_str,
                        rss_uses='T'
                    )
                    add_count += 1

        return update_count, add_count

    def _local_storage_save(self):
        """同步 LocalStorage 到 Redis（事件触发）"""
        self.ctx.info("开始同步 LocalStorage ...")
        contents, msg, flag = self._download_data()
        if not flag:
            self.ctx.error(msg)
            self._send_message(msg)
            return
        if not contents:
            self.ctx.info("未从 CookieCloud 获取到数据")
            self._send_message(msg)
            return

        local_storage = contents.get("local_storage_data") or {}
        for site, storage in local_storage.items():
            if not storage:
                continue
            if not self._check_domain(site):
                continue
            domain_parts = site.split(".")[-2:]
            domain_key = tuple(domain_parts)
            domain_url = ".".join(domain_key)
            if 'm-team' in domain_url:
                domain_url = '.'.join(MT_URL.split('.')[-2:])

            self._cache.set(f'local_storage:{domain_url}', json.dumps(storage))

        self.ctx.info("LocalStorage 同步 Redis 成功")

    def _send_message(self, msg):
        self.ctx.notify(
            title="【CookieCloud 同步任务执行完成】",
            text=msg,
        )
