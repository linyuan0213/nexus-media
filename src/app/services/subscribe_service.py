"""SubscribeService - 订阅业务 Facade 兼容层，已迁移到 app.services.subscribe 子包."""

from app.services.subscribe.service import SubscribeService

__all__ = ["SubscribeService"]
