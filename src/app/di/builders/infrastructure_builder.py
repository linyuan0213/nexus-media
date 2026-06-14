"""基础设施 Builder — 创建 Layer 1 对象。"""

import log
from app.db.repositories.apikey_repo_adapter import APIKeyLogRepositoryAdapter, APIKeyRepositoryAdapter
from app.db.repositories.plugin_framework_repo_adapter import PluginLogRepositoryAdapter
from app.di.models import InfrastructureObjects
from app.events import register_modules
from app.events.bridge import PluginBridge
from app.events.bus import EventBus
from app.events.config import EVENT_HANDLER_MODULES
from app.events.decorators import auto_register
from app.events.middleware import ErrorHandlingMiddleware, LoggingMiddleware
from app.events.registry import EventHandlerRegistry
from app.infrastructure.queue.factory import MessageQueueFactory
from app.infrastructure.thread import ThreadExecutor
from app.message.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.registry import PluginRegistry
from app.plugin_framework.sandbox import PluginSandbox
from app.services.apikey_service import APIKeyService
from app.services.scheduler.core import SchedulerCore
from app.services.site_rate_limiter import SiteRateLimiterService
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.sites.siteuserinfo.config_api import _api_factory
from app.sites.siteuserinfo.config_html import _html_config_factory


def build_infrastructure() -> InfrastructureObjects:
    """创建 Layer 1 基础设施对象。"""
    plugin_registry = PluginRegistry()
    thread_executor = ThreadExecutor.named("default")
    scheduler_core = SchedulerCore()
    apikey_service = APIKeyService(
        key_repo=APIKeyRepositoryAdapter(),
        log_repo=APIKeyLogRepositoryAdapter(),
    )
    message = Message(apikey_service=apikey_service)

    site_engine = SiteEngine()
    site_engine.register_user_info_factory(_api_factory)
    site_engine.register_user_info_factory(_html_config_factory)

    site_rate_limiter = SiteRateLimiterService()
    site_cache = SiteCache(site_engine=site_engine, rate_limiter=site_rate_limiter)
    site_engine.site_limiter = site_rate_limiter
    message_queue = MessageQueueFactory.create()
    hook_system = HookSystem(plugin_sandbox=None)

    plugin_sandbox = PluginSandbox(
        plugin_registry=plugin_registry,
        message=message,
        scheduler_core=scheduler_core,
        hook_system=hook_system,
        site_engine=site_engine,
        media_service=None,
        plugin_log_repo=PluginLogRepositoryAdapter(),
    )
    hook_system.set_plugin_sandbox(plugin_sandbox)

    event_bus = EventBus(
        registry=EventHandlerRegistry(),
        bridge=PluginBridge(hook_system=hook_system),
        message_queue=message_queue,
        middleware=[
            LoggingMiddleware(),
            ErrorHandlingMiddleware(),
        ],
    )
    register_modules(EVENT_HANDLER_MODULES)
    auto_register(event_bus)

    log.info("[DI]基础设施层构建完成")
    return InfrastructureObjects(
        event_bus=event_bus,
        thread_executor=thread_executor,
        scheduler_core=scheduler_core,
        message=message,
        message_queue=message_queue,
        site_cache=site_cache,
        site_engine=site_engine,
        hook_system=hook_system,
        plugin_sandbox=plugin_sandbox,
        plugin_registry=plugin_registry,
        apikey_service=apikey_service,
    )
