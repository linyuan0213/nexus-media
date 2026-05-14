import os

# -*- coding: utf-8 -*-
"""
AutoGenRss Plugin v2
RSS自动生成
"""
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytz
from lxml import etree

from app.db.repositories import SiteRepository
from app.helper import SiteHelper, SubmoduleHelper
from app.helper.cloudflare_helper import under_challenge
from app.helper.drissionpage_helper import DrissionPageHelper
from app.plugin_framework.context import PluginContext
from app.sites.siteconf import SiteConf
from app.sites.sites import Sites
from app.utils import ExceptionUtils, JsonUtils, RequestUtils, StringUtils
from app.utils.config_tools import get_proxies


class AutoGenRssPlugin:
    """RSS自动生成插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._site_schema = []
        self._site_repo = SiteRepository()
        self._siteconf = SiteConf()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("RSS自动生成插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("RSS自动生成插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行"""
        self.ctx.info("手动触发RSS生成")
        self._do_gen_rss()

    def _start_service(self):
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")
        onlyonce = config.get("onlyonce", False)

        if not enabled and not onlyonce:
            return

        # 加载模块
        self._site_schema = SubmoduleHelper.import_submodules(
            "app.plugin_framework.builtin_plugins.autogenrss.backend._autogenrss",
            filter_func=lambda _, obj: hasattr(obj, "match"),
        )
        self.ctx.debug(f"加载特殊站点：{self._site_schema}")

        if onlyonce:
            self.ctx.info("RSS自动生成服务启动，立即运行一次")
            run_date = datetime.now(tz=pytz.timezone(os.environ.get("TZ"))) + timedelta(seconds=3)
            self.ctx.schedule_date("gen_rss_once", self._do_gen_rss, run_date=run_date)
            self.ctx.set_config("onlyonce", False)

        if cron:
            self.ctx.info(f"同步服务启动，周期：{cron}")
            self.ctx.schedule_cron("gen_rss", self._do_gen_rss, cron=str(cron))

    def _stop_service(self):
        try:
            self.ctx.remove_schedule("gen_rss")
            self.ctx.remove_schedule("gen_rss_once")
        except Exception:
            pass

    def _do_gen_rss(self):
        config = self._get_config()
        rss_sites = config.get("rss_sites", [])
        notify = config.get("notify", False)

        if isinstance(rss_sites, str):
            rss_sites = [s for s in rss_sites.split("\n") if s]

        rss_sites = copy.deepcopy(Sites().get_sites(siteids=rss_sites))
        if not rss_sites:
            self.ctx.info("没有需要生成的站点，停止运行")
            return

        self.ctx.info("开始生成RSS任务")
        with ThreadPoolExecutor(min(len(rss_sites), 10)) as p:
            status = list(p.map(self._gen_rss, rss_sites))

        if status:
            self.ctx.info("生成RSS任务完成！")
            failed_msg = []
            gen_success_msg = []
            for s in status:
                if not s:
                    continue
                if "成功" in s:
                    gen_success_msg.append(s)
                else:
                    failed_msg.append(s)

            if notify:
                rss_message = "\n".join(gen_success_msg + failed_msg)
                self.ctx.notify(
                    title="【自动生成RSS任务完成】", text=f"生成RSS站点数: {len(rss_sites)} \n{rss_message}"
                )
        else:
            self.ctx.error("站点生成RSS任务失败！")

    def _build_class(self, url):
        for site_schema in self._site_schema:
            try:
                if site_schema.match(url):
                    return site_schema
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def _gen_rss(self, site_info):
        site_module = self._build_class(site_info.get("signurl"))
        if site_module and hasattr(site_module, "gen_rss"):
            try:
                status, msg = site_module().gen_rss(site_info)
                return msg
            except Exception as e:
                return f"【{site_info.get('name')}】生成RSS失败：{str(e)}"
        else:
            return self._gen_rss_base(site_info)

    def _gen_rss_base(self, site_info):
        if not site_info:
            return ""
        site = site_info.get("name")
        try:
            site_url = site_info.get("signurl")
            site_cookie = site_info.get("cookie")
            ua = site_info.get("ua")
            headers = site_info.get("headers")
            if (not site_url or not site_cookie) and not headers:
                self.ctx.warn(f"未配置 {str(site)} 的Cookie或请求头，无法获取到RSS")
                return ""
            if JsonUtils.is_valid_json(headers):
                headers = json.loads(headers)
            else:
                headers = {}

            home_url = StringUtils.get_base_url(site_url)
            rss_url = f"{home_url}/getrss.php"
            chrome = DrissionPageHelper()
            if site_info.get("chrome") and chrome.get_status():
                self.ctx.info(f"开始生成RSS站点（Chrome）：{site}")
                # TODO: Chrome仿真实现
                return f"【{site}】Chrome仿真生成RSS暂未实现"
            else:
                self.ctx.info(f"开始生成RSS站点：{site}")
                data = {
                    "inclbookmarked": "0",
                    "itemcategory": "1",
                    "itemsmalldescr": "1",
                    "itemsize": "1",
                    "showrows": "50",
                    "search": "",
                    "search_mode": "1",
                }
                headers.update({"User-Agent": ua})
                res = RequestUtils(
                    cookies=site_cookie,
                    headers=headers,
                    referer=site_url,
                    proxies=get_proxies() if site_info.get("proxy") else None,
                ).post_res(url=rss_url, data=data)

                if res and res.status_code in [200, 500, 403]:
                    if not SiteHelper.is_logged_in(res.text):
                        if under_challenge(res.text):
                            msg = "站点被Cloudflare防护，请开启浏览器仿真"
                        elif res.status_code == 200:
                            msg = "Cookie已失效"
                        else:
                            msg = f"状态码：{res.status_code}"
                        self.ctx.warn(f"{site} 生成RSS失败，{msg}")
                        return f"【{site}】生成RSS失败，{msg}！"
                    else:
                        if re.search(r"完成两步验证", res.text, re.IGNORECASE):
                            self.ctx.warn(f"{site} 生成RSS失败，需要两步验证")
                            return f"【{site}】生成RSS失败，需要两步验证"

                        gen_rss_url = self._parse_rss_link(res.text)
                        self.ctx.debug(f"生成的rss: {gen_rss_url}")
                        if gen_rss_url:
                            self._site_repo.update_site_rssurl(site_info.get("id"), gen_rss_url)
                            self.ctx.info(f"{site} 生成RSS成功")
                            return f"【{site}】生成RSS成功"
                elif res is not None:
                    self.ctx.warn(f"{site} 生成RSS失败，状态码：{res.status_code}")
                    return f"【{site}】生成RSS失败，状态码：{res.status_code}！"
                else:
                    self.ctx.warn(f"{site} 生成RSS失败，无法打开网站")
                    return f"【{site}】生成RSS失败，无法打开网站！"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            self.ctx.warn(f"{site} 生成RSS失败：{str(e)}")
            return f"【{site}】生成RSS失败：{str(e)}！"

    @staticmethod
    def _parse_rss_link(html_text: str) -> str:
        if not html_text:
            return ""
        html = etree.HTML(html_text)
        return next((href for href in html.xpath('//a[contains(@href, "linktype=dl")]/@href')), "")
