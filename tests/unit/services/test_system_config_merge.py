"""系统配置深合并写入测试（防止整体覆盖丢失既有键）."""

from unittest.mock import MagicMock

from app.services.system.config import SystemConfigService


def _service(initial):
    store = MagicMock()
    store.get.return_value = initial
    return SystemConfigService(store), store


class TestSetMerged:
    def test_preserves_unknown_keys(self):
        svc, store = _service(
            {"scraper_pic": {"tv": {"poster": True, "episode_thumb": True, "episode_thumb_ffmpeg": False}}}
        )
        svc.set_merged("UserScraperConf", {"scraper_pic": {"tv": {"poster": False}}})
        written = store.set.call_args.kwargs["value"]
        assert written["scraper_pic"]["tv"]["episode_thumb"] is True
        assert written["scraper_pic"]["tv"]["episode_thumb_ffmpeg"] is False
        assert written["scraper_pic"]["tv"]["poster"] is False

    def test_non_dict_value_replaces(self):
        svc, store = _service({"k": 1})
        svc.set_merged("k", [1, 2])
        assert store.set.call_args.kwargs["value"] == [1, 2]

    def test_missing_current_uses_patch(self):
        svc, store = _service(None)
        svc.set_merged("UserScraperConf", {"scraper_nfo": {"tv": {"basic": True}}})
        assert store.set.call_args.kwargs["value"] == {"scraper_nfo": {"tv": {"basic": True}}}
