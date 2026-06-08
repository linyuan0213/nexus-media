from typing import Callable

from app.utils.submodule_loader import SubmoduleLoader
from app.utils import StringUtils

from .handlers.base import SiteSigninHandler
from .handlers._declarative import DeclarativeSigninHandler
from .handlers._generic import GenericSigninHandler


HandlerFactory = Callable[[], SiteSigninHandler]


class HandlerRegistry:
    def __init__(self, plugin_ctx, rate_limiter, site_configs: list):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter
        self._site_configs = {cfg.site_url: cfg for cfg in site_configs}
        self._handlers: dict[str, HandlerFactory] = {}

    def load(self):
        self._handlers.clear()

        custom_classes = SubmoduleLoader.import_submodules(
            "app.plugin_framework.builtin_plugins.autosignin.backend.handlers",
            filter_func=lambda _, obj: (
                bool(getattr(obj, "site_url", "")) and obj.site_url not in ("__fallback__", "__generic__")
            ),
        )
        for cls in custom_classes:
            self._handlers[cls.site_url] = lambda c=cls: c(self._plugin_ctx, self._rate_limiter)

        for site_url, cfg in self._site_configs.items():
            if site_url not in self._handlers:
                self._handlers[site_url] = lambda c=cfg: DeclarativeSigninHandler(
                    self._plugin_ctx, self._rate_limiter, c
                )

    def get(self, signurl: str | None) -> HandlerFactory | None:
        if not signurl:
            return None
        domain = StringUtils.get_url_domain(signurl)
        return self._handlers.get(domain)

    def get_generic(self) -> HandlerFactory:
        return lambda: GenericSigninHandler(self._plugin_ctx, self._rate_limiter)

    def __len__(self) -> int:
        return len(self._handlers)
