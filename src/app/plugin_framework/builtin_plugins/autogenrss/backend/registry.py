import inspect
from typing import Any, Callable

from app.utils.submodule_loader import SubmoduleLoader

from .handlers._api import ApiRssGenHandler
from .handlers._browser import BrowserRssGenHandler
from .handlers._form import FormRssGenHandler
from .handlers.base import SiteRssGenHandler

HandlerFactory = Callable[[], SiteRssGenHandler]


class RssHandlerRegistry:
    _FALLBACK_FORM_KEY = "__fallback_form__"
    _GENERIC_KEYS = {"__form__", "__api__", "__browser__"}

    def __init__(self, plugin_ctx, rate_limiter, site_engine, rss_configs: list[dict], site_repo=None, site_cache=None):
        self._plugin_ctx = plugin_ctx
        self._rate_limiter = rate_limiter
        self._site_engine = site_engine
        self._site_repo = site_repo
        self._site_cache = site_cache
        self._rss_configs = {cfg["site_id"]: cfg for cfg in rss_configs}
        self._fallback_form_config = self._rss_configs.pop(self._FALLBACK_FORM_KEY, {})
        self._handlers: dict[str, HandlerFactory] = {}

    def load(self):
        self._handlers.clear()

        custom_classes = SubmoduleLoader.import_submodules(
            "app.plugin_framework.builtin_plugins.autogenrss.backend.handlers",
            filter_func=lambda _, obj: (
                bool(getattr(obj, "site_id", "")) and getattr(obj, "site_id", "") not in self._GENERIC_KEYS
            ),
        )
        for cls in custom_classes:
            key = getattr(cls, "site_id", "")
            if not key:
                continue
            self._handlers[key] = lambda c=cls: c(
                self._plugin_ctx,
                self._rate_limiter,
                self._site_repo,
                self._site_cache,
                **self._filter_kwargs(c, {}),
            )

        for site_id, cfg in self._rss_configs.items():
            if site_id in self._handlers:
                continue
            strategy_type = cfg.get("type", "form")
            if strategy_type == "api":
                self._handlers[site_id] = lambda c=cfg: ApiRssGenHandler(
                    self._plugin_ctx, self._rate_limiter, self._site_repo, self._site_cache, c
                )
            elif strategy_type == "browser":
                self._handlers[site_id] = lambda c=cfg: BrowserRssGenHandler(
                    self._plugin_ctx, self._rate_limiter, self._site_repo, self._site_cache, c
                )
            else:
                self._handlers[site_id] = lambda c=cfg: FormRssGenHandler(
                    self._plugin_ctx, self._rate_limiter, self._site_repo, self._site_cache, c
                )

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
        if not site_id or not self._fallback_form_config:
            return None
        return lambda: FormRssGenHandler(
            self._plugin_ctx, self._rate_limiter, self._site_repo, self._site_cache, self._fallback_form_config
        )

    def get_generic(self) -> HandlerFactory:
        return lambda: FormRssGenHandler(self._plugin_ctx, self._rate_limiter, self._site_repo, self._site_cache, {})

    def __len__(self) -> int:
        return len(self._handlers)
