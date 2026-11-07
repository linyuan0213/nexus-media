"""转移 / 搜索 / TMDB 数据正确性回归测试."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.media_types import ProviderMediaType
from app.media.lookup.tmdb_client import update_tmdbinfo_cn_title
from app.services.search_orchestrator import SearchOrchestrator
from app.services.transfer.filetransfer_service import FileTransferService


class TestEpisodeInHistory:
    def test_range_matches_all_episodes(self):
        h = SimpleNamespace(season_episode="S01 E01-E05")
        for ep in range(1, 6):
            assert FileTransferService._episode_in_history([h], ep) is True
        assert FileTransferService._episode_in_history([h], 6) is False

    def test_single_episode(self):
        h = SimpleNamespace(season_episode="S01E03")
        assert FileTransferService._episode_in_history([h], 3) is True
        assert FileTransferService._episode_in_history([h], 4) is False


class TestMergeTransferResults:
    def test_failure_result_marks_failed(self):
        svc = FileTransferService.__new__(FileTransferService)
        merged = svc._merge_transfer_results([{"failed_count": 1, "success_flag": False, "error_message": "boom"}])
        assert merged["success_flag"] is False
        assert merged["error_message"] == "boom"

    def test_run_parallel_wrapper_returns_failure_dict(self):
        svc = FileTransferService.__new__(FileTransferService)
        svc._thread_executor = cast(Any, ThreadPoolExecutor(max_workers=2))

        def boom(_item):
            raise RuntimeError("boom")

        try:
            results = svc._run_parallel([{"x": 1}], boom)
        finally:
            svc._thread_executor.shutdown(wait=True)

        assert len(results) == 1
        assert results[0]["success_flag"] is False
        assert results[0]["failed_count"] == 1


class TestTmdbLanguage:
    def test_en_language_does_not_force_chinese(self):
        info = {"media_type": ProviderMediaType.MOVIE, "title": "English Title"}
        result = update_tmdbinfo_cn_title(dict(info), "en")
        assert result["title"] == "English Title"


class TestSearchFilterDownloaded:
    def test_uses_completed_semantics(self):
        svc = SearchOrchestrator.__new__(SearchOrchestrator)
        repo = MagicMock()
        repo.is_completed_by_tmdb.return_value = True
        svc._download_repo = repo

        item = MagicMock()
        item.tmdb_id = 123
        item.get_season_episode_string.return_value = "S01E01"

        assert svc._filter_downloaded([item]) == []
        repo.is_completed_by_tmdb.assert_called_once()
        repo.is_exists_by_tmdb.assert_not_called()
