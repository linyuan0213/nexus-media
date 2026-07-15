import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
    SiteRssGenResult,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.registry import (
    RssHandlerRegistry,
)


class RssGenEngine:
    """RSS 生成编排引擎。"""

    def __init__(
        self,
        ctx,
        registry: RssHandlerRegistry,
        site_cache=None,
        site_repo=None,
        site_engine=None,
        event: Event | None = None,
    ):
        self.ctx = ctx
        self._registry = registry
        self._site_cache = site_cache
        self._site_repo = site_repo
        self._site_engine = site_engine
        self._event = event

    def run(self, config: dict):
        rss_sites = config.get("rss_sites", [])
        notify = config.get("notify", False)
        queue_cnt = config.get("queue_cnt", 10)

        if isinstance(rss_sites, str):
            rss_sites = [s for s in rss_sites.split("\n") if s]

        rss_sites = copy.deepcopy(self._site_cache.get_sites(siteids=rss_sites))  # type: ignore
        if not rss_sites:
            self.ctx.info("没有需要生成的站点，停止运行")
            return

        self.ctx.info("开始生成RSS任务")
        with ThreadPoolExecutor(min(len(rss_sites), int(queue_cnt) if queue_cnt else 10)) as p:
            status = list(p.map(self._generate_site, rss_sites))

        if not status:
            self.ctx.error("站点生成RSS任务失败！")
            return

        self.ctx.info("生成RSS任务完成！")
        gen_success_msg = [s.msg for s in status if s.ok]
        failed_msg = [s.msg for s in status if not s.ok]

        if notify:
            rss_message = "\n".join(gen_success_msg + failed_msg)
            self.ctx.notify(
                title="[自动生成RSS任务完成]",
                text=f"生成RSS站点数: {len(rss_sites)} \n{rss_message}",
            )

    def _generate_site(self, site_info: dict) -> SiteRssGenResult:
        if self._event and self._event.is_set():
            return SiteRssGenResult.custom(True, "")
        ctx = SiteRssGenContext.from_site_info(site_info, self._site_engine)
        self.ctx.debug(
            f"开始处理站点 {ctx.site} (输入id={site_info.get('id')}, 解析site_id={ctx.site_id}, url={ctx.site_url})"
        )
        factory = self._registry.get(ctx.site_id)
        handler_name = factory.__name__ if factory else "无"
        self.ctx.debug(f"站点 {ctx.site} 命中 handler: {handler_name}")

        handler = None
        if factory:
            handler = factory()

        if not handler:
            factory = self._registry.get_fallback(ctx.site_id)
            if factory:
                self.ctx.debug(f"站点 {ctx.site} 未命中专用配置，使用通用表单兜底")
                handler = factory()

        if not handler:
            handler = self._registry.get_generic()()

        try:
            result = handler.generate(ctx)
            self.ctx.debug(f"站点 {ctx.site} 结果: {result.msg}")
            return result
        except Exception as e:
            self.ctx.warn(f"站点 {ctx.site} RSS生成异常: {e}")
            return SiteRssGenResult.fail(ctx.site, str(e))
