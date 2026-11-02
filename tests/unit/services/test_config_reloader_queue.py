"""队列并发配置热重载测试."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from app.di.context import AppContext
from app.services import config_reloader as module
from app.services.config_reloader import ConfigReloader


class _Settings:
    def __init__(self, queue):
        self.queue = queue

    def get(self, node=None):
        if node == "queue":
            return self.queue
        return {}


def test_queue_config_change_restarts_workers():
    queue_cfg = {"transfer_workers": 4, "sync_workers": 3, "scrape_workers": 5}
    with patch.object(module, "settings", _Settings(queue_cfg)):
        ctx = SimpleNamespace(
            scrape_queue_service=MagicMock(),
            transfer_queue_service=MagicMock(),
            sync_engine=MagicMock(),
            knowledge_ingestor=None,
            conversation_store=None,
        )
        reloader = ConfigReloader(cast("AppContext", ctx))
        reloader._queue_snapshot = {"transfer_workers": 2, "sync_workers": 2, "scrape_workers": 3}

        reloader._reload_task_queues()

    ctx.scrape_queue_service.restart.assert_called_once()
    ctx.transfer_queue_service.restart.assert_called_once()
    ctx.sync_engine.restart_queue.assert_called_once()


def test_unchanged_queue_config_does_not_restart_workers():
    queue_cfg = {"transfer_workers": 2, "sync_workers": 2, "scrape_workers": 3}
    with patch.object(module, "settings", _Settings(queue_cfg)):
        ctx = SimpleNamespace(
            scrape_queue_service=MagicMock(),
            transfer_queue_service=MagicMock(),
            sync_engine=MagicMock(),
            knowledge_ingestor=None,
            conversation_store=None,
        )
        reloader = ConfigReloader(cast("AppContext", ctx))
        reloader._reload_task_queues()

    ctx.scrape_queue_service.restart.assert_not_called()
    ctx.transfer_queue_service.restart.assert_not_called()
    ctx.sync_engine.restart_queue.assert_not_called()
