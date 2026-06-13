"""ToolExecutor 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.agent.tool_executor import ToolExecutor


@pytest.fixture
def executor():
    return ToolExecutor(
        message=MagicMock(),
        thread_executor=MagicMock(),
        scheduler_core=MagicMock(),
        event_bus=MagicMock(),
        download_monitor=MagicMock(),
        filetransfer_service=MagicMock(),
        rss_helper=MagicMock(),
        search_intent_agent=MagicMock(),
        site_userinfo=MagicMock(),
        scheduler_service=MagicMock(),
        message_client_service=MagicMock(),
        sync_service=MagicMock(),
        subscription_monitor=MagicMock(),
        torrentremover_service=MagicMock(),
        subscribe_service=MagicMock(),
        system_lifecycle_service=MagicMock(),
        brush_service=MagicMock(),
        site_service=MagicMock(),
        rss_task_service=MagicMock(),
        media_service=MagicMock(),
        indexer_service=MagicMock(),
        downloader_core=MagicMock(),
        searcher=MagicMock(),
    )


class TestToolExecutor:
    def test_execute_unknown_tool(self, executor):
        result = executor.execute("unknown_tool")
        assert result.success is False
        assert "未实现工具" in result.error

    def test_execute_exception(self, executor):
        executor._test_tool = MagicMock(side_effect=ValueError("boom"))
        result = executor.execute("test_tool")
        assert result.success is False
        assert "boom" in result.error

    def test_system_command_scheduler_list(self, executor):
        resp = MagicMock()
        resp.code = 0
        resp.data = [MagicMock(id="j1", name="job1", paused=False, next_run_time="now")]
        executor._scheduler_service.get_jobs.return_value = resp
        result = executor._system_command(action="scheduler_list")
        assert result.success is True
        assert result.data["jobs"][0]["id"] == "j1"

    def test_system_command_scheduler_run(self, executor):
        resp = MagicMock()
        resp.code = 0
        resp.msg = "ok"
        executor._scheduler_service.run_job.return_value = resp
        result = executor._system_command(action="scheduler_run", target="j1")
        assert result.success is True
        executor._scheduler_service.run_job.assert_called_once()

    def test_system_command_scheduler_pause_resume(self, executor):
        resp = MagicMock(code=0, msg="ok")
        executor._scheduler_service.pause_job.return_value = resp
        executor._scheduler_service.resume_job.return_value = resp
        assert executor._system_command(action="scheduler_pause", target="j1").success is True
        assert executor._system_command(action="scheduler_resume", target="j1").success is True

    def test_handle_brush_list(self, executor):
        executor._brush_service.get_tasks.return_value = [{"id": "1", "name": "t1", "site": "s1", "state": "running"}]
        result = executor._system_command(action="brush_list")
        assert result.success is True
        assert result.data["tasks"][0]["name"] == "t1"

    def test_handle_brush_delete(self, executor):
        result = executor._system_command(action="brush_delete", target="1")
        assert result.success is True
        executor._brush_service.delete_task.assert_called_once_with("1")

    def test_handle_brush_delete_no_target(self, executor):
        result = executor._system_command(action="brush_delete")
        assert result.success is False

    def test_handle_site_list(self, executor):
        site = MagicMock()
        site.id = 1
        site.name = "s1"
        executor._site_service.get_sites.return_value = [site]
        result = executor._system_command(action="site_list")
        assert result.success is True

    def test_handle_site_refresh_with_target(self, executor):
        result = executor._system_command(action="site_refresh", target="s1")
        assert result.success is True
        executor._site_userinfo.refresh_site_data_now.assert_called_once_with(specify_sites=["s1"])

    def test_handle_rss_list(self, executor):
        executor._rss_task_service.get_rsstask_info.return_value = [{"id": "1", "name": "r1"}]
        result = executor._system_command(action="rss_list")
        assert result.success is True

    def test_handle_rss_run_no_target(self, executor):
        result = executor._system_command(action="rss_run")
        assert result.success is False

    def test_handle_rss_run_with_target(self, executor):
        result = executor._system_command(action="rss_run", target="1")
        assert result.success is True
        executor._rss_task_service.check_task_rss.assert_called_once_with(1)

    def test_system_command_sync_run(self, executor):
        result = executor._system_command(action="sync_run")
        assert result.success is True
        executor._sync_service.transfer_sync.assert_called_once()

    def test_system_command_subscribe_search_all(self, executor):
        result = executor._system_command(action="subscribe_search_all")
        assert result.success is True
        executor._subscription_monitor.run.assert_called_once()

    def test_system_command_auto_remove_torrents(self, executor):
        result = executor._system_command(action="auto_remove_torrents")
        assert result.success is True
        executor._torrentremover_service.auto_remove_torrents.assert_called_once()

    def test_system_command_truncate_transfer_blacklist(self, executor):
        result = executor._system_command(action="truncate_transfer_blacklist")
        assert result.success is True
        executor._filetransfer_service.truncate_transfer_blacklist.assert_called_once()

    def test_system_command_re_identify(self, executor):
        result = executor._system_command(action="re_identify")
        assert result.success is True
        executor._sync_service.re_identify_items.assert_called_once_with(flag="unidentification", ids=[])

    def test_system_command_restart_server(self, executor):
        result = executor._system_command(action="restart_server")
        assert result.success is True
        executor._system_lifecycle_service.restart_server.assert_called_once()

    def test_system_command_unknown(self, executor):
        result = executor._system_command(action="unknown_action")
        assert result.success is False

    def test_message_template_list(self, executor):
        result = executor._message_template(action="list")
        assert result.success is True
        assert "types" in result.data

    def test_message_template_get_unknown(self, executor):
        result = executor._message_template(action="get", msg_type="unknown")
        assert result.success is False

    def test_message_template_update_missing_params(self, executor):
        result = executor._message_template(action="update", msg_type="t")
        assert result.success is False
