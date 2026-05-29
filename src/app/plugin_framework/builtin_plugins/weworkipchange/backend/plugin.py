"""
WeworkIPChange Plugin v2
定时获取动态IP更新到企业微信可信任IP列表
"""

import contextlib
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytz
from pyquery import PyQuery

from app.helper.cookiecloud_helper import CookiecloudHelper
from app.infrastructure.cache_system import get_cache_manager
from app.plugin_framework.context import PluginContext
from app.plugin_framework.event_compat import EventHandler
from app.utils.config_tools import get_ua
from app.utils.http_utils import RequestUtils
from app.utils.types import EventType
from app.di import container


class WeworkIPChangePlugin:
    """企业微信可信任IP更新插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._drissonpage_helper = None
        self._cache = None
        self._tab_id = ""
        self._ip_url = "https://4.ipw.cn"

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("企业微信可信IP更新插件已启用")
        self._drissonpage_helper = container.drissionpage_helper()
        self._cache = get_cache_manager().get_or_create("wework_ipchange", cache_type="redis", fallback_maxsize=10)
        self._init_chrome_tab()
        self._start_service()

    def on_disable(self):
        self.ctx.info("企业微信可信IP更新插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行IP更新"""
        self.ctx.info("手动触发企业微信可信IP更新")
        self._change_ip()

    def _init_chrome_tab(self):
        if not self._drissonpage_helper or not self._cache:
            return
        try:
            tab_id = self._cache.get("tab_id")
            if isinstance(tab_id, bytes):
                tab_id = tab_id.decode("utf-8")
            if not tab_id or not self._drissonpage_helper.get_page_html_without_closetab(tab_id=tab_id):
                self._tab_id = self._drissonpage_helper.create_tab(
                    "https://work.weixin.qq.com/wework_admin/frame", self._get_config().get("cookie", "")
                )
                self._cache.set("tab_id", self._tab_id)
            else:
                self._tab_id = tab_id
        except Exception as e:
            self.ctx.error(f"初始化Chrome标签页失败: {e}")

    def _start_service(self):
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")
        onlyonce = config.get("onlyonce", False)

        if not enabled and not onlyonce:
            return

        if onlyonce:
            self.ctx.info("企业微信可信IP更新服务启动，立即运行一次")
            run_date = datetime.now(tz=pytz.timezone(os.environ.get("TZ") or "UTC")) + timedelta(seconds=3)
            self.ctx.schedule_date("change_ip_once", self._change_ip, run_date=run_date)
            self.ctx.set_config("onlyonce", False)

        if cron:
            self.ctx.info(f"企业微信可信IP更新服务启动，周期：{cron}")
            self.ctx.schedule_cron("change_ip", self._change_ip, cron=str(cron))

    def _stop_service(self):
        try:
            self.ctx.remove_schedule("change_ip")
            self.ctx.remove_schedule("change_ip_once")
        except Exception:
            pass

    @EventHandler.register(EventType.WeworkLogin)
    def login_by_code(self, event=None) -> bool:
        if not self._drissonpage_helper:
            return False
        item = event.event_data if event else {}
        if item:
            msg = item.get("msg")
            self.ctx.debug(f"验证码: {msg}")
            if self._drissonpage_helper.input_on_element(
                tab_id=self._tab_id, selector="tag:div@class=number_panel", input_str=msg or ""
            ):
                self.ctx.debug("验证码输入成功")
                return True
        return False

    def _get_cookie_by_chrome(self) -> bool:
        if not self._drissonpage_helper:
            return False
        login_status = False
        html_text = self._drissonpage_helper.get_page_html_without_closetab(tab_id=self._tab_id, is_refresh=True)
        if html_text and "退出" in html_text:
            login_status = True
            self.ctx.info("登录成功")
        else:
            html_text = self._drissonpage_helper.get_page_html_without_closetab(
                tab_id=self._tab_id, is_refresh=False, tab_category="iframe"
            )
            if html_text:
                html_doc = PyQuery(html_text)
                img_url = html_doc("img.qrcode_login_img.js_qrcode_img").attr("src")
                self.ctx.debug(f"获取二维码成功，当前二维码url: {img_url}")
                if img_url:
                    img_url = f"https://work.weixin.qq.com{img_url}"
                    self.ctx.info("登录已过期，重新登录")
                    self.ctx.notify(title="[企业微信登录过期]", text="请点击扫码重新登录", image=img_url)

        if not login_status:
            start = time.time()
            self.ctx.info("等待扫码结果...")
            while time.time() - start < 60:
                time.sleep(5)
                html_text = self._drissonpage_helper.get_page_html_without_closetab(tab_id=self._tab_id)
                if html_text and ("短信安全验证" in html_text or "SMS" in html_text):
                    self.ctx.info("等待输入验证码...")
                    self.ctx.notify(title="[企业微信登录验证码]", text="请输入 /wxl+验证码 认证")
                if html_text and ("退出" in html_text or "Quit" in html_text):
                    login_status = True
                    break
            if login_status:
                self.ctx.info("登录成功")
            else:
                self.ctx.info("登录失败，请重新登录...")
                return False

        cookie = self._drissonpage_helper.get_cookie(self._tab_id)
        self.ctx.debug(f"获取cookie成功，当前cookie: {cookie}")
        self.ctx.set_config("cookie", cookie)
        return True

    def _change_ip(self):
        self.ctx.info(f"当前时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))} 开始更新IP")
        config = self._get_config()
        use_cookiecloud = config.get("use_cookiecloud")
        use_chrome = config.get("use_chrome")
        cookie = config.get("cookie")
        app_ids = config.get("app_ids")
        overwrite = config.get("overwrite", True)
        notify = config.get("notify", False)

        if not app_ids:
            self.ctx.warn("未配置企业微信APP ID")
            return

        if use_cookiecloud:
            EventHandler.send_event(EventType.CookieSync)
            time.sleep(10)
            cookie = CookiecloudHelper().get_cookie("qq.com")

        if use_chrome:
            if not self._get_cookie_by_chrome():
                return
            cookie = self.ctx.get_config("cookie")

        dynamic_ip = self._get_current_dynamic_ip()
        if not dynamic_ip:
            self.ctx.error("获取动态IP失败")
            return

        app_ids_list = [app_id.strip() for app_id in app_ids.split(",") if app_id.strip()]
        if not app_ids_list:
            self.ctx.warn("APP ID解析为空")
            return

        all_msg = []
        with ThreadPoolExecutor(max_workers=min(4, len(app_ids_list))) as executor:
            futures = [
                executor.submit(self._process_single_app, app_id, cookie, dynamic_ip, overwrite)
                for app_id in app_ids_list
            ]
            for future in futures:
                try:
                    all_msg.append(future.result())
                except Exception as e:
                    all_msg.append(f"处理异常: {e}\n")

        final_msg = "".join(all_msg)
        self.ctx.info(final_msg)

        if notify:
            schedules = self.ctx.get_schedules()
            next_run_time = ""
            if schedules:
                with contextlib.suppress(Exception):
                    next_run_time = schedules[0].next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            self.ctx.notify(
                title="[自动更新企业微信可信IP任务完成]", text=final_msg + f"\n下次更新时间: {next_run_time}"
            )

    def _process_single_app(self, app_id, cookie, dynamic_ip, overwrite):
        msg = ""
        update_status = False
        try:
            ips = self._get_current_iplist(cookie=cookie, app_id=app_id)
            ip_exist = dynamic_ip in ips if ips else False

            iplist = []
            if not overwrite:
                iplist = ips.copy() if ips else []
            iplist.append(dynamic_ip)

            if not ip_exist:
                update_status = self._set_iplist(cookie=cookie, iplist=iplist, app_id=app_id)
                if update_status:
                    self.ctx.info(f"AppID[{app_id}] 更新可信IP成功，当前IP: {dynamic_ip}")
                else:
                    self.ctx.error(f"AppID[{app_id}] 更新可信IP失败，请检查cookie")

            if ip_exist:
                msg = f"AppID[{app_id}] IP {dynamic_ip} 已存在\n"
            else:
                msg = (
                    f"AppID[{app_id}] 更新可信IP成功，当前IP: {dynamic_ip}\n"
                    if update_status
                    else f"AppID[{app_id}] 更新可信IP失败，请检查cookie\n"
                )
        except Exception as e:
            msg = f"AppID[{app_id}] 处理异常: {str(e)}\n"
            self.ctx.error(msg)
        return msg

    def _get_current_dynamic_ip(self):
        try:
            response = RequestUtils().get_res(url=self._ip_url)
            if response and response.status_code == 200:
                pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
                ip_str = response.text.strip()
                if re.match(pattern, ip_str):
                    self.ctx.debug(f"动态公网IP: {ip_str}")
                    return ip_str
        except Exception as e:
            self.ctx.error(f"获取动态IP失败: {e}")
        return None

    def _get_current_iplist(self, cookie: str, app_id: str):
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            "content-type": "application/x-www-form-urlencoded",
            "referer": "https://work.weixin.qq.com/wework_admin/frame",
            "cookie": cookie,
            "user-agent": get_ua(),
            "x-requested-with": "XMLHttpRequest",
        }
        url = "https://work.weixin.qq.com/wework_admin/apps/getOpenApiApp"
        params = {
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
            "timeZoneInfo%5Bzone_offset%5D": "-8",
            "random": str(random.random()),
            "app_id": app_id,
            "bind_mini_program": "false",
        }
        try:
            response = RequestUtils(headers=headers).get_res(url=url, params=params)
            if response and response.status_code == 200:
                app_json = response.json()
                try:
                    ip_list = app_json.get("data", {}).get("white_ip_list", {}).get("ip") or []
                except Exception:
                    if app_json.get("result", {}).get("errCode"):
                        self.ctx.debug("获取当前可信任IP失败")
                    return []
                self.ctx.debug(f"当前可信IP: {ip_list}")
                return ip_list
        except Exception as e:
            self.ctx.error(f"获取可信IP列表失败: {e}")
        return []

    def _set_iplist(self, cookie: str, iplist: list, app_id: str):
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookie,
            "origin": "https://work.weixin.qq.com",
            "referer": "https://work.weixin.qq.com/wework_admin/frame",
            "user-agent": get_ua(),
            "x-requested-with": "XMLHttpRequest",
        }
        params = {
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
            "timeZoneInfo[zone_offset]": "-8",
            "random": str(random.random()),
        }
        ip_str = "\u0026".join([f"ipList[]={ip}" for ip in iplist])
        data = f"app_id={app_id}\u0026{ip_str}"
        url = "https://work.weixin.qq.com/wework_admin/apps/saveIpConfig"

        try:
            response = RequestUtils(headers=headers).post_res(url=url, params=params, data=data)
            if response and response.status_code == 200:
                json_data = response.json()
                try:
                    if json_data.get("data"):
                        self.ctx.debug("更新可信IP成功")
                        return True
                except Exception:
                    if json_data.get("result", {}).get("errCode"):
                        self.ctx.debug("更新可信IP失败")
                    return False
        except Exception as e:
            self.ctx.error(f"设置可信IP列表失败: {e}")
        return False
