"""Tests for app.db.repositories.subscribe_repository update defaults."""

from unittest.mock import MagicMock, patch

from app.db.models.subscribe import SubscribeTvs
from app.db.repositories.subscribe_repository import SubscribeRepository


class TestSubscribeRepositoryUpdateDefaults:
    """Test suite for update_rss_movie/update_rss_tv None handling."""

    @patch("app.db.repositories.subscribe_repository.JsonUtils.dumps", return_value='"[]"')
    def test_update_rss_movie_skips_none_fields(self, _mock_dumps):
        """None 字段不更新（保留原值），仅更新显式提供的字段"""
        repo = SubscribeRepository()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.__enter__.return_value.query.return_value = mock_query

        with patch.object(repo, "session", return_value=mock_session):
            repo.update_rss_movie(
                rssid=1,
                name="Test",
                save_path=None,
                filter_rule=None,
                download_setting=None,
                fuzzy_match=None,
                over_edition=None,
                rss_sites=["site"],
            )

        update_fields = mock_query.filter.return_value.update.call_args[0][0]
        assert update_fields["NAME"] == "Test"
        assert "SAVE_PATH" not in update_fields
        assert "FILTER_RULE" not in update_fields
        assert "DOWNLOAD_SETTING" not in update_fields
        assert "FUZZY_MATCH" not in update_fields
        assert "OVER_EDITION" not in update_fields

    @patch("app.db.repositories.subscribe_repository.JsonUtils.dumps", return_value='"[]"')
    def test_update_rss_tv_skips_none_fields(self, _mock_dumps):
        """None 字段不更新（保留原值），仅更新显式提供的字段"""
        repo = SubscribeRepository()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.__enter__.return_value.query.return_value = mock_query

        with patch.object(repo, "session", return_value=mock_session):
            repo.update_rss_tv(
                rssid=1,
                name="Test",
                season=None,
                save_path=None,
                filter_rule=None,
                download_setting=None,
                total_ep=None,
                current_ep=None,
                total=None,
                lack=None,
            )

        update_fields = mock_query.filter.return_value.update.call_args[0][0]
        assert update_fields["NAME"] == "Test"
        assert "SEASON" not in update_fields
        assert "SAVE_PATH" not in update_fields
        assert "FILTER_RULE" not in update_fields
        assert "DOWNLOAD_SETTING" not in update_fields
        assert "TOTAL_EP" not in update_fields
        assert "CURRENT_EP" not in update_fields
        assert "TOTAL" not in update_fields
        assert "LACK" not in update_fields
        assert update_fields["NAME"] == "Test"

    @patch("app.db.repositories.subscribe_repository.JsonUtils.dumps", return_value='"[]"')
    def test_update_rss_tv_normalizes_season(self, _mock_dumps):
        repo = SubscribeRepository()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.__enter__.return_value.query.return_value = mock_query
        with patch.object(repo, "session", return_value=mock_session):
            repo.update_rss_tv(rssid=1, season="1")
        update_fields = mock_query.filter.return_value.update.call_args[0][0]
        assert update_fields["SEASON"] == "S01"


class TestUpdateRssTvLackAdvancesCurrentEp:
    """update_rss_tv_lack 同步推进 current_ep（首个待下载 = 缺失集最小值）"""

    def _setup_repo(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.models.base import Base
        from app.db.models.subscribe import SubscribeTvs
        from app.db.session import SessionManager

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        mgr = SessionManager()
        mgr._engine = engine
        mgr._factory = sessionmaker(bind=engine, expire_on_commit=False)
        SubscribeRepository._session_manager = mgr
        with mgr.session_scope() as db:
            db.add(
                SubscribeTvs(
                    NAME="测试剧",
                    YEAR="2023",
                    SEASON="S01",
                    TMDBID="223564",
                    TOTAL_EP=48,
                    CURRENT_EP=26,
                    TOTAL=48,
                    LACK=23,
                    STATE="R",
                )
            )
        return mgr

    def test_advances_to_first_missing(self):
        mgr = self._setup_repo()
        repo = SubscribeRepository()
        repo.update_rss_tv_lack(title=None, year=None, season=None, rssid=1, lack_episodes=[31, 32, 33])
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            assert row.LACK == 3
            assert row.CURRENT_EP == 31  # 首个待下载集推进

    def test_advances_as_episodes_transfer(self):
        """转移 26-30 后缺失集变为 31.. → current_ep 从 26 推进到 31"""
        mgr = self._setup_repo()
        repo = SubscribeRepository()
        # 模拟转移完成：缺失集从 [26..48] 减去已转移 26-30 → [31..48]
        repo.update_rss_tv_lack(title=None, year=None, season=None, rssid=1, lack_episodes=list(range(31, 49)))
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            assert row.LACK == 18
            assert row.CURRENT_EP == 31

    def test_episode_rows_copy_subscription_scope(self):
        from app.db.models.subscribe import SubscribeTvEpisodes

        mgr = self._setup_repo()
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            row.IDENTITY_ID = "01IDENTITY"
            row.ANCHOR_PROVIDER = "tmdb"
            row.ANCHOR_EXTERNAL_ID = "223564"
            row.CONTENT_PROFILE = "default"
        repo = SubscribeRepository()
        repo.update_rss_tv_episodes(1, [3, 4])
        with mgr.session_scope() as db:
            ep = db.query(SubscribeTvEpisodes).filter(SubscribeTvEpisodes.RSSID == 1).first()
            assert ep is not None
            assert ep.EPISODES == "3,4"
            assert ep.IDENTITY_ID == "01IDENTITY"
            assert ep.ANCHOR_PROVIDER == "tmdb"
            assert ep.ANCHOR_EXTERNAL_ID == "223564"

    def test_empty_missing_keeps_current_ep(self):
        mgr = self._setup_repo()
        repo = SubscribeRepository()
        repo.update_rss_tv_lack(title=None, year=None, season=None, rssid=1, lack_episodes=[])
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            assert row.LACK == 0
            assert row.CURRENT_EP == 26  # 无缺失集时不改 current_ep（完成态由 STATE 表达）

    def test_update_current_ep_resets_persisted_missing(self):
        """编辑开始集数时应重置缺失集列表与 LACK，避免进度被旧列表推回"""
        from app.db.models.subscribe import SubscribeTvEpisodes

        mgr = self._setup_repo()
        repo = SubscribeRepository()
        repo.update_rss_tv(rssid=1, current_ep=5, total=48)
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            assert row.CURRENT_EP == 5
            assert row.LACK == 44  # 5..48 共 44 集
            ep = db.query(SubscribeTvEpisodes).filter(SubscribeTvEpisodes.RSSID == 1).first()
            assert ep is not None
            assert ep.EPISODES.startswith("5,")
            assert ep.EPISODES.endswith(",48")


class TestDescTruncation:
    """DESC 为 varchar(255)，更新路径必须截断，否则 PostgreSQL 报 StringDataRightTruncation。"""

    def _setup_repo(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.models.base import Base
        from app.db.models.subscribe import SubscribeMovies, SubscribeTvs
        from app.db.session import SessionManager

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        mgr = SessionManager()
        mgr._engine = engine
        mgr._factory = sessionmaker(bind=engine, expire_on_commit=False)
        SubscribeRepository._session_manager = mgr
        with mgr.session_scope() as db:
            db.add(SubscribeTvs(NAME="剧", SEASON="S01", TMDBID="1", STATE="R"))
            db.add(SubscribeMovies(NAME="片", TMDBID="2", STATE="R"))
        return mgr

    def test_update_rss_tv_truncates_long_desc(self):
        mgr = self._setup_repo()
        repo = SubscribeRepository()
        long_desc = "字" * 400
        repo.update_rss_tv(rssid=1, desc=long_desc)
        with mgr.session_scope() as db:
            row = db.query(SubscribeTvs).filter(SubscribeTvs.ID == 1).first()
            assert row is not None
            assert row.DESC == long_desc[:200]
            assert len(row.DESC) == 200

    def test_update_rss_movie_truncates_long_desc(self):
        mgr = self._setup_repo()
        repo = SubscribeRepository()
        long_desc = "字" * 400
        repo.update_rss_movie(rssid=1, desc=long_desc)
        with mgr.session_scope() as db:
            from app.db.models.subscribe import SubscribeMovies

            row = db.query(SubscribeMovies).filter(SubscribeMovies.ID == 1).first()
            assert row is not None
            assert row.DESC == long_desc[:200]
            assert len(row.DESC) == 200

    def test_trim_desc_handles_none_and_short(self):
        from app.db.repositories.subscribe_repository import _trim_desc

        assert _trim_desc(None) == ""
        assert _trim_desc("abc") == "abc"
        assert len(_trim_desc("x" * 300)) == 200


class TestSubscribeHistoryNullFields:
    """回归：电影等无季/集信息时 SUBSCRIBE_HISTORY.SEASON/TOTAL/START(NOT NULL) 不得写入 NULL。"""

    def _setup(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.models.base import Base
        from app.db.session import SessionManager

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        mgr = SessionManager()
        mgr._engine = engine
        mgr._factory = sessionmaker(bind=engine, expire_on_commit=False)
        SubscribeRepository._session_manager = mgr
        return mgr

    def test_insert_movie_history_none_season(self):
        from app.db.models.subscribe import SubscribeHistory

        mgr = self._setup()
        repo = SubscribeRepository()
        repo.insert_rss_history(
            rssid=1,
            rtype="movie",
            name="欢迎来龙餐馆",
            year="2026",
            tmdbid="1391021",
            image="",
            desc="",
            season=None,
            total=None,
            start=None,
        )
        with mgr.session_scope() as db:
            row = db.query(SubscribeHistory).first()
            assert row is not None
            assert row.SEASON == ""
            assert row.TOTAL == 0
            assert row.START == 0
            assert row.ANCHOR_PROVIDER == "tmdb"
            assert row.ANCHOR_EXTERNAL_ID == "1391021"
            assert row.METADATA_POLICY == "tmdb_primary"

    def test_upsert_movie_history_none_season(self):
        from app.db.models.subscribe import SubscribeHistory

        mgr = self._setup()
        repo = SubscribeRepository()
        repo.upsert_rss_history(
            rssid=2,
            rtype="movie",
            name="年会不能停！2",
            year="2026",
            tmdbid="1541125",
            image="",
            desc="",
            season=None,
            total=None,
            start=None,
        )
        with mgr.session_scope() as db:
            row = db.query(SubscribeHistory).first()
            assert row is not None
            assert row.SEASON == ""
            assert row.TOTAL == 0
            assert row.START == 0
            assert row.ANCHOR_PROVIDER == "tmdb"
            assert row.ANCHOR_EXTERNAL_ID == "1541125"


class TestRssTorrentScope:
    def test_insert_rss_torrent_persists_scope(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.models.base import Base
        from app.db.models.subscribe import SubscribeTorrents
        from app.db.session import SessionManager

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        mgr = SessionManager()
        mgr._engine = engine
        mgr._factory = sessionmaker(bind=engine, expire_on_commit=False)
        SubscribeRepository._session_manager = mgr
        repo = SubscribeRepository()
        repo.insert_rss_torrent(
            "torrent",
            "magnet:?xt=urn:btih:abc",
            "movie",
            "电影",
            "2024",
            "",
            "",
            identity_id="01IDENTITY",
            anchor_provider="tmdb",
            anchor_external_id="100",
            content_profile="default",
        )
        with mgr.session_scope() as db:
            row = db.query(SubscribeTorrents).first()
            assert row is not None
            assert row.IDENTITY_ID == "01IDENTITY"
            assert row.ANCHOR_PROVIDER == "tmdb"
            assert row.ANCHOR_EXTERNAL_ID == "100"
