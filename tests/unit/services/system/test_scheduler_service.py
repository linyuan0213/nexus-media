"""SchedulerService 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ResourceNotFoundError
from app.services.system.lifecycle import SchedulerService


@pytest.fixture
def scheduler_service():
    return SchedulerService(
        downloader=MagicMock(),
        sync=MagicMock(),
        thread_executor=MagicMock(),
        torrent_remover=MagicMock(),
        subscription_monitor=MagicMock(),
    )


class TestSchedulerService:
    def test_start_service_pttransfer(self, scheduler_service):
        scheduler_service.start_service("pttransfer")
        scheduler_service._thread_executor.submit.assert_called_once()
        assert scheduler_service.start_service("pttransfer") == "服务已启动"

    def test_start_service_sync(self, scheduler_service):
        scheduler_service.start_service("sync")
        scheduler_service._sync.transfer_sync.assert_not_called()
        scheduler_service._thread_executor.submit.assert_called_once()

    def test_start_service_message_commands(self, scheduler_service):
        scheduler_service.start_service("/ptt")
        scheduler_service.start_service("/ptr")
        scheduler_service.start_service("/rst")
        scheduler_service.start_service("/sub")
        assert scheduler_service._thread_executor.submit.call_count == 4

    def test_start_service_unknown(self, scheduler_service):
        with pytest.raises(ResourceNotFoundError):
            scheduler_service.start_service("unknown")

    def test_start_service_no_executor(self):
        service = SchedulerService()
        assert service.start_service("pttransfer") == "服务已启动"

    def test_command_map_caches(self, scheduler_service):
        m1 = scheduler_service._command_map
        m2 = scheduler_service._command_map
        assert m1 is m2
