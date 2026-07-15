import copy
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import SiteSigninContext
from app.plugin_framework.builtin_plugins.autosignin.backend.registry import HandlerRegistry


class SigninEngine:
    def __init__(self, ctx, registry: HandlerRegistry, site_cache=None, site_engine=None):
        self.ctx = ctx
        self._registry = registry
        self._site_cache = site_cache
        self._site_engine = site_engine

    def run(self, config: dict, get_history, update_history, delete_history):
        sign_sites_cfg = config.get("sign_sites", [])
        special_sites = config.get("special_sites") or []
        browser_sites = config.get("browser_sites") or []
        retry_keyword = config.get("retry_keyword")
        queue_cnt = config.get("queue_cnt", 10)
        notify = config.get("notify", False)

        today = datetime.today()
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        delete_history(yesterday_str)

        today_str = today.strftime("%Y-%m-%d")
        today_history = get_history(key=today_str)

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

        browser_set = set(str(s) for s in browser_sites)
        sign_sites = copy.deepcopy(self._site_cache.get_sites(siteids=sign_sites))  # type: ignore
        if not sign_sites:
            self.ctx.info("没有可签到站点，停止运行")
            return

        new_sign_sites = []
        for site in sign_sites:
            if site.get("public"):
                self.ctx.info(f"站点 {site.get('name')} 是BT站点，跳过签到")
                continue
            if str(site.get("id")) in browser_set or str(site.get("id", "")) in browser_set:
                site["is_browser"] = True
            new_sign_sites.append(site)

        sign_sites = new_sign_sites
        if not sign_sites:
            self.ctx.info("没有可签到站点（已过滤BT站点），停止运行")
            return

        self.ctx.info("开始执行签到任务")
        with ThreadPoolExecutor(min(len(sign_sites), int(queue_cnt) if queue_cnt else 10)) as p:
            status = list(p.map(self._signin_site, sign_sites))

        if status:
            self._process_results(
                status,
                sign_sites_cfg,
                special_sites,
                retry_keyword,
                notify,
                today_str,
                get_history,
                update_history,
            )

    def _signin_site(self, site_info: dict) -> str:
        site_ctx = SiteSigninContext.from_site_info(site_info, self._site_engine)
        self.ctx.debug(
            f"开始处理站点 {site_ctx.site} (输入id={site_info.get('id')}, "
            f"解析site_id={site_ctx.site_id}, url={site_ctx.site_url}, "
            f"browser={site_ctx.is_browser})"
        )
        factory = self._registry.get(site_ctx.site_id)
        handler_name = factory.__name__ if factory else "无"
        self.ctx.debug(f"站点 {site_ctx.site} 命中 handler: {handler_name}")
        if not factory:
            self.ctx.debug(f"站点 {site_ctx.site} 未找到专用 handler，使用通用 HTTP 兜底")

        handler = None
        if factory:
            handler = factory()

        if not handler:
            factory = self._registry.get_fallback(site_ctx.site_id)
            if factory:
                self.ctx.debug(f"站点 {site_ctx.site} 未命中专用配置，使用通用 HTTP 兜底")
                handler = factory()

        if not handler:
            handler = self._registry.get_generic()()

        try:
            result = handler.signin(site_ctx)
            self.ctx.debug(f"站点 {site_ctx.site} 结果: {result.msg}")
            return result.msg
        except Exception as e:
            self.ctx.warn(f"站点 {site_ctx.site} 签到异常: {e}")
            return f"[{site_ctx.site}]签到失败：{str(e)}"

    def _process_results(
        self, status, sign_sites_cfg, special_sites, retry_keyword, notify, today_str, get_history, update_history
    ):
        self.ctx.info("站点签到任务完成！")
        retry_sites: list = []
        retry_msg: list = []
        login_success_msg: list = []
        sign_success_msg: list = []
        already_sign_msg: list = []
        fz_sign_msg: list = []
        failed_msg: list = []

        sites_map = {site.get("name"): site.get("id") for site in self._site_cache.get_site_dict()}  # type: ignore
        for s in status:
            if not s:
                continue
            if "登录成功" in s:
                login_success_msg.append(s)
            elif "浏览器签到成功" in s:
                fz_sign_msg.append(s)
            elif "签到成功" in s:
                sign_success_msg.append(s)
            elif "已签到" in s:
                already_sign_msg.append(s)
            else:
                failed_msg.append(s)
                site_names = re.findall(r"\[(.*?)\]", s)
                if site_names:
                    site_id = sites_map.get(site_names[0])
                    if site_id and (not retry_keyword or re.search(retry_keyword, s)):
                        self.ctx.debug(f"站点 {site_names[0]} 加入重试列表")
                        retry_sites.append(str(site_id))
                        retry_msg.append(s)

        id_to_name = {str(site.get("id")): site.get("name") for site in self._site_cache.get_site_dict()}  # type: ignore
        retry_names = [id_to_name.get(str(sid), sid) for sid in retry_sites]
        failed_detail = "\n".join(failed_msg + retry_msg) or "无"

        def _extract_site_ids(messages: list[str]) -> list[str]:
            ids: list[str] = []
            for msg in messages:
                names = re.findall(r"\[(.*?)\]", msg)
                if names:
                    sid = sites_map.get(names[0])
                    if sid:
                        ids.append(str(sid))
            return ids

        sign_sites = _extract_site_ids(sign_success_msg + already_sign_msg + login_success_msg + fz_sign_msg)
        sign_sites = list(set(sign_sites))

        self.ctx.debug(
            f"签到结果统计: 成功={len(sign_success_msg)}, 已签={len(already_sign_msg)}, "
            f"登录={len(login_success_msg)}, 浏览器={len(fz_sign_msg)}, 失败={len(failed_msg)}, 重试={len(retry_sites)}"
        )
        self.ctx.debug(f"失败详情:\n{failed_detail}")
        self.ctx.debug(f"下次签到重试站点 {retry_names}")

        today_history = get_history(key=today_str) or {}
        today_history.update({"sign": sign_sites, "retry": retry_sites, "names": id_to_name})
        update_history(today_str, today_history)

        if notify:
            signin_message = login_success_msg + sign_success_msg + already_sign_msg + fz_sign_msg + failed_msg
            if retry_msg:
                signin_message.append("——————命中重试—————")
                signin_message += retry_msg
            self.ctx._message.send_site_signin_message(signin_message)

            self.ctx.notify(
                title="[自动签到任务完成]",
                text=f"本次签到数量: {len(status)} \n"
                f"命中重试数量: {len(retry_sites)} \n"
                f"强制签到数量: {len(special_sites)} \n"
                f"下次签到数量: {len(set(retry_sites + special_sites))} \n"
                f"详见签到消息",
            )
