"""批次游标持久化测试."""

from unittest.mock import MagicMock

from app.services.subscribe.strategies.base_search import BaseSearchStrategy


def _strategy(cursor: int = 0, fail_load: bool = False, fail_save: bool = False):
    strategy = object.__new__(BaseSearchStrategy)
    strategy._batch_cursors = {}
    repo = MagicMock()
    if fail_load:
        repo.get_search_cursor.side_effect = RuntimeError("db down")
    else:
        repo.get_search_cursor.return_value = cursor
    if fail_save:
        repo.set_search_cursor.side_effect = RuntimeError("db down")
    strategy._rss_repo = repo
    return strategy, repo


class TestBatchCursorPersistence:
    def test_resumes_from_persisted_cursor(self):
        strategy, repo = _strategy(cursor=3)

        batch = strategy._take_batch(list(range(10)), "movie", 2)

        assert batch == [3, 4]
        repo.set_search_cursor.assert_called_once_with("movie", 5)

    def test_falls_back_to_zero_when_load_fails(self):
        strategy, repo = _strategy(fail_load=True)

        batch = strategy._take_batch(list(range(10)), "movie", 2)

        assert batch == [0, 1]
        repo.set_search_cursor.assert_called_once_with("movie", 2)

    def test_save_failure_keeps_memory_cursor(self):
        strategy, _repo = _strategy(cursor=0, fail_save=True)

        strategy._take_batch(list(range(10)), "movie", 2)

        assert strategy._batch_cursors["movie"] == 2

    def test_small_list_returns_all_without_cursor_change(self):
        strategy, repo = _strategy(cursor=1)

        assert strategy._take_batch([1, 2], "movie", 2) == [1, 2]
        repo.set_search_cursor.assert_not_called()
