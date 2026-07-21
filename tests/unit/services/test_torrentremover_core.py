"""TorrentRemoverService 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.downloader.strategy import RemoveStrategy
from app.schemas.download import TorrentStatus
from app.services.torrentremover_core import TorrentRemoverRepository, TorrentRemoverService


def _make_service(repo=None, downloader=None, message=None, scheduler=None):
    return TorrentRemoverService(
        repository=repo or MagicMock(spec=TorrentRemoverRepository),
        downloader=downloader or MagicMock(),
        message=message or MagicMock(),
        scheduler=scheduler or MagicMock(),
    )


class TestUpdateTorrentRemoveTask:
    """删种任务保存校验测试"""

    def test_accepts_global_status_for_any_downloader(self):
        """应接受 TorrentStatus 全局状态，而不受下载器自身支持状态限制"""
        repo = MagicMock(spec=TorrentRemoverRepository)
        svc = _make_service(repo=repo)
        svc._tasks = {}

        data = {
            "tid": "",
            "name": "Test",
            "downloader": "1",
            "action": 1,
            "interval": 60,
            "enabled": 0,
            "samedata": 0,
            "only_nexus_media": 1,
            "ratio": 0,
            "seeding_time": 0,
            "upload_avs": 0,
            "size": "",
            "tags": "",
            "savepath_key": "",
            "tracker_key": "",
            "filter_status": "Stopped",
        }

        svc.update_torrent_remove_task(data)

        repo.insert_task.assert_called_once()
        config = repo.insert_task.call_args.kwargs["config"]
        assert config["filter_status"] == ["Stopped"]

    def test_rejects_invalid_status(self):
        """非法状态应抛出 ValidationError"""
        svc = _make_service()

        data = {
            "tid": "",
            "name": "Test",
            "downloader": "1",
            "action": 1,
            "interval": 60,
            "enabled": 0,
            "samedata": 0,
            "only_nexus_media": 1,
            "ratio": 0,
            "seeding_time": 0,
            "upload_avs": 0,
            "size": "",
            "tags": "",
            "savepath_key": "",
            "tracker_key": "",
            "filter_status": "NotAStatus",
        }

        with pytest.raises(ValidationError, match="种子状态参数不合法"):
            svc.update_torrent_remove_task(data)


class TestRemoveStrategy:
    """RemoveStrategy 配置解析测试"""

    def test_converts_status_strings_to_enum(self):
        """字符串状态应转换为 TorrentStatus 枚举"""
        strategy = RemoveStrategy.from_dict({"filter_status": "Stopped"})
        assert strategy.filter_status == [TorrentStatus.Stopped]

    def test_converts_multiple_status_strings(self):
        """多个字符串状态应转换为对应的枚举列表"""
        strategy = RemoveStrategy.from_dict({"filter_status": ["Stopped", "Paused", "Uploading"]})
        assert strategy.filter_status == [
            TorrentStatus.Stopped,
            TorrentStatus.Paused,
            TorrentStatus.Uploading,
        ]

    def test_keeps_enum_values(self):
        """已是 TorrentStatus 枚举的值应保持不变"""
        strategy = RemoveStrategy.from_dict({"filter_status": [TorrentStatus.Downloading]})
        assert strategy.filter_status == [TorrentStatus.Downloading]

    def test_skips_invalid_status_strings(self):
        """非法状态字符串应被忽略"""
        strategy = RemoveStrategy.from_dict({"filter_status": "NotAStatus"})
        assert strategy.filter_status == []

    def test_empty_status(self):
        """空状态应得到空列表"""
        strategy = RemoveStrategy.from_dict({})
        assert strategy.filter_status == []
