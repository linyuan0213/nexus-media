"""DI 基础设施 builder 单元测试."""

from unittest.mock import MagicMock, patch

from app.di.builders.infrastructure_builder import build_infrastructure
from app.events.bus import EventBus
from app.events.middleware import ErrorHandlingMiddleware, LoggingMiddleware


class TestBuildInfrastructure:
    """测试基础设施 builder."""

    def _build_with_mocks(self):
        """使用 mock 隔离重依赖，仅验证 EventBus 创建与注册."""
        site_engine_instance = MagicMock()
        site_engine_instance.get_by_url.return_value = None
        mq_factory = MagicMock()
        mq_factory.create.return_value = MagicMock()
        mocks = {
            "SiteEngine": MagicMock(return_value=site_engine_instance),
            "SiteCache": MagicMock(),
            "PluginRegistry": MagicMock(),
            "PluginSandbox": MagicMock(),
            "HookSystem": MagicMock(),
            "MessageQueueFactory": mq_factory,
        }
        with patch.multiple("app.di.builders.infrastructure_builder", **mocks):
            return build_infrastructure()

    def test_build_infrastructure_creates_event_bus(self):
        """构建基础设施时应创建 EventBus."""
        infra = self._build_with_mocks()
        assert isinstance(infra.event_bus, EventBus)

    def test_build_infrastructure_registers_event_handlers(self):
        """构建基础设施时应注册 @on_event handler."""
        with patch("app.di.builders.infrastructure_builder.register_modules") as mock_register:
            with patch("app.di.builders.infrastructure_builder.auto_register") as mock_auto:
                self._build_with_mocks()

        mock_register.assert_called_once()
        mock_auto.assert_called_once()

    def test_build_infrastructure_event_bus_has_middleware(self):
        """EventBus 应配置中间件."""
        infra = self._build_with_mocks()
        middleware_types = [type(m) for m in infra.event_bus._middleware]
        assert LoggingMiddleware in middleware_types
        assert ErrorHandlingMiddleware in middleware_types
