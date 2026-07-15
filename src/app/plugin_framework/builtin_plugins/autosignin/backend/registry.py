import inspect
from typing import Any, Callable

from app.utils.submodule_loader import SubmoduleLoader

from .handlers._api import ApiSigninHandler
from .handlers._browser import BrowserSigninHandler
from .handlers._http import HttpSigninHandler
from .handlers.base import SiteSigninHandler

HandlerFactory = Callable[[], SiteSigninHandler]


class HandlerRegistry:
    _FALLBACK_HTTP_KEY = "__fallback_http__"

    def __init__(self, plugin_ctx, rate_limiter, site_engine, signin_configs: list[dict], agent_service=None):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter
        self._site_engine = site_engine
        self._agent_service = agent_service
        self._signin_configs = {cfg["site_id"]: cfg for cfg in signin_configs}
        self._fallback_http_config = self._signin_configs.pop(self._FALLBACK_HTTP_KEY, {})
        self._handlers: dict[str, HandlerFactory] = {}

    def load(self):
        self._handlers.clear()

        custom_classes = SubmoduleLoader.import_submodules(
            "app.plugin_framework.builtin_plugins.autosignin.backend.handlers",
            filter_func=lambda _, obj: (
                bool(getattr(obj, "site_id", ""))
                or (bool(getattr(obj, "site_url", "")) and obj.site_url not in ("__fallback__", "__generic__"))
            ),
        )
        for cls in custom_classes:
            key = getattr(cls, "site_id", "") or getattr(cls, "site_url", "")
            if not key:
                continue
            self._handlers[key] = lambda c=cls: c(
                self._plugin_ctx,
                self._rate_limiter,
                **self._filter_kwargs(
                    c,
                    {
                        "agent_service": self._agent_service,
                    },
                ),
            )

        for site_id, cfg in self._signin_configs.items():
            if site_id in self._handlers:
                continue
            strategy_type = cfg.get("type", "http")
            if strategy_type == "api":
                self._handlers[site_id] = lambda c=cfg: ApiSigninHandler(self._plugin_ctx, self._rate_limiter, c)
            elif strategy_type == "browser":
                self._handlers[site_id] = lambda c=cfg: BrowserSigninHandler(self._plugin_ctx, self._rate_limiter, c)
            else:
                self._handlers[site_id] = lambda c=cfg: HttpSigninHandler(self._plugin_ctx, self._rate_limiter, c)

    @staticmethod
    def _filter_kwargs(handler_class: type, deps: dict[str, Any]) -> dict[str, Any]:
        try:
            params = inspect.signature(handler_class.__init__).parameters
        except Exception:
            return {}
        return {k: v for k, v in deps.items() if k in params}

    def get(self, site_id: str | None) -> HandlerFactory | None:
        if not site_id:
            return None
        return self._handlers.get(site_id)

    def get_fallback(self, site_id: str | None) -> HandlerFactory | None:
        if not site_id or not self._fallback_http_config:
            return None
        site_def = self._site_engine.get_by_id(site_id)
        if site_def and site_def.api:
            return None
        return lambda: HttpSigninHandler(self._plugin_ctx, self._rate_limiter, self._fallback_http_config)

    def get_generic(self) -> HandlerFactory:
        return lambda: HttpSigninHandler(self._plugin_ctx, self._rate_limiter, {})

    def __len__(self) -> int:
        return len(self._handlers)
