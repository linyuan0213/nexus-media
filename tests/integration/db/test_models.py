"""数据库模型单元测试"""


class TestDatabaseModels:
    def test_base_create_tables(self, db_session):
        """验证所有模型表能正确创建"""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        tables = inspector.get_table_names()
        assert len(tables) > 0
        assert "RBAC_USERS" in tables
        assert "CONFIG_USERS" in tables

    def test_rbac_user_crud(self, db_session):
        """RBACUser 增删改查"""
        from app.db.models import RBACUser

        user = RBACUser(
            USERNAME="testuser",
            PASSWORD_HASH="hash123",
            EMAIL="test@example.com",
            STATUS=1,
        )
        db_session.add(user)
        db_session.commit()

        result = db_session.query(RBACUser).filter_by(USERNAME="testuser").first()
        assert result is not None
        assert result.EMAIL == "test@example.com"
        assert result.ID is not None

    def test_config_users_crud(self, db_session):
        """CONFIGUSERS 增删改查"""
        from app.db.models import CONFIGUSERS

        user = CONFIGUSERS(NAME="admin", PASSWORD="secret", PRIS="admin")
        db_session.add(user)
        db_session.commit()

        result = db_session.query(CONFIGUSERS).filter_by(NAME="admin").first()
        assert result is not None
        assert result.PRIS == "admin"

    def test_rss_movies_crud(self, db_session):
        """RSSMOVIES 增删改查"""
        from app.db.models import RSSMOVIES

        movie = RSSMOVIES(
            NAME="Test Movie",
            YEAR="2024",
            TMDBID="12345",
            KEYWORD="",
            IMAGE="",
            RSS_SITES="",
            SEARCH_SITES="",
            OVER_EDITION=0,
            FILTER_ORDER=0,
            FILTER_RESTYPE="",
            FILTER_PIX="",
            FILTER_RULE=0,
            FILTER_TEAM="",
            FILTER_INCLUDE="",
            FILTER_EXCLUDE="",
            SAVE_PATH="",
            DOWNLOAD_SETTING=0,
            FUZZY_MATCH=0,
            STATE="",
            DESC="",
            NOTE="",
        )
        db_session.add(movie)
        db_session.commit()

        result = db_session.query(RSSMOVIES).filter_by(NAME="Test Movie").first()
        assert result is not None
        assert result.YEAR == "2024"

    def test_download_history_crud(self, db_session):
        """DOWNLOADHISTORY 增删改查"""
        from app.db.models import DOWNLOADHISTORY

        record = DOWNLOADHISTORY(
            TITLE="Test",
            YEAR="",
            TYPE="TV",
            TMDBID="",
            SE="",
            VOTE="",
            POSTER="",
            OVERVIEW="",
            TORRENT="",
            ENCLOSURE="",
            SITE="",
            DESC="",
            DOWNLOADER="",
            DOWNLOAD_ID="",
            SAVE_PATH="/downloads/test.mkv",
            STATE="downloading",
            DATE="",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(DOWNLOADHISTORY).filter_by(TITLE="Test").first()
        assert result is not None
        assert result.TYPE == "TV"

    def test_transfer_history_crud(self, db_session):
        """TRANSFERHISTORY 增删改查"""
        from app.db.models import TRANSFERHISTORY

        record = TRANSFERHISTORY(
            MODE="link",
            TYPE="TV",
            CATEGORY="",
            TMDBID=0,
            TITLE="Test",
            YEAR="",
            SEASON_EPISODE="",
            SOURCE="/src/test.mkv",
            SOURCE_PATH="/src",
            SOURCE_FILENAME="test.mkv",
            DEST="/dest/test.mkv",
            DEST_PATH="/dest",
            DEST_FILENAME="test.mkv",
            DST_BACKEND=None,
            DATE="",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(TRANSFERHISTORY).filter_by(SOURCE="/src/test.mkv").first()
        assert result is not None
        assert result.MODE == "link"
