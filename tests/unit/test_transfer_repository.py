"""TransferRepository.get_transfer_series_statistics 回归测试."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import TRANSFERHISTORY, Base
from app.db.repositories.transfer_repository import TransferRepository
from app.db.session import SessionManager


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    manager = SessionManager()
    manager._engine = engine
    manager._factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    TransferRepository._session_manager = manager
    yield TransferRepository()
    engine.dispose()


def _insert(repo: TransferRepository, mtype: str, tmdbid: int, date: str) -> None:
    with repo.session() as db:
        db.add(
            TRANSFERHISTORY(
                MODE="link",
                TYPE=mtype,
                CATEGORY="",
                TMDBID=tmdbid,
                TITLE=f"title-{tmdbid}",
                YEAR="2024",
                SEASON_EPISODE="S01E01",
                SOURCE="",
                SOURCE_PATH="/src",
                SOURCE_FILENAME="f.mkv",
                DEST="",
                DEST_PATH="/dst",
                DEST_FILENAME="f.mkv",
                DATE=date,
            )
        )
        db.commit()


def _insert_at(
    repo: TransferRepository,
    source_path: str,
    source_filename: str,
    dest_path: str,
    dest_filename: str,
    date: str = "2024-01-01 10:00:00",
) -> None:
    with repo.session() as db:
        db.add(
            TRANSFERHISTORY(
                MODE="link",
                TYPE="tv",
                CATEGORY="",
                TMDBID=1,
                TITLE="title",
                YEAR="2024",
                SEASON_EPISODE="S01E01",
                SOURCE="",
                SOURCE_PATH=source_path,
                SOURCE_FILENAME=source_filename,
                DEST="",
                DEST_PATH=dest_path,
                DEST_FILENAME=dest_filename,
                DATE=date,
            )
        )
        db.commit()


class TestGetTransferHistoryBySourceDir:
    def test_returns_dir_rows_sorted_desc(self, repo):
        _insert_at(repo, "/src/Movie", "E01.mkv", "/lib/Movie", "E01.mkv", "2024-01-01 10:00:00")
        _insert_at(repo, "/src/Movie", "E02.mkv", "/lib/Movie", "E02.mkv", "2024-01-02 10:00:00")
        _insert_at(repo, "/src/Other", "x.mkv", "/lib/Other", "x.mkv")
        rows = repo.get_transfer_history_by_source_dir("/src/Movie")
        assert [r.SOURCE_FILENAME for r in rows] == ["E02.mkv", "E01.mkv"]

    def test_normpath_and_empty(self, repo):
        _insert_at(repo, "/src/Movie", "E01.mkv", "/lib/Movie", "E01.mkv")
        assert len(repo.get_transfer_history_by_source_dir("/src/./Movie")) == 1
        assert repo.get_transfer_history_by_source_dir("") == []

    def test_includes_subdir_rows_only(self, repo):
        _insert_at(repo, "/src/tv/Show/S01", "E01.mkv", "/lib/Show/S01", "E01.mkv")
        _insert_at(repo, "/src/tv/Show2/S01", "E01.mkv", "/lib/Show2/S01", "E01.mkv")
        _insert_at(repo, "/src/tvother", "x.mkv", "/lib/x", "x.mkv")
        rows = repo.get_transfer_history_by_source_dir("/src/tv")
        assert {r.SOURCE_PATH for r in rows} == {"/src/tv/Show/S01", "/src/tv/Show2/S01"}

    def test_exact_dir_and_subdir(self, repo):
        _insert_at(repo, "/src/tv", "E01.mkv", "/lib/tv", "E01.mkv")
        _insert_at(repo, "/src/tv/S01", "E02.mkv", "/lib/tv/S01", "E02.mkv")
        assert len(repo.get_transfer_history_by_source_dir("/src/tv")) == 2


class TestGetTransferSeriesStatistics:
    def test_distinct_series_per_day(self, repo):
        _insert(repo, "tv", 101, "2024-01-01 10:00:00")
        _insert(repo, "tv", 101, "2024-01-01 11:00:00")
        _insert(repo, "tv", 102, "2024-01-01 12:00:00")
        _insert(repo, "tv", 103, "2024-01-02 09:00:00")
        result = repo.get_transfer_series_statistics(days=0)
        assert result == [("2024-01-01", 2), ("2024-01-02", 1)]

    def test_ignores_movie_and_zero_tmdbid(self, repo):
        _insert(repo, "movie", 201, "2024-01-01 10:00:00")
        _insert(repo, "tv", 0, "2024-01-01 10:00:00")
        _insert(repo, "tv", 202, "2024-01-01 10:00:00")
        result = repo.get_transfer_series_statistics(days=0)
        assert result == [("2024-01-01", 1)]

    def test_empty(self, repo):
        assert repo.get_transfer_series_statistics(days=0) == []
