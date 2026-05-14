"""
AutoSignIn Plugin v2
站点自动签到保号，支持重试
"""

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from time import time

from lxml import etree

from app.core.constants import MT_URL
from app.helper import SiteHelper, SubmoduleHelper
from app.helper.cloudflare_helper import under_challenge
from app.helper.drissionpage_helper import DrissionPageHelper
from app.message import Message
from app.plugin_framework.context import PluginContext
from app.sites.siteconf import SiteConf
from app.sites.sites import Sites
from app.utils import ExceptionUtils, JsonUtils, RequestUtils, StringUtils
from app.utils.config_tools import get_proxies


class AutoSignInPlugin:
    """站点自动签到插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._site_schema = []
        self._siteconf = SiteConf()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("站点自动签到插件已启用")
        self._start_service()
        # 注册消息命令：/signin 立即执行签到
        self.ctx.register_message_command(cmd="/signin", desc="站点签到", func=self._handle_signin_command)

    def on_disable(self):
        self.ctx.info("站点自动签到插件已禁用")
        self._stop_service()
        self.ctx.unregister_message_command("/signin")

    def _handle_signin_command(self, msg, in_from, user_id, user_name):
        """处理 /signin 消息命令"""
        self.ctx.info(f"收到签到命令: user={user_name}, msg={msg}")
        self.run()
        Message().send_channel_msg(
            channel=in_from, title="站点签到", text="签到任务已触发，请稍后查看签到结果", user_id=user_id
        )

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行签到"""
        self.ctx.info("手动触发站点签到")
        self._do_signin()

    def _start_service(self):
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")
        clean = config.get("clean", False)

        if not enabled:
            return

        # 加载模块
        self._site_schema = SubmoduleHelper.import_submodules(
            "app.plugin_framework.builtin_plugins.autosignin.backend._autosignin",
            filter_func=lambda _, obj: hasattr(obj, "match"),
        )
        self.ctx.debug(f"加载站点签到：{self._site_schema}")

        # 清理缓存
        if clean:
            self._delete_history(datetime.today().strftime("%Y-%m-%d"))
            self.ctx.set_config("clean", False)

        if cron:
            self.ctx.info(f"定时签到服务启动，周期：{cron}")
            self.ctx.schedule_cron("signin", self._do_signin, cron=str(cron))

    def _stop_service(self):
        try:
            self.ctx.remove_schedule("signin")
            self.ctx.remove_schedule("signin_once")
        except Exception:
            pass

    def _load_history(self):
        content = self.ctx.read_data("signin_history.json")
        if content:
            try:
                return json.loads(content)
            except Exception:
                pass
        return {}

    def _save_history(self, data):
        self.ctx.write_data("signin_history.json", json.dumps(data, ensure_ascii=False, indent=2))

    def _get_history(self, key=None):
        data = self._load_history()
        if key:
            return data.get(key)
        return data

    def _update_history(self, key, value):
        data = self._load_history()
        data[key] = value
        self._save_history(data)

    def _delete_history(self, key):
        data = self._load_history()
        if key in data:
            del data[key]
            self._save_history(data)

    def _do_signin(self):
        config = self._get_config()
        sign_sites_cfg = config.get("sign_sites", [])
        special_sites = config.get("special_sites") or []
        emulate_sites = config.get("emulate_sites") or []
        retry_keyword = config.get("retry_keyword")
        queue_cnt = config.get("queue_cnt", 10)
        notify = config.get("notify", False)

        today = datetime.today()
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        self._delete_history(yesterday_str)

        today_str = today.strftime("%Y-%m-%d")
        today_history = self._get_history(key=today_str)

        if not today_history:
            sign_sites = sign_sites_cfg
            self.ctx.info(f"今日 {today_str} 未签到，开始签到已选站点")
        else:
            retry_sites_hist = today_history.get("retry", [])
            already_sign_sites = today_history.get("sign", [])
            no_sign_sites = [s for s in sign_sites_cfg if s not in already_sign_sites]
            sign_sites = list(set(retry_sites_hist + no_sign_sites + special_sites))
            if sign_sites:
                self.ctx.info(f"今日 {today_str} 已签到，开始重签重试站点、特殊站点、未签站点")
            else:
                self.ctx.info(f"今日 {today_str} 已签到，无重新签到站点，本次任务结束")
                return

        emulate_set = set(emulate_sites).intersection(set(sign_sites))
        sign_sites = copy.deepcopy(Sites().get_sites(siteids=sign_sites))
        if not sign_sites:
            self.ctx.info("没有可签到站点，停止运行")
            return

        new_sign_sites = []
        for site in sign_sites:
            if site.get("public"):
                self.ctx.info(f"站点 {site.get('name')} 是BT站点，跳过签到")
                continue
            if str(site.get("id")) in emulate_set:
                site["chrome"] = True
            new_sign_sites.append(site)

        sign_sites = new_sign_sites
        if not sign_sites:
            self.ctx.info("没有可签到站点（已过滤BT站点），停止运行")
            return

        self.ctx.info("开始执行签到任务")
        with ThreadPoolExecutor(min(len(sign_sites), int(queue_cnt) if queue_cnt else 10)) as p:
            status = list(p.map(self._signin_site, sign_sites))

        if status:
            self.ctx.info("站点签到任务完成！")
            retry_sites = []
            retry_msg = []
            login_success_msg = []
            sign_success_msg = []
            already_sign_msg = []
            fz_sign_msg = []
            failed_msg = []

            sites_map = {site.get("name"): site.get("id") for site in Sites().get_site_dict()}
            for s in status:
                if not s:
                    continue
                if retry_keyword:
                    site_names = re.findall(r"【(.*?)】", s)
                    if site_names:
                        site_id = sites_map.get(site_names[0])
                        if site_id and re.search(retry_keyword, s):
                            self.ctx.debug(f"站点 {site_names[0]} 命中重试关键词 {retry_keyword}")
                            retry_sites.append(str(site_id))
                            retry_msg.append(s)
                            continue

                if "登录成功" in s:
                    login_success_msg.append(s)
                elif "仿真签到成功" in s:
                    fz_sign_msg.append(s)
                    continue
                elif "签到成功" in s:
                    sign_success_msg.append(s)
                elif "已签到" in s:
                    already_sign_msg.append(s)
                else:
                    failed_msg.append(s)

            if not retry_keyword:
                retry_sites = sign_sites_cfg

            self.ctx.debug(f"下次签到重试站点 {retry_sites}")

            # 存储站点名称映射（用于前端展示）
            id_to_name = {str(site.get("id")): site.get("name") for site in Sites().get_site_dict()}
            history_data = {"sign": sign_sites_cfg, "retry": retry_sites, "names": id_to_name}
            self._update_history(today_str, history_data)

            if notify:
                signin_message = login_success_msg + sign_success_msg + already_sign_msg + fz_sign_msg + failed_msg
                if retry_msg:
                    signin_message.append("——————命中重试—————")
                    signin_message += retry_msg
                Message().send_site_signin_message(signin_message)

                self.ctx.notify(
                    title="【自动签到任务完成】",
                    text=f"本次签到数量: {len(sign_sites)} \n"
                    f"命中重试数量: {len(retry_sites) if retry_keyword else 0} \n"
                    f"强制签到数量: {len(special_sites)} \n"
                    f"下次签到数量: {len(set(retry_sites + special_sites))} \n"
                    f"详见签到消息",
                )
        else:
            self.ctx.error("站点签到任务失败！")

    def _build_class(self, url):
        for site_schema in self._site_schema:
            try:
                if site_schema.match(url):
                    return site_schema
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def _signin_site(self, site_info):
        site_module = self._build_class(site_info.get("signurl"))
        if site_module and hasattr(site_module, "signin"):
            try:
                status, msg = site_module().signin(site_info)
                return msg
            except Exception as e:
                return f"【{site_info.get('name')}】签到失败：{str(e)}"
        else:
            return self._signin_base(site_info)

    def _signin_base(self, site_info):
        if not site_info:
            return ""
        site = site_info.get("name")
        try:
            site_url = site_info.get("signurl")
            site_cookie = site_info.get("cookie")
            ua = site_info.get("ua")
            headers = site_info.get("headers")
            if (not site_url or not site_cookie) and not headers:
                self.ctx.warn(f"未配置 {str(site)} 的Cookie或请求头，无法签到")
                return ""
            if JsonUtils.is_valid_json(headers):
                headers = json.loads(headers)
            else:
                headers = {}

            chrome = DrissionPageHelper()
            if site_info.get("chrome") and chrome.get_status():
                self.ctx.info(f"开始站点仿真签到：{site}")
                home_url = StringUtils.get_base_url(site_url)
                if "1ptba" in home_url:
                    home_url = f"{home_url}/index.php"

                html_text = chrome.get_page_html(url=home_url, cookies=site_cookie)
                if not html_text:
                    self.ctx.warn(f"{site} 无法打开网站")
                    return f"【{site}】仿真签到失败，无法打开网站！"

                if re.search(r"已签|签到已得|今日已签|已签到|签到成功", html_text, re.IGNORECASE):
                    self.ctx.info(f"{site} 今日已签到")
                    return f"【{site}】今日已签到"

                if re.search(r"完成两步验证", html_text, re.IGNORECASE):
                    self.ctx.warn(f"{site} 仿真签到失败，需要两步验证")
                    return f"【{site}】仿真签到失败，需要两步验证"

                if not SiteHelper.is_logged_in(html_text):
                    self.ctx.warn(f"{site} 仿真签到失败，登录状态异常")
                    return f"【{site}】仿真签到失败，登录状态异常"

                html = etree.HTML(html_text)
                xpath_str = None
                for xpath in self._siteconf.get_checkin_conf():
                    if html.xpath(xpath):
                        xpath_str = xpath
                        self.ctx.debug(f"{site} 找到签到按钮XPath: {xpath_str}")
                        break

                if not xpath_str:
                    self.ctx.warn(f"{site} 未找到签到按钮，但登录成功")
                    return f"【{site}】模拟登录成功"

                try:
                    self.ctx.debug(f"{site} 开始点击签到按钮")
                    html_text = chrome.get_page_html(
                        url=home_url, cookies=site_cookie, click_xpath=f"xpath:{xpath_str}", delay=10, click_delay=15
                    )

                    if not html_text:
                        self.ctx.warn(f"{site} 仿真签到失败，无法通过Cloudflare")
                        return f"【{site}】仿真签到失败，无法通过Cloudflare！"

                    if re.search(r"已签|签到已得|签到成功|签到.*成功|获得.*积分|签到.*积分", html_text, re.IGNORECASE):
                        self.ctx.info(f"{site} 仿真签到成功")
                        return f"【{site}】仿真签到成功"
                    elif re.search(r"完成两步验证|两步验证|2FA|二次验证", html_text, re.IGNORECASE):
                        self.ctx.warn(f"{site} 仿真签到失败，需要两步验证")
                        return f"【{site}】仿真签到失败，需要两步验证"
                    elif re.search(r"已签到|今日已签|重复签到", html_text, re.IGNORECASE):
                        self.ctx.info(f"{site} 今日已签到")
                        return f"【{site}】今日已签到"
                    else:
                        if re.search(r"错误|失败|异常|error|fail", html_text, re.IGNORECASE):
                            self.ctx.warn(f"{site} 仿真签到失败，页面显示错误")
                            return f"【{site}】仿真签到失败，页面显示错误"
                        else:
                            self.ctx.warn(f"{site} 仿真签到失败，未知原因")
                            return f"【{site}】仿真签到失败，未知原因"
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    self.ctx.warn(f"{site} 仿真签到失败：{str(e)}")
                    return f"【{site}】签到失败！"
            else:
                if site_url.find("attendance.php") != -1 or site_url.find("checkIn") != -1:
                    checkin_text = "签到"
                else:
                    checkin_text = "模拟登录"
                self.ctx.info(f"开始站点{checkin_text}：{site}")

                if "m-team" in site_url:
                    site_def = SiteEngine.get_instance().get_by_url(site_url)
                    url = (
                        f"{site_def.api.base_url}/api/member/updateLastBrowse"
                        if site_def and site_def.api
                        else f"{MT_URL}/api/member/updateLastBrowse"
                    )
                    headers.update(
                        {
                            "accept": "application/json, text/plain, */*",
                            "content-type": "application/json",
                            "user-agent": ua,
                            "ts": str(int(time())),
                        }
                    )
                    if headers.get("x-api-key"):
                        headers.pop("x-api-key")
                    if not headers.get("authorization"):
                        self.ctx.warn(f"{site} 请填写请求头 authorization 参数")
                        return f"【{site}】请填写请求头 authorization 参数！"
                    res = RequestUtils(
                        headers=headers, proxies=get_proxies() if site_info.get("proxy") else None
                    ).post_res(url=url)
                else:
                    headers.update({"User-Agent": ua})
                    res = RequestUtils(
                        cookies=site_cookie, headers=headers, proxies=get_proxies() if site_info.get("proxy") else None
                    ).get_res(url=site_url)

                if res and res.status_code in [200, 500, 403]:
                    if not SiteHelper.is_logged_in(res.text):
                        if under_challenge(res.text):
                            msg = "站点被Cloudflare防护，请开启浏览器仿真"
                        elif res.status_code == 200:
                            msg = "Cookie已失效"
                        else:
                            msg = f"状态码：{res.status_code}"
                        self.ctx.warn(f"{site} {checkin_text}失败，{msg}")
                        return f"【{site}】{checkin_text}失败，{msg}！"
                    else:
                        if re.search(r"完成两步验证", res.text, re.IGNORECASE):
                            self.ctx.warn(f"{site} 签到失败，需要两步验证")
                            return f"【{site}】签到失败，需要两步验证"
                        self.ctx.info(f"{site} {checkin_text}成功")
                        return f"【{site}】{checkin_text}成功"
                elif res is not None:
                    self.ctx.warn(f"{site} {checkin_text}失败，状态码：{res.status_code}")
                    return f"【{site}】{checkin_text}失败，状态码：{res.status_code}！"
                else:
                    self.ctx.warn(f"{site} {checkin_text}失败，无法打开网站")
                    return f"【{site}】{checkin_text}失败，无法打开网站！"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            self.ctx.warn(f"{site} 签到失败：{str(e)}")
            return f"【{site}】签到失败：{str(e)}！"
